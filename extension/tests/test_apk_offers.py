"""
APK offer analysis - shared/apk_check.js and its wiring into the WhatsApp lane.

The case that motivated this: a WhatsApp file bubble reading

    Spotify v9.1.36.1948 (Premium) Mod2.apk        APK - 129 MB

was invisible to every existing check. `.apk` was matched only in message TEXT
and in link paths; a document attachment carries neither. The filename is on the
attachment node and had to be read from there.

Two properties are asserted throughout:

  * modded and fake-broker packages are flagged, with the specific claim named;
  * ordinary files are not, and nothing anywhere calls a package "malware" -
    nothing in this lane opens or inspects the package, so that claim is not
    ours to make (BL-1, BL-4).

Standalone:  python tests/test_apk_offers.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"


def _node(script: str):
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         cwd=str(ROOT), timeout=60)
    assert out.returncode == 0, out.stderr[:1000]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _inspect(filename: str, source: str = "chat"):
    return _node(
        "const A=require('./extension/shared/apk_check.js');"
        f"console.log(JSON.stringify(A.inspect({{filename:{json.dumps(filename)},"
        f"source:{json.dumps(source)}}})));")


# ------------------------------------------------------------ the real file --

def test_the_screenshot_file_is_flagged_high():
    r = _inspect("Spotify v9.1.36.1948 (Premium) Mod2.apk")
    assert r["is_apk"] is True
    assert r["severity"] == "high"
    assert set(r["claims"]) >= {"Mod", "Premium"}, r["claims"]
    assert r["brand"] == "spotify"
    labels = " | ".join(s["label"] for s in r["signals"])
    assert "outside an app store" in labels
    assert "unlocked for free" in labels


def test_separator_styles_do_not_hide_the_claim():
    """
    `_` is a word character, so \\bunlocked\\b never matched "Pro_Unlocked" and
    \\bmod\\b never matched "..._money_mod.apk" - i.e. every marker failed on
    exactly the naming style modded builds use. Guard the flattening.
    """
    for name, expect in [
        ("Zerodha_Kite_Pro_Unlocked.apk", "Unlocked"),
        ("BGMI_90_unlimited_money_mod.apk", "Mod"),
        ("Netflix-Premium-Cracked.apk", "Cracked"),
        ("canva.pro.unlocked.apk", "Pro unlocked"),
    ]:
        r = _inspect(name)
        assert expect in r["claims"], f"{name}: {expect!r} not in {r['claims']}"


# ------------------------------------------------- the securities-fraud case --

def test_fake_broker_apks_are_top_severity():
    for name in ["Zerodha_Kite_Pro_Unlocked.apk", "Groww Premium Mod.apk",
                 "AngelOne-trading-mod.apk", "Upstox_Pro.apk"]:
        r = _inspect(name)
        assert r["severity"] == "high", name
        assert r["evidence"]["financial_brand"], f"{name}: financial brand not recognised"
        labels = " ".join(s["label"] for s in r["signals"])
        assert "financial or trading brand" in labels, name


def test_financial_apk_explanation_names_the_real_consequence():
    r = _inspect("Groww Premium Mod.apk")
    text = _node(
        "const A=require('./extension/shared/apk_check.js');"
        f"console.log(JSON.stringify(A.explain(A.inspect({{filename:'Groww Premium Mod.apk',source:'chat'}}))));")
    assert "not real" in text or "are not real" in text, text
    assert "unknown-sources" in text or "unknown sources" in text, text
    assert r["severity"] == "high"


def test_disguised_extension_is_caught():
    r = _inspect("Payment_Receipt.pdf.apk")
    assert r["severity"] == "high"
    assert r["evidence"]["disguised_extension"] is True
    assert any("shaped like a document" in s["label"] for s in r["signals"])


# ------------------------------------------------------------ false positives --

def test_ordinary_files_are_not_apk_offers():
    for name in ["Statement_July.pdf", "resume.docx", "photo.jpg",
                 "Q3_results.xlsx", "notes.txt"]:
        r = _inspect(name)
        assert r["is_apk"] is False, f"{name} was treated as an Android package"
        assert r["signals"] == []


def test_a_plain_unbranded_apk_is_noted_but_not_top_severity():
    """A developer sharing their own build is not the same as a fake broker."""
    r = _inspect("MyCompanyApp-release.apk")
    assert r["is_apk"] is True
    assert r["severity"] == "medium", "an unbranded APK must not score like a fake broker"
    assert r["claims"] == []
    assert r["brand"] is None


def test_an_apk_not_delivered_to_the_user_has_no_delivery_signal():
    r = _inspect("MyCompanyApp-release.apk", source="page")
    assert not any("received outside an app store" in s["label"] for s in r["signals"])


# ------------------------------------------------------------ lane behaviour --

def test_verdict_emits_an_app_offer_code_not_a_payment_claim():
    """
    The APK used to be appended to W4's payment evidence, producing "This message
    asks for money: an Android app distributed outside an app store." It does not
    ask for money; saying the wrong thing teaches the user to discount warnings.
    """
    res = _node("""
      const V = require('./extension/whatsapp/verdict.js');
      const APK = require('./extension/shared/apk_check.js');
      const attachment = { filename: 'Spotify v9.1.36.1948 (Premium) Mod2.apk',
                           size_text: '129 MB', source: 'chat' };
      const rec = {
        message_id: 'm1', direction: 'incoming', timestamp: '2026-08-08T06:33:00Z',
        sender: { display_name: 'Unknown' }, body_text: '',
        entities: {}, attachment: attachment, apk: APK.inspect(attachment),
        flags: {},
      };
      const v = V.assemble(rec, { signals: [], detail: {} }, { registration: {} });
      console.log(JSON.stringify(v));
    """)
    codes = [c["code"] for c in res["codes"]]
    assert "W4_UNSAFE_APP_OFFER" in codes, codes
    assert "W4_PAYMENT_SOLICITATION" not in codes, \
        "an app offer must not be reported as a request for money"
    assert res["badge"] is True, "an APK offer must raise a badge"
    summary = " ".join(c["summary"] for c in res["codes"])
    assert "Mod" in summary and "Premium" in summary, summary


def test_no_lane_calls_a_package_malware():
    """Nothing here inspects the package, so nothing may assert what it contains."""
    banned = re.compile(
        r"(?i)\b(is\s+(a\s+)?(virus|malware|trojan|spyware)|contains\s+malware|"
        r"will\s+steal|infected)\b")
    for path in [EXT / "shared/apk_check.js", EXT / "whatsapp/verdict.js"]:
        src = path.read_text(encoding="utf-8")
        code = "\n".join(
            line for line in src.splitlines()
            if not line.lstrip().startswith(("*", "//", "/*")))
        hit = banned.search(code)
        assert not hit, f"{path.name} asserts package contents: {hit.group(0)!r}"


def test_extract_reads_a_filename_from_an_attachment_node():
    """Guard the wiring, not just the analyser."""
    src = (EXT / "whatsapp/extract.js").read_text(encoding="utf-8")
    assert "APK.readAttachmentFrom" in src and "APK.inspect" in src, \
        "extract.js does not run apk_check over document attachments"


def test_file_bubble_reading_has_exactly_one_definition():
    """
    The message lane and the legacy page lane both read file bubbles. Two copies
    is how the UPI extractor drifted until it accused every email address of
    being a payment handle. The selector literal must live only in apk_check.js.
    """
    owners = []
    for path in EXT.rglob("*.js"):
        src = path.read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines()
                         if not l.lstrip().startswith(("//", "*", "/*")))
        if 'data-icon="document"' in code or "data-icon*=\"document\"" in code:
            owners.append(path.relative_to(EXT).as_posix())
    assert owners == ["shared/apk_check.js"], \
        f"file-bubble selectors duplicated outside the shared module: {owners}"


# ------------------------------------------- the panel that reported SAFE 94 --

def test_a_file_bubble_is_not_discarded_for_having_no_message_text():
    """
    extractWhatsAppMessages() skipped any bubble whose .selectable-text was
    shorter than 5 characters. A file bubble has NO .selectable-text at all, so
    an APK attachment was dropped before anything could look at it - the panel
    reported the chat SAFE 94 while the APK sat on screen.
    """
    src = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert "readAttachmentFrom" in src, \
        "the page lane never reads attachments; a file bubble stays invisible to it"
    fn = src[src.index("function extractWhatsAppMessages"):]
    fn = fn[:fn.index("\n  function ", 10)]
    assert "if (!attachment && (!text || text.length < 5)) return;" in fn, (
        "the text-length guard still drops bubbles that carry an attachment")
    assert "attachments," in fn, "attachments are not returned from the extractor"


def test_snapshot_and_background_carry_attachments_through():
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    assert "attachments:" in cs, "buildSnapshot does not carry attachments"
    assert "applyAttachmentSignals" in bg, "background never analyses attachments"
    fn = bg[bg.index("function applyAttachmentSignals"):]
    fn = fn[:fn.index("\nasync function")]
    assert "Math.min(assessment.trustScore" in fn, \
        "attachment findings must FLOOR the score, never raise it"
    assert "PhishermanApkCheck.inspect" in fn


def test_apk_analysis_does_not_depend_on_the_backend():
    """
    C5: the product works offline. An APK offer is the case where the user is
    least likely to have a backend and most likely to act, so the merge must sit
    outside every backend-conditional branch.
    """
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    # The CALL, not the definition - `.index()` would find `function apply...`.
    call = bg.index("applyAttachmentSignals(assessment, snapshot);")
    prefix = bg[bg.rindex("\n", 0, call) + 1:call].strip()
    assert prefix == "", f"applyAttachmentSignals is guarded by: {prefix!r}"

    # Behavioural, not textual: lift the real function out of background.js and
    # run it against a local-gate-only assessment. If it merges nothing when the
    # backend is absent, an APK offer goes unreported exactly when it matters.
    src = bg[bg.index("function applyAttachmentSignals"):]
    src = src[:src.index("\nasync function")]
    res = _node("""
      const APK = require('./extension/shared/apk_check.js');
      globalThis.PhishermanApkCheck = APK;
      %s
      const assessment = { trustScore: 94, riskLevel: 'SAFE',
                           signals: ['[behaviour] Artificial time pressure'],
                           source: 'local-gate', backendOnline: false };
      applyAttachmentSignals(assessment, { attachments: [
        { filename: 'Spotify v9.1.36.1948 (Premium) Mod2.apk', source: 'chat' } ] });
      console.log(JSON.stringify(assessment));
    """ % src)
    assert res["trustScore"] <= 24, (
        f"trust {res['trustScore']} with the backend down — an APK offer must "
        f"still floor the score (C5: the product works offline)")
    assert any("outside an app store" in (s.get("label") or "")
               for s in res["signals"] if isinstance(s, dict)), res["signals"]
    assert res["attachmentFindings"][0]["severity"] == "high"


def test_attachment_findings_never_raise_a_score():
    """Floor only. A benign attachment must not make a bad page look better."""
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    src = bg[bg.index("function applyAttachmentSignals"):]
    src = src[:src.index("\nasync function")]
    res = _node("""
      const APK = require('./extension/shared/apk_check.js');
      globalThis.PhishermanApkCheck = APK;
      %s
      const out = {};
      for (const [name, atts] of Object.entries({
        benign_file: [{ filename: 'Statement_July.pdf', source: 'chat' }],
        none:        [],
      })) {
        const a = { trustScore: 12, riskLevel: 'DANGER', signals: ['known phishing'] };
        applyAttachmentSignals(a, { attachments: atts });
        out[name] = a.trustScore;
      }
      console.log(JSON.stringify(out));
    """ % src)
    assert res["benign_file"] == 12, "a benign attachment raised a DANGER score"
    assert res["none"] == 12


def test_apk_modules_load_in_the_page_content_script_bundle():
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    worker = (EXT / "background.js").read_text(encoding="utf-8")
    assert "shared/apk_check.js" in worker, \
        "background.js calls PhishermanApkCheck but never importScripts it"
    for bundle in [cs.get("js", []) for cs in manifest.get("content_scripts", [])]:
        for consumer in ("content_script.js", "whatsapp/extract.js"):
            if consumer in bundle:
                assert "shared/apk_check.js" in bundle, \
                    f"{consumer} calls apk_check but it is not in its bundle"
                assert bundle.index("shared/apk_check.js") < bundle.index(consumer), \
                    f"shared/apk_check.js must be listed before {consumer}"


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}"); passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
