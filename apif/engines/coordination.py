"""Coordination / bot-campaign detection.

HONEST SCOPE: this is a heuristic detector, not the trained GNN described in plan.md.
There is no labelled bot dataset in this project, and a GNN trained on nothing would be
less trustworthy than a well-understood heuristic -- in a regulatory tool, a scoring
method you can explain to SEBI beats one you cannot. The signal is reported as such.

The apparent blocker is that Firecrawl returns only title/description/url for each
X/Twitter hit -- no author, no timestamp, which is exactly what coordination analysis
needs. Both are recoverable from the URL alone:

  https://x.com/<handle>/status/<id>
                ^ author        ^ snowflake ID

A Twitter snowflake's upper 41 bits are a millisecond timestamp offset from the Twitter
epoch (1288834974657). So `id >> 22` plus that epoch gives post time to the millisecond.

Coordination is then: distinct accounts posting near-identical text about the same
ticker inside a tight time window. Each dimension alone is innocent -- shared wording is
just a retweet, a burst is just breaking news, several accounts is just popularity. The
product of all three is a campaign.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

import networkx as nx

from ..schemas import SIGNAL_COORDINATION, Signal

TWITTER_EPOCH_MS = 1288834974657

# Twitter used plain sequential IDs before migrating to snowflake on 2010-11-04, at
# which point IDs were around 2.97e10. Anything smaller is a legacy or fabricated ID:
# bit-shifting it yields a timestamp at (or just after) the epoch, which would silently
# enter the burst analysis as a real 2010 post. Reject rather than decode.
_MIN_SNOWFLAKE_ID = 29_000_000_000

_STATUS_RE = re.compile(
    r"(?:twitter|x)\.com/(?P<handle>[A-Za-z0-9_]{1,15})/status(?:es)?/(?P<id>\d+)",
    re.IGNORECASE,
)

# Cosine similarity at which two posts count as the same message. 0.85 tolerates the
# token-level edits campaigns use to dodge exact-duplicate filters, without collapsing
# genuinely different posts that merely share finance vocabulary.
_SIMILARITY_THRESHOLD = 0.85
_MIN_CLUSTER_ACCOUNTS = 3


def parse_status_url(url: str) -> dict[str, Any] | None:
    """Recover author handle and post time from an X/Twitter status URL."""
    match = _STATUS_RE.search(url or "")
    if not match:
        return None
    status_id = int(match.group("id"))
    if status_id < _MIN_SNOWFLAKE_ID:
        return None
    # Snowflake: 41-bit ms timestamp in the high bits, then worker/sequence bits.
    posted_ms = (status_id >> 22) + TWITTER_EPOCH_MS
    try:
        posted_at = datetime.fromtimestamp(posted_ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    # Sanity bound: IDs predating Twitter or far in the future are not real statuses.
    if not (2010 <= posted_at.year <= datetime.now(timezone.utc).year + 1):
        return None
    return {"handle": match.group("handle").lower(), "status_id": status_id,
            "posted_at": posted_at}


def _prepare(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only items whose URL yields an author and timestamp."""
    prepared = []
    for item in items or []:
        parsed = parse_status_url(item.get("url", ""))
        if not parsed:
            continue
        text = " ".join(
            str(item.get(k, "")) for k in ("headline", "title", "summary", "description")
        ).strip()
        if not text:
            continue
        prepared.append({**parsed, "text": text, "url": item.get("url", ""),
                         "company": item.get("company", "")})
    return prepared


def _cluster(posts: list[dict[str, Any]]) -> list[list[int]]:
    """Group near-duplicate posts via TF-IDF cosine similarity over a similarity graph."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [p["text"] for p in posts]
    try:
        matrix = TfidfVectorizer(stop_words="english", min_df=1).fit_transform(texts)
    except ValueError:
        return []  # every document was stop-words only

    similarity = cosine_similarity(matrix)
    graph = nx.Graph()
    graph.add_nodes_from(range(len(posts)))
    for i in range(len(posts)):
        for j in range(i + 1, len(posts)):
            if similarity[i, j] >= _SIMILARITY_THRESHOLD:
                graph.add_edge(i, j, weight=float(similarity[i, j]))

    return [sorted(component) for component in nx.connected_components(graph)]


def _score_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    handles = {p["handle"] for p in cluster}
    times = sorted(p["posted_at"] for p in cluster)
    span_minutes = max((times[-1] - times[0]).total_seconds() / 60.0, 0.0)

    # Accounts: 3 is unremarkable, 15+ is a network.
    account_factor = min(1.0, (len(handles) - _MIN_CLUSTER_ACCOUNTS + 1) / 12.0)
    # Compression: same message from many accounts inside an hour is the strongest tell.
    burst_factor = 1.0 if span_minutes <= 60 else max(0.0, 1.0 - (span_minutes - 60) / 1440)

    return {
        "accounts": sorted(handles),
        "account_count": len(handles),
        "post_count": len(cluster),
        "span_minutes": round(span_minutes, 1),
        "first_post": times[0].isoformat(),
        "last_post": times[-1].isoformat(),
        "sample_text": cluster[0]["text"][:280],
        "urls": [p["url"] for p in cluster[:10]],
        "score": round(min(1.0, 0.5 * account_factor + 0.5 * burst_factor), 4),
    }


def analyze(items: list[dict[str, Any]]) -> Signal:
    """Detect coordinated amplification across social posts. Never raises."""
    posts = _prepare(items)
    if len(posts) < _MIN_CLUSTER_ACCOUNTS:
        return Signal.unavailable(
            SIGNAL_COORDINATION,
            f"only {len(posts)} post(s) with a resolvable author and timestamp - "
            "too few to assess coordination",
        )

    try:
        components = _cluster(posts)
    except Exception as exc:  # noqa: BLE001
        return Signal.unavailable(
            SIGNAL_COORDINATION, f"clustering failed ({type(exc).__name__}: {exc})"
        )

    clusters = []
    for component in components:
        members = [posts[i] for i in component]
        if len({p["handle"] for p in members}) < _MIN_CLUSTER_ACCOUNTS:
            # One account posting repeatedly is spam, not coordination.
            continue
        clusters.append(_score_cluster(members))

    if not clusters:
        return Signal(
            name=SIGNAL_COORDINATION,
            score=0.0,
            available=True,
            summary=f"No coordinated clusters across {len(posts)} analysed posts",
            evidence={"posts_analysed": len(posts), "clusters": [],
                      "method": "heuristic (TF-IDF similarity + burst timing)"},
        )

    clusters.sort(key=lambda c: c["score"], reverse=True)
    top = clusters[0]
    return Signal(
        name=SIGNAL_COORDINATION,
        score=top["score"],
        available=True,
        summary=(
            f"{top['account_count']} accounts posted near-identical content within "
            f"{top['span_minutes']:.0f} minutes"
        ),
        evidence={
            "posts_analysed": len(posts),
            "cluster_count": len(clusters),
            "clusters": clusters[:5],
            "method": "heuristic (TF-IDF similarity + burst timing), not a trained GNN",
        },
    )
