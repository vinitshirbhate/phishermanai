"""Market-correlation engine.

A rumour is far more serious when the stock it names actually moved. This engine takes
the tickers the LLM analyst extracted and asks whether price/volume around the content's
timestamp is anomalous versus that stock's own recent baseline.

Deliberately simple statistics -- a z-score against a 20-day rolling window. The plan
mentions Granger causality; with a single rumour timestamp and daily bars there aren't
enough observations for it to mean anything, and a spurious causality claim in a
regulatory tool is worse than an honest anomaly score.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import anyio

from ..schemas import SIGNAL_MARKET_ANOMALY, Signal

_BASELINE_DAYS = 20
_WINDOW_DAYS = 2          # trading days either side of the content timestamp
_HISTORY_DAYS = 90        # enough calendar days to yield ~60 trading bars

# A z-score of 4+ is a dramatic, obvious move; anything beyond adds no signal.
_Z_SATURATION = 4.0


def _fetch_sync(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    # NSE symbols carry a .NS suffix on Yahoo Finance; BSE would be .BO.
    symbol = ticker if ticker.endswith((".NS", ".BO")) else f"{ticker}.NS"
    frame = yf.Ticker(symbol).history(period=f"{_HISTORY_DAYS}d", interval="1d")
    if frame is None or frame.empty:
        return {"ticker": ticker, "symbol": symbol, "error": "no price data returned"}
    return {"ticker": ticker, "symbol": symbol, "frame": frame}


def _analyze_frame(payload: dict[str, Any], at: datetime) -> dict[str, Any]:
    """Compute volume and return z-scores near `at`, versus a trailing baseline."""
    import numpy as np
    import pandas as pd

    frame = payload["frame"]
    frame = frame.copy()
    # fill_method=None: forward-filling a gap would manufacture a 0% return on a day
    # with no trade, diluting the very baseline volatility we measure against.
    frame["return"] = frame["Close"].pct_change(fill_method=None)

    index = frame.index
    if index.tz is not None:
        target = pd.Timestamp(at).tz_convert(index.tz) if pd.Timestamp(at).tz is not None \
            else pd.Timestamp(at).tz_localize("UTC").tz_convert(index.tz)
    else:
        target = pd.Timestamp(at).tz_localize(None)

    # Bars within +/- _WINDOW_DAYS of the content. Markets close, so an exact match
    # rarely exists -- take everything in the span.
    lo, hi = target - timedelta(days=_WINDOW_DAYS), target + timedelta(days=_WINDOW_DAYS)
    window = frame.loc[(index >= lo) & (index <= hi)]
    if window.empty:
        return {
            "ticker": payload["ticker"], "symbol": payload["symbol"],
            "error": "no trading days within the correlation window",
        }

    # Baseline must exclude the window itself, or a large spike inflates its own
    # standard deviation and hides the anomaly it is supposed to reveal.
    baseline = frame.loc[index < lo].tail(_BASELINE_DAYS)
    if len(baseline) < 5:
        return {
            "ticker": payload["ticker"], "symbol": payload["symbol"],
            "error": "insufficient baseline history",
        }

    vol_mean, vol_std = baseline["Volume"].mean(), baseline["Volume"].std()
    ret_std = baseline["return"].std()

    volume_z = (
        float((window["Volume"].max() - vol_mean) / vol_std)
        if vol_std and not np.isnan(vol_std) and vol_std > 0 else 0.0
    )
    # A single-row window has a NaN return, and `NaN or 0.0` evaluates to NaN (NaN is
    # truthy) -- which would propagate a NaN score into fusion. Test explicitly.
    raw_peak = window["return"].abs().max()
    peak_return = 0.0 if raw_peak is None or np.isnan(raw_peak) else float(raw_peak)
    return_z = (
        float(peak_return / ret_std)
        if ret_std and not np.isnan(ret_std) and ret_std > 0 else 0.0
    )

    return {
        "ticker": payload["ticker"],
        "symbol": payload["symbol"],
        "volume_z": round(volume_z, 2),
        "return_z": round(return_z, 2),
        "peak_abs_return_pct": round(peak_return * 100, 2),
        "baseline_days": len(baseline),
        "window_start": str(window.index.min().date()),
        "window_end": str(window.index.max().date()),
    }


def _score_from_z(volume_z: float, return_z: float) -> float:
    strongest = max(abs(volume_z), abs(return_z))
    return max(0.0, min(1.0, strongest / _Z_SATURATION))


async def analyze(tickers: list[str], at: datetime | None = None) -> Signal:
    """Score abnormal market activity around `at` for the given tickers. Never raises."""
    tickers = [t.strip().upper() for t in (tickers or []) if t and t.strip()]
    if not tickers:
        return Signal.unavailable(
            SIGNAL_MARKET_ANOMALY, "no tickers identified in the content"
        )

    at = at or datetime.now(timezone.utc)
    per_ticker: list[dict[str, Any]] = []

    for ticker in tickers[:5]:  # bound external calls; a rumour naming 20 stocks is noise
        try:
            payload = await anyio.to_thread.run_sync(_fetch_sync, ticker)
            if "error" in payload:
                per_ticker.append(payload)
                continue
            per_ticker.append(await anyio.to_thread.run_sync(_analyze_frame, payload, at))
        except Exception as exc:  # noqa: BLE001 - yfinance raises broadly on network issues
            per_ticker.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})

    scored = [t for t in per_ticker if "error" not in t]
    if not scored:
        reasons = {t.get("error", "unknown") for t in per_ticker}
        return Signal.unavailable(
            SIGNAL_MARKET_ANOMALY, f"no usable market data ({'; '.join(sorted(reasons))})"
        )

    best = max(scored, key=lambda t: max(abs(t["volume_z"]), abs(t["return_z"])))
    score = _score_from_z(best["volume_z"], best["return_z"])

    return Signal(
        name=SIGNAL_MARKET_ANOMALY,
        score=score,
        available=True,
        summary=(
            f"{best['ticker']}: volume {best['volume_z']:+.1f}sigma, "
            f"return {best['return_z']:+.1f}sigma "
            f"({best['peak_abs_return_pct']:+.1f}% peak move) vs its {_BASELINE_DAYS}-day baseline"
        ),
        evidence={
            "evaluated_at": at.isoformat(),
            "strongest": best,
            "per_ticker": per_ticker,
        },
    )
