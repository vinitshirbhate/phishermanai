"""
Guard against code that is built, tested, and never loaded.

WHY THIS EXISTS: extension/preflight/* was written, exercised by a Node harness,
and passed every test while being completely unreachable in the actual
extension - background.js imported only securities_check.js and ml_scorer.js.
Every green check was true and none of it meant the code ran. That was caught by
hand. The next orphan will not announce itself, so it is pinned here.

Two things are asserted:

  1. REACHABILITY - every .js under extension/ is referenced from a real entry
     point (importScripts, manifest content_scripts, or a <script src> in
     sidepanel/options HTML), or is on ALLOWED_ORPHANS with a written reason.

  2. THE UMD FALLBACK BRANCH - these modules resolve dependencies through
     `require` under Node and through the global `self` in the service worker.
     The Node harness only ever exercises the first branch. The second is what
     actually ships, so it is executed here in a bare `vm` context with `require`
     undefined, in the same order background.js imports them.

Standalone:  python tests/test_module_reachability.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extension"
BACKGROUND = EXT / "background.js"
MANIFEST = EXT / "manifest.json"

# Files that are legitimately not loaded by the extension. Every entry needs a
# reason. Harness-only modules belong here; nothing else should.
ALLOWED_ORPHANS = {
    "content_script.js": "injected via manifest content_scripts; asserted separately below",
}


def _js_files() -> list[Path]:
    return sorted(p for p in EXT.rglob("*.js")
                  if ".cache" not in p.parts and "node_modules" not in p.parts)


def _import_scripts_targets() -> set[str]:
    """Every path inside importScripts(...) in background.js, multi-line safe."""
    src = BACKGROUND.read_text(encoding="utf-8")
    out: set[str] = set()
    for call in re.findall(r"importScripts\s*\((.*?)\)", src, re.S):
        out.update(re.findall(r"['\"]([^'\"]+\.js)['\"]", call))
    return out


def _manifest_targets() -> set[str]:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out: set[str] = set()
    bg = m.get("background") or {}
    if bg.get("service_worker"):
        out.add(bg["service_worker"])
    for cs in m.get("content_scripts", []) or []:
        out.update(cs.get("js", []) or [])
    for war in m.get("web_accessible_resources", []) or []:
        for r in (war.get("resources", []) if isinstance(war, dict) else [war]):
            if str(r).endswith(".js"):
                out.add(str(r))
    return out


def _html_script_targets() -> set[str]:
    out: set[str] = set()
    for html in EXT.rglob("*.html"):
        src = html.read_text(encoding="utf-8", errors="replace")
        for ref in re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", src, re.I):
            if not ref.endswith(".js"):
                continue
            resolved = (html.parent / ref).resolve()
            try:
                out.add(resolved.relative_to(EXT).as_posix())
            except ValueError:
                out.add(ref)
    return out


def reachable_set() -> set[str]:
    """Entry-point-referenced paths, normalised to be relative to extension/."""
    raw = _import_scripts_targets() | _manifest_targets() | _html_script_targets()
    out: set[str] = set()
    for r in raw:
        r = r.lstrip("./")
        out.add(r)
        out.add(Path(r).name)          # importScripts paths are worker-relative
    return out


def test_every_extension_module_is_reachable():
    reachable = reachable_set()
    orphans = []
    for f in _js_files():
        rel = f.relative_to(EXT).as_posix()
        if rel in reachable or f.name in reachable or rel in ALLOWED_ORPHANS:
            continue
        orphans.append(rel)
    assert not orphans, (
        "module built but never loaded: " + ", ".join(orphans)
        + "\n  Not referenced by importScripts() in background.js, by a manifest "
          "content_scripts entry, or by a <script src> in sidepanel/ or options/. "
          "Either load it or add it to ALLOWED_ORPHANS with a reason."
    )


def test_allowed_orphans_all_have_a_reason_and_still_exist():
    for name, reason in ALLOWED_ORPHANS.items():
        assert reason.strip(), f"ALLOWED_ORPHANS['{name}'] needs a written reason"
        assert list(EXT.rglob(name)), f"ALLOWED_ORPHANS['{name}'] no longer exists — remove it"


def test_orphan_detection_actually_fires():
    """The guard must fail on a real orphan, not just pass vacuously.

    Verifies against a synthetic path rather than writing a file into the tree:
    a genuinely unreferenced module must not appear in the reachable set.
    """
    reachable = reachable_set()
    fake = "preflight/deliberately_orphaned_probe.js"
    assert fake not in reachable and Path(fake).name not in reachable, \
        "reachability check is vacuous — an unreferenced path was reported reachable"


def test_umd_fallback_branch_loads_in_a_service_worker_context():
    """
    Execute the importScripts() order in a bare vm context with `require` and
    `module` undefined, so the `root.PhishermanX` branch - the one that actually
    ships - is the branch under test. The Node harness never reaches it.
    """
    order = [t for t in _import_scripts_targets()]
    # Preserve background.js's declared order; dependencies load first.
    src = BACKGROUND.read_text(encoding="utf-8")
    order.sort(key=lambda t: src.index(t))
    assert order, "no importScripts() targets found in background.js"

    script = """
    const fs = require('fs'), path = require('path'), vm = require('vm');
    const EXT = process.argv[1], ORDER = JSON.parse(process.argv[2]);
    const sandbox = { console, URL, URLSearchParams, Math, JSON, Date, Map, Set, RegExp,
                      TextEncoder, TextDecoder };
    sandbox.self = sandbox; sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    for (const f of ORDER) {
      vm.runInContext(fs.readFileSync(path.join(EXT, f), 'utf8'), sandbox, { filename: f });
    }
    const globals = Object.keys(sandbox).filter(k => k.startsWith('Phisherman'));
    // Exercise the pipeline through the globals, as the worker would.
    sandbox.PhishermanSecurities.load(JSON.parse(
      fs.readFileSync(path.join(EXT, 'data/securities_snapshot.json'), 'utf8')));
    const parsed = sandbox.PhishermanUrlParse.parse('https://zerodha.com/products/kite', {});
    const ident = sandbox.PhishermanPreflightIdentity.resolve(parsed, {});
    const v = sandbox.PhishermanPreflightVerdict.assemble(parsed, ident, {});
    console.log(JSON.stringify({ globals: globals, verdict: v.verdict }));
    """
    out = subprocess.run(["node", "-e", script, str(EXT), json.dumps(order)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, (
        "UMD fallback branch failed to load in a service-worker context "
        "(require undefined). This is what ships.\n" + out.stderr[:800])
    res = json.loads(out.stdout.strip().splitlines()[-1])
    for expected in ("PhishermanNormalise", "PhishermanPSL", "PhishermanSecurities",
                     "PhishermanUrlParse", "PhishermanPreflightIdentity",
                     "PhishermanPreflightVerdict"):
        assert expected in res["globals"], \
            f"{expected} not registered on the worker global — UMD fallback is broken"
    assert res["verdict"] == "L0_NO_SIGNALS", \
        f"pipeline misbehaved under the worker branch: {res['verdict']}"


def test_importscripts_order_puts_dependencies_first():
    """UMD fallback resolves from the global, so a module loaded before its
    dependency silently binds `undefined` and fails at call time, not load time."""
    order = list(_import_scripts_targets())
    src = BACKGROUND.read_text(encoding="utf-8")
    order.sort(key=lambda t: src.index(t))
    pos = {t: i for i, t in enumerate(order)}
    deps = {
        "preflight/url_parse.js": ["shared/normalise.js", "preflight/psl.js"],
        "preflight/identity.js": ["securities_check.js"],
    }
    for mod, needs in deps.items():
        if mod not in pos:
            continue
        for dep in needs:
            assert dep in pos, f"{mod} needs {dep}, which is not imported at all"
            assert pos[dep] < pos[mod], \
                f"{dep} must be imported before {mod} (UMD fallback resolves from the global)"


def test_content_script_bundles_load_dependencies_first():
    """Content scripts execute in array order and share one global, so the same
    UMD-fallback ordering hazard applies here as to importScripts()."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    deps = {
        "whatsapp/health.js": ["whatsapp/selectors.js"],
        "whatsapp/extract.js": ["whatsapp/selectors.js", "shared/normalise.js"],
        "whatsapp/context.js": ["shared/normalise.js"],
    }
    for cs in m.get("content_scripts", []) or []:
        files = cs.get("js", []) or []
        pos = {f: i for i, f in enumerate(files)}
        for mod, needs in deps.items():
            if mod not in pos:
                continue
            for dep in needs:
                assert dep in pos, f"{mod} needs {dep} in the same content_scripts bundle"
                assert pos[dep] < pos[mod], \
                    f"{dep} must be listed before {mod} (shared global, array order)"


