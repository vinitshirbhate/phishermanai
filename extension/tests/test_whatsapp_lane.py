"""
WhatsApp lane - PURE-LOGIC tests.

SCOPE, STATED UP FRONT. These exercise the halves of the lane that do not touch
WhatsApp's markup: data-pre-plain-text parsing, entity extraction, channel
scoring, and W0-W6 assembly. They run against MessageRecords, which are OUR
schema, so they are not the self-consistency trap.

What they DELIBERATELY do not cover: whether selectors.js resolves against real
WhatsApp DOM. That cannot be tested without human-captured fixtures in
eval/fixtures/whatsapp/, and authoring those here would only prove the selectors
match markup written by the same author to match them. That gap is real and is
reported, not papered over - see test_selector_fixtures_are_absent_and_that_is_reported.

Everything is driven through node, since the modules are UMD JS.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
WA_FIXTURES = ROOT / "eval" / "fixtures" / "whatsapp"


def _node(body: str):
    """Load the pure WhatsApp modules under node and run `body`."""
    script = f"""
    const path = require('path');
    const EXT = {json.dumps(str(EXT).replace(chr(92), '/'))};
    const N   = require(path.join(EXT,'shared/normalise.js'));
    const SEL = require(path.join(EXT,'whatsapp/selectors.js'));
    const EX  = require(path.join(EXT,'whatsapp/extract.js'));
    const CTX = require(path.join(EXT,'whatsapp/context.js'));
    const V   = require(path.join(EXT,'whatsapp/verdict.js'));
    const out = (o) => console.log('@@' + JSON.stringify(o));
    {body}
    """
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"node failed: {r.stderr[:900]}"
    line = [l for l in r.stdout.splitlines() if l.startswith("@@")][-1]
    return json.loads(line[2:])


# --- data-pre-plain-text: the anchor attribute ------------------------------ #
def test_pre_plain_text_parses_sender_and_timestamp():
    res = _node("""
      out({
        std:  EX.parsePrePlainText('[14:32, 07/08/2026] Ramesh Kumar: '),
        ampm: EX.parsePrePlainText('[2:05 PM, 7/8/2026] Alpha Research: '),
        junk: EX.parsePrePlainText('not a pre-plain-text value'),
        phone: EX.senderIsPhoneNumber('+91 98765 43210'),
        named: EX.senderIsPhoneNumber('Ramesh Kumar'),
      });
    """)
    assert res["std"]["sender"] == "Ramesh Kumar"
    assert res["std"]["iso"].startswith("2026-08-07T14:32")
    assert res["ampm"]["iso"].startswith("2026-08-07T14:05")
    # An unparseable value must yield null, never a guessed timestamp.
    assert res["junk"] is None
    assert res["phone"] is True and res["named"] is False


# --- entity extraction, obfuscation, script handling ------------------------ #
def test_entities_survive_zero_width_and_homoglyph_obfuscation():
    res = _node(r"""
      const clean = EX.extractEntities('Pay to profitdesk99@ybl now, Rs 45,000 due. https://a.tld/x');
      // zero-width space inside the UPI id, Cyrillic 'о' in the word
      const dirty = EX.extractEntities('Pay to prof​itdesk99@ybl nоw, 2 lakh');
      out({ clean_upi: clean.upi_ids, clean_amt: clean.amounts, clean_urls: clean.urls,
            dirty_upi: dirty.upi_ids, dirty_amt: dirty.amounts,
            dirty_obf: !!dirty.obfuscation, clean_obf: !!clean.obfuscation });
    """)
    assert res["clean_upi"] == ["profitdesk99@ybl"]
    assert res["clean_amt"][0]["value"] == 45000
    assert res["clean_urls"] == ["https://a.tld/x"]
    # Zero-width must not hide the payment identifier...
    assert res["dirty_upi"] == ["profitdesk99@ybl"]
    assert res["dirty_amt"][0]["value"] == 200000
    # ...and the obfuscation is itself reported as a signal, not silently cleaned.
    assert res["dirty_obf"] is True and res["clean_obf"] is False


def test_devanagari_body_is_not_assumed_latin():
    res = _node("""
      const e = EX.extractEntities('निवेश करें, पैसा भेजें vipwealth@okaxis पर ₹50,000');
      out({ script: e.script, upi: e.upi_ids, amounts: e.amounts.map(a => a.value) });
    """)
    assert res["script"] == "indic_or_mixed"
    assert res["upi"] == ["vipwealth@okaxis"]
    assert res["amounts"] == [50000]


# --- channel signals, scored independently of content ----------------------- #
def _records_js(n=6, direction="incoming", body="Good morning"):
    return f"""
      const recs = [];
      for (let i = 0; i < {n}; i++) recs.push({{
        message_id: 'm' + i, chat_id: 'c1', direction: '{direction}',
        timestamp: '2026-07-01T10:0' + i + ':00',
        sender: {{ display_name: '+91 98765 4321' + (i % 3), is_contact: false,
                  is_business: false, is_admin: false }},
        body_text: '{body}', body_sha256: 'h' + i,
        entities: EX.extractEntities('{body}'),
        flags: {{ is_forwarded: false, forwarded_many_times: false, is_system: false,
                 has_media: false, media_kind: null, is_reply: false, is_deleted: false }},
      }});
      recs.push({{ message_id: 'sys', chat_id: 'c1', direction: 'incoming', timestamp: null,
        sender: {{ display_name: null, is_contact: null }},
        body_text: 'You were added', body_sha256: null,
        entities: EX.extractEntities(''),
        flags: {{ is_system: true, is_forwarded: false, forwarded_many_times: false,
                 has_media: false, media_kind: null, is_reply: false, is_deleted: false }} }});
    """


def test_benign_message_in_funnel_chat_is_channel_signal_and_zero_content_signal():
    """The defining BL-2 case: 'Good morning' in a W1001-VIP Wealth group."""
    res = _node(_records_js() + """
      const ch = CTX.assess({ chat_id:'c1', title:'W1001-VIP Wealth', member_count:400 }, recs, {});
      const v = V.assemble(recs[0], ch, { registration: { state: 'not_applicable' } });
      out({ signals: ch.signals, verdict: v.verdict,
            channel: v.truths.channel.state, content: v.truths.content.state,
            badge: v.badge, dcc: ch.disclosure_channel_context });
    """)
    assert "unsolicited_add" in res["signals"]
    assert "group_name_securities_funnel_pattern" in res["signals"]
    assert "skewed_poster_ratio" in res["signals"]
    assert res["verdict"] == "W1_UNSOLICITED_CONTEXT"
    # Both truths visible, neither overwriting the other.
    assert res["channel"] == "signals"
    assert res["content"] == "no_signals"
    assert res["badge"] is True
    # T3 hand-off object carries the fields securities_identity.py expects.
    for k in ("unsolicited_add", "group_name", "group_member_count",
              "distinct_posters_in_window", "prior_outgoing_message_in_chat"):
        assert k in res["dcc"]


def test_w1_needs_two_signals_not_one():
    """One funnel property alone is ordinary - plenty of legitimate groups are
    large, and plenty add you without asking."""
    res = _node(_records_js(n=3) + """
      // Contacts known, benign name, small group: only `unsolicited_add` remains.
      recs.forEach(r => { if (r.sender) r.sender.is_contact = true; });
      const ch = CTX.assess({ chat_id:'c1', title:'Class 7B Parents', member_count:40 }, recs, {});
      const v = V.assemble(recs[0], ch, { registration: { state: 'not_applicable' } });
      out({ signals: ch.signals, verdict: v.verdict, badge: v.badge });
    """)
    assert res["verdict"] == "W0_NO_SIGNALS"
    assert res["badge"] is False       # W0 renders nothing at all


def test_outgoing_messages_are_never_scored_for_risk():
    res = _node(_records_js(direction="outgoing", body="Send me guaranteed returns") + """
      const ch = CTX.assess({ chat_id:'c1', title:'W1001-VIP Wealth', member_count:400 }, recs, {});
      const v = V.assemble(recs[0], ch, { registration: { state: 'absent' } });
      out({ verdict: v.verdict, badge: v.badge, scored: v.scored });
    """)
    assert res["verdict"] == "W0_NO_SIGNALS"
    assert res["scored"] is False and res["badge"] is False


# --- W2 / W4 / W5 / W6 ------------------------------------------------------ #
def test_w2_carries_the_bl3_disclaimer():
    res = _node(_records_js(body="Guaranteed 30 percent monthly on stock trading") + """
      const ch = CTX.assess({ chat_id:'c1', title:'Signals Room', member_count:400 }, recs, {});
      const v = V.assemble(recs[0], ch, { registration: { state: 'absent', register_as_of: '2026-08-06' } });
      out({ verdict: v.verdict, disclaimers: v.truths.content.disclaimers });
    """)
    assert res["verdict"] in ("W2_UNVERIFIED_ADVISORY", "W1_UNSOLICITED_CONTEXT")
    joined = " ".join(res["disclaimers"])
    assert "not proof of deception" in joined


def test_w4_fires_on_payment_and_w5_speaks_about_the_credential_not_the_person():
    res = _node(_records_js(body="Send 50000 to vipdesk@okaxis") + """
      const ch = CTX.assess({ chat_id:'c1', title:'Wealth Signals', member_count:400 }, recs, {});
      const w4 = V.assemble(recs[0], ch, { registration: {
        state: 'not_applicable', upi: [{ upi_id:'vipdesk@okaxis', in_valid_namespace:false }] } });
      const w5 = V.assemble(recs[0], ch, { registration: { state: 'collision',
        claims: [{ number:'INH000000552', resolved_name:'Real Research Pvt Ltd' }] } });
      out({ w4: w4.verdict, w4_truth: w4.truths.interaction.state,
            w5: w5.verdict, w5_summary: w5.truths.identity.summary });
    """)
    assert res["w4"] == "W4_PAYMENT_SOLICITATION"
    assert res["w4_truth"] == "signals"
    assert res["w5"] == "W5_IDENTITY_MISMATCH"
    # The claim is about the CREDENTIAL. Never an accusation about the person.
    assert "registered to" in res["w5_summary"]
    for word in ("criminal", "fraudster", "scammer", "fake"):
        assert word not in res["w5_summary"].lower()


def test_w6_campaign_linkage_outranks_everything():
    res = _node(_records_js(body="Join our app, send to vipdesk@okaxis") + """
      const ch = CTX.assess({ chat_id:'c1', title:'Wealth Signals', member_count:400 }, recs, {});
      const v = V.assemble(recs[0], ch, {
        registration: { state:'collision', claims:[{number:'INH000000552', resolved_name:'X'}] },
        campaign: { shared_entities:['vipdesk@okaxis','INH000000552','profit-signals.top'],
                    prior:{ where:'another chat', seen_at:'2026-07-20' }, within_days: 30 } });
      out({ verdict: v.verdict, fired: v.codes_fired, confidence: v.confidence });
    """)
    assert res["verdict"] == "W6_CAMPAIGN_LINKED"
    assert "W5_IDENTITY_MISMATCH" in res["fired"]     # all fired codes still render
    assert res["confidence"] == "high"


def test_escalation_ladder_detected_across_messages():
    res = _node("""
      const mk = (i, amt) => ({ message_id:'m'+i, chat_id:'c1', direction:'incoming',
        timestamp:'2026-07-0'+(i+1)+'T10:00:00',
        sender:{display_name:'Desk', is_contact:false}, body_text:'Pay Rs '+amt,
        body_sha256:'h'+i, entities: EX.extractEntities('Pay Rs '+amt),
        flags:{is_system:false,is_forwarded:false,forwarded_many_times:false,
               has_media:false,media_kind:null,is_reply:false,is_deleted:false} });
      const recs = [mk(0,5000), mk(1,25000), mk(2,80000), mk(3,150000)];
      const ch = CTX.assess({ chat_id:'c1', title:'Profit Desk', member_count:200 }, recs, {});
      out({ ladder: ch.detail.escalation_ladder, has: ch.signals.indexOf('escalation_ladder') !== -1 });
    """)
    assert res["ladder"]["monotonically_rising"] is True
    assert res["has"] is True


# --- privacy contract ------------------------------------------------------- #
def test_body_text_is_never_marked_persistable_for_view_once():
    res = _node("""
      const rec = { message_id:'m1', chat_id:'c1', direction:'incoming', timestamp:null,
        sender:{display_name:'X', is_contact:false}, body_text:'secret', body_sha256:'abc',
        entities: EX.extractEntities('secret'), persist: false,
        flags:{is_system:false,is_forwarded:false,forwarded_many_times:false,has_media:true,
               media_kind:'image',is_reply:false,is_deleted:false,view_once_unscannable:true} };
      const v = V.assemble(rec, {signals:[],detail:{}}, {});
      out({ persist: v.persist, unscannable: v.unscannable });
    """)
    assert res["persist"]["allowed"] is False
    assert res["persist"]["body_sha256"] == "abc"
    assert "body_text" not in res["persist"]          # hashes and codes only
    assert "view_once_not_opened" in res["unscannable"]


def test_selectors_contain_no_class_name_selectors():
    src = (EXT / "whatsapp" / "selectors.js").read_text(encoding="utf-8")
    import re
    # A CSS class selector inside a querySelector string, e.g. ".x3f9" - the
    # hashed-class pattern this registry exists to avoid. `[class*=...]` is an
    # attribute match and is permitted as a tier-2 fallback.
    bad = re.findall(r"querySelector(?:All)?\(\s*['\"][^'\"]*(?<![\w\]])\.[a-zA-Z_-]", src)
    assert not bad, f"class-name selector found in the registry: {bad}"


def test_selector_fixtures_are_absent_and_that_is_reported():
    """
    The DOM half of this lane is UNVERIFIED and must stay visibly so.

    When real captures land in eval/fixtures/whatsapp/, this test flips to
    asserting they parse. Until then it exists to stop the absence being quietly
    forgotten - which is exactly how 'built but never verified' becomes 'assumed
    working'.
    """
    if not WA_FIXTURES.exists() or not list(WA_FIXTURES.glob("*.html")):
        print("NOTE: eval/fixtures/whatsapp/*.html absent — selector resolution "
              "against real WhatsApp DOM is UNVERIFIED. Capture per Part B1.")
        return
    import subprocess as sp
    r = sp.run(["node", str(ROOT / "eval" / "whatsapp_harness.js")],
               capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"whatsapp harness failed against real fixtures:\n{r.stdout[-2000:]}"


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items()) if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}"); passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