def test_declared_entry_points_are_invoked():
    """
    File-level reachability is not enough. preflight/adapter_mv3.js was imported
    by background.js - so the guard above was green - while `initBackground()`,
    its only entry point, had NO CALLER anywhere. Triggers T1-T7 loaded and never
    ran: the hover path in the page showed a bare hostname and the whole preflight
    lane was inert in the shipped extension.

    A module that exports an initialiser must have it called, or the module is
    decoration. Mapping: exported entry point -> files allowed to invoke it.
    """
    entry_points = {
        "initBackground": ["background.js"],
    }
    # Entry points that are knowingly NOT invoked. Same contract as
    # ALLOWED_ORPHANS: the gap is recorded here, in the open, rather than the
    # guard being loosened until it stops noticing.
    known_uninvoked = {
        "initContent":
            "preflight/adapter_mv3.js exports it for triggers T1-T3/T5. T1 (hover) "
            "is served instead by the hover card in content_script.js, which calls "
            "the 'preflightLink' message handler. T2/T3 are click interstitials and "
            "T5 is message-link context; wiring those changes click behaviour on "
            "every page, so they are left unwired pending an explicit decision.",
    }
    for name, reason in known_uninvoked.items():
        assert reason.strip(), f"known_uninvoked['{name}'] needs a written reason"
    sources = {}
    for f in _js_files():
        sources[f.relative_to(EXT).as_posix()] = f.read_text(encoding="utf-8")

    for name, callers in entry_points.items():
        # Only require a call if something actually exports this entry point.
        exporters = [rel for rel, src in sources.items()
                     if re.search(rf"\b{name}\s*:\s*{name}\b", src)
                     or re.search(rf"\bfunction\s+{name}\s*\(", src)]
        if not exporters:
            continue
        called = False
        for rel, src in sources.items():
            code = "\n".join(l for l in src.splitlines()
                             if not l.lstrip().startswith(("//", "*", "/*")))
            # A call, not the definition.
            for m in re.finditer(rf"\b{name}\s*\(", code):
                line_start = code.rfind("\n", 0, m.start()) + 1
                if re.match(r"\s*function\b", code[line_start:m.start()]):
                    continue
                if rel in callers or any(rel.endswith(c) for c in callers):
                    called = True
                    break
            if called:
                break
        assert called, (
            f"{name}() is exported by {exporters} but never invoked. "
            f"The module loads and does nothing — importScripts alone does not "
            f"make a lane run.")


def test_preflight_pipeline_is_reachable_from_a_message_handler():
    """The hover path must actually be able to ask for an analysis."""
    bg = BACKGROUND.read_text(encoding="utf-8")
    assert "'preflightLink'" in bg, "no preflightLink message handler in background.js"
    assert "PhishermanUrlParse.parse" in bg and "PhishermanPreflightVerdict.assemble" in bg, \
        "background.js never runs the preflight pipeline it imports"
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert "preflightLink" in cs, "content_script never requests a link preflight"


def test_whatsapp_modules_declare_no_chrome_api_outside_the_adapter():
    """Same architecture rule as preflight/: pure modules stay harness-runnable."""
    offenders = []
    for f in (EXT / "whatsapp").glob("*.js"):
        if f.name == "adapter_mv3.js":
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//")[0].split("*")[0]
            if re.search(r"\bchrome\s*\.", code):
                offenders.append(f"{f.name}:{i}")
    assert not offenders, "chrome.* outside whatsapp/adapter_mv3.js: " + ", ".join(offenders)


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
