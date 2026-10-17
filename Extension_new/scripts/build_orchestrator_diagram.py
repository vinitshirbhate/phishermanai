"""Write the requested plain Excalidraw element array; no Mermaid or SVG."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sections = [
('1. PRODUCT SURFACES — WHERE USERS START',
 'Chrome extension: website, link and visible-message checks.\nMain Next.js website: product pages and verification workbench.\nFinancial web app: a second, older verification interface.\nSMTP gateway: checks mail while receiving it.\nWHY: different entry points reuse analysis instead of copying rules.\nALTERNATIVE: one website only; simpler, but misses browsing context.\nTRADEOFF: duplicate interfaces increase maintenance and setup confusion.\nEVIDENCE: extension/manifest.json; website/src/lib/engine-client.ts.'),
('2. REQUEST ORCHESTRATOR — CHOOSES WHAT RUNS',
 'Current system has several coordinators, not one master controller.\nExtension background.js routes browser actions and staged scans.\nbackend/main.py composes browser, financial and PDF HTTP routes.\nemail_detection/core/pipeline.py coordinates financial checks.\napif/pipeline.py coordinates independent multimodal detectors.\nWHY: each coordinator owns its input types and evidence contract.\nALTERNATIVE: one central pipeline; easier routing, bigger failure scope.\nTRADEOFF: integrations and score meanings must be made explicit.'),
('3. BROWSER WORKER — EVENT AND STATE COORDINATOR',
 'Service worker = background JavaScript, outside the webpage.\nReceives clicks, scans, hover requests and settings changes.\nReturns local results first; optional server results arrive later.\nGeneration markers stop old results replacing a newer scan.\nWHY: fast feedback and one place to manage request policy.\nALTERNATIVE: wait for server before displaying any result.\nTRADEOFF: staged results need careful cache and navigation handling.\nWorker memory is temporary; saved preferences use local storage.'),
('4. PRIVACY MODES — WHERE INFORMATION GOES',
 'On-device: analysis runs inside the browser without server requests.\nLocal server: browser contacts a loopback address on this computer.\nRemote: configured external server and possible cloud fallback.\nPDF upload and financial verification require explicit confirmation.\nWHY: users choose the processing boundary for their information.\nALTERNATIVE: cloud-only service; less setup, more data transmission.\nTRADEOFF: local setup and CPU cost; remote availability and privacy.\nLoopback limits browser transport, not a server operator\'s behavior.'),
('5. UNIFIED HTTP API — ONE LOCAL ADDRESS',
 'Entry: Extension_new/backend/main.py; public port: 8000.\nHTTP API = agreed URLs and request/response formats.\nBrowser routes: /api/analyze/page, /text, /url and related checks.\nFinancial routes: /verify, /verify/email and entity lookup.\nPDF route: /api/analyze/pdf. Docs: /docs.\nHealth: /health for corpus; /api/health for browser engines.\nWHY: one configured address avoids wrong-service 404 errors.\nTRADEOFF: shared process and dependency/import coupling.\nAPIF is NOT mounted here; its documented 8000 port conflicts.'),
('6. WEBSITE AND LINK CHECKS — BEFORE THE CLICK',
 'Parse URL using the browser-compatible URL parser.\nCompare visible URL text with the actual link destination.\nInspect obfuscation, identity clues, shorteners and threat evidence.\nOptional redirect checks reveal later destinations after opt-in.\nWHY: syntax, identity and known-bad evidence are complementary.\nALTERNATIVE: domain popularity alone; ignores deceptive link text.\nTRADEOFF: no redirect fetch preserves privacy but leaves uncertainty.\nA clean hostname cannot guarantee a safe repository or download.'),
('7. WEBSITE LIST — IDENTITY CONTEXT, NOT A BYPASS',
 'Current bundled list: 969 exact hosts; www aliases supported.\nOfficial directory imports preserve sources and review dates.\nDeveloper hosts are curated; inherited entries still need review.\nNo blanket trust for arbitrary subdomains or shared hosting.\nWHY: recognize normal sites while keeping risky content visible.\nALTERNATIVE: trust all children of a popular host; broader but unsafe.\nTRADEOFF: exact matching needs more records and refresh work.\nRefresh scripts import data; sync_allowlist.py builds browser data.'),
('8. PERSONAL WHITELIST — USER INTERRUPTION PREFERENCE',
 'One question in a 10-second bottom-right popup.\nEligible weak warnings can be remembered for 30 days.\nSeven-day prompt cooldown reduces repeat interruptions.\nPreferences do not raise scores or hide strong findings.\nIncorrect-warning reports remain pending for review.\nWHY: reduce nuisance without allowing silent global trust changes.\nALTERNATIVE: permanent user override; simpler, easier to misuse.\nTRADEOFF: expiry and eligibility add state and explanation needs.'),
('9. FINANCIAL PIPELINE — CHECK THE CLAIM AGAINST RECORDS',
 'Entry: email_detection/core/pipeline.py.\nParse input; inspect source and claimed identity.\nCheck delivery, entity, payment and claim evidence.\nMatch a company filing; compare extracted fields with filed values.\nReturn reasons, available evidence and recommended actions.\nWHY: source authentication alone does not establish claim truth.\nALTERNATIVE: keyword classifier or LLM answer alone.\nTRADEOFF: record coverage, extraction quality and corpus freshness\nlimit what can be established; incomplete evidence stays explicit.'),
('10. PDF CHECKING — DOCUMENT TEXT AND HIDDEN LINK TARGETS',
 'User selects a PDF and confirms full-document upload.\npypdf extracts readable text and embedded HTTP/HTTPS annotations.\nPanel checks text and lists link results with page numbers.\nLimits: 12 MB, 100 pages, 200 links; local text check: first 15k chars.\nWHY: Chrome native PDF viewer is outside normal content injection.\nALTERNATIVE: custom PDF.js viewer; enables document hover overlays.\nTRADEOFF: current upload flow is simpler but requires a server.\nNo OCR, PDF JavaScript or attachment execution; links are not opened.'),
('11. SCAMGATE — OPTIONAL ESCALATION INSIDE THE BACKEND',
 'Tier 0: deterministic patterns; backend default maximum tier is 0.\nTier 1: optional local Ollama model. Tier 2: optional cloud model.\nEscalation must be enabled by backend configuration.\nWHY: cheap, explainable checks before expensive inference.\nALTERNATIVE: use an LLM for every request.\nTRADEOFF: rules need maintenance; models add latency, cost\nand uncertain outputs. Local models require machine resources.\nBrowser privacy mode does not independently audit server inference.'),
('12. APIF — SEPARATE MULTIMODAL FUSION APPLICATION',
 'Entry: apif/main.py; coordination: apif/pipeline.py.\nText classification and entity extraction feed later checks.\nAudio transcription, voice/video, registry and market signals.\nIndependent tasks overlap after their inputs become available.\nFusion = combining available detector evidence into a verdict.\nWHY: several evidence types are stronger than one detector.\nALTERNATIVE: one model handles every modality.\nTRADEOFF: unavailable detectors reduce coverage; weights need\nvalidation. APIF risk scores differ from browser trust scores.'),
('13. DETECTOR DEPENDENCIES — COST AND FAILURE BOUNDARIES',
 'APIF text adapter calls phishing_detection /detect on port 8080.\nLocal transcription requires model files and compute.\nVoice/video and explanation paths have configurable providers.\ndeepfake_detection holds separate reference implementations.\nWHY: adapters isolate provider/model details from orchestration.\nALTERNATIVE: embed every model in one API process.\nTRADEOFF: network dependencies versus heavier startup and memory.\nTimeout/unavailable evidence must not be counted as proof of safety.'),
('14. DATA AND RETENTION — WHAT IS READ OR SAVED',
 'Financial SQLite: entities, filings, rules and derived verifications.\nBrowser backend: reference registries, feeds and review requests.\nExtension storage: settings, history and personal preferences.\nFinancial extension results: temporary service-worker memory.\nAPIF stages uploaded files and has its own persistence layer.\nWHY SQLite: straightforward local deployment without a DB server.\nALTERNATIVE PostgreSQL: better multi-instance operations.\nTRADEOFF: SQLite write contention, backup and container durability.\nRetention is module-specific; do not claim one global policy.'),
('15. DELIVERY AND TESTING — VERIFY BEFORE DISTRIBUTION',
 'Financial deployment: Dockerfile, Compose and Render blueprint.\nThat container does not automatically include unified browser/PDF API.\nPython tests and Node VM harnesses cover bounded code paths.\nContract validation checks permissions and signed metadata.\nWHY: reproducible builds plus explicit behavior checks.\nALTERNATIVE: manual-only demos; quicker initially, hard to reproduce.\nTRADEOFF: mock tests do not prove live Chrome usability or accuracy.\nNo GitHub Actions workflow found; CI automation remains follow-up.'),
('16. ORCHESTRATOR OPERATING RULES — PROPOSED WORKFLOW',
 '1. Inspect relevant code, configuration and current diff.\n2. Identify the owning pipeline and its data/privacy boundary.\n3. Make the smallest change that completes the requested behavior.\n4. Test failure states, normal behavior and misleading reassurance.\n5. Report evidence, limits and deployment steps; stop after 5 cycles.\nWHY: reviewable changes rather than implicit repository-wide rewrites.\nDo not reset user work, rotate secrets or deploy without authorization.\nThis is a maintenance guide, not a newly implemented agent service.'),
('17. TERMINOLOGY — SAME WORDS, CONSISTENT MEANING',
 'Signal: one finding; evidence: what supports that finding.\nVerdict: combined result; coverage: checks actually completed.\nTrust score: browser scale where higher means fewer risk findings.\nRisk score: APIF threat scale; do not interchange score directions.\nEvidence confidence: financial evidence availability, not page safety.\nCache: saved result for reuse; TTL: when that cached result expires.\nLoopback: this computer; adapter: connector to another component.\nCorpus: reference collection; fusion: combines detector results.\nProvenance: where evidence/data came from and when it was gathered.'),
('18. DECISIONS AND GAPS — WHAT SHOULD BE RESOLVED NEXT',
 'Root README still describes an older port/integration arrangement.\nAPIF and unified backend both document port 8000; choose routing\nbefore claiming every repository application uses one server.\nDuplicate websites/extensions need an explicit supported-product path.\nA hardcoded credential exists in fake_propaganda/main.py:\nowner should revoke/rotate it and use environment configuration.\nMeasure representative accuracy, false alarms and live-browser latency.\nAudit inherited website entries and define per-module retention.\nNo deployments or source changes were made by this diagram task.'),
]
review = json.loads((ROOT / 'docs/agentic-security-review.json').read_text(encoding='utf-8'))
title, body = sections[-1]
sections[-1] = (title, body.replace('A hardcoded credential exists in fake_propaganda/main.py:',
    'The prototype literal credential has been removed;').replace('No deployments or source changes were made by this diagram task.',
    'Targeted security fixes made; no deployment or provider revocation.'))
import textwrap
for risk in review['risks']:
    body = f"STATUS: {risk['status']}\n\nCONTROLS: {risk['controls']}\n\nREMAINING: {risk['gaps']}"
    body = '\n'.join(textwrap.fill(line, width=68) if line else '' for line in body.splitlines())
    sections.append((f"{len(sections)+1}. {risk['id']} — {risk['name']}", body))
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--detailed', action='store_true', help='Generate the original extensive review.')
detailed = parser.parse_args().detailed
if not detailed:
    sections = [
        ('USER ENTRY POINTS', 'Chrome extension: websites, links and messages.\nWebsite: verification workbench.\nPDFs: choose a file and confirm upload.\nOlder web app and extension remain separate.'),
        ('ORCHESTRATION — HOW CHECKS RUN', 'Browser worker routes requests and shows local results first.\nUnified backend combines browser, financial and PDF checks.\nAPIF coordinates separate audio/video detector pipelines.\nNo single repository-wide autonomous agent is deployed.'),
        ('ONE LOCAL BACKEND — PORT 8000', 'Entry: Extension_new/backend/main.py\nBrowser: /api/analyze/* | Financial: /verify\nPDF: /api/analyze/pdf | API docs: /docs\nOne address simplifies setup; shared process couples failures.'),
        ('WHAT IS CHECKED', 'Links: destination, misleading labels and threat evidence.\nFinancial claims: identity and matching exchange filings.\nPDFs: readable text and embedded links; no OCR.\nAPIF: separate voice/video analysis with external dependencies.'),
        ('DATA AND PRIVACY', 'On-device: browser analysis only.\nLocal server: this computer; remote mode can send data out.\nPDF and financial submissions require explicit consent.\n969 exact website hosts; listing is not a safety guarantee.\nSQLite is simple locally; scaling needs further work.'),
        ('USER TRUST AND TRADEOFFS', 'Rules are fast; ambiguous cases can need deeper analysis.\nPersonal exceptions expire and keep strong warnings visible.\nUnavailable checks must not appear as proof of safety.\nLocal processing needs setup; remote processing adds privacy cost.'),
        ('SECURITY FIXES AND EXISTING SAFEGUARDS', 'Fixed: literal credential removed; CORS credentials disabled.\nAdded: untrusted-input boundaries in LLM prompts.\nExisting: schemas, consent, timeouts and signed contracts.\nPrompt boundaries and metadata signatures have limited scope.'),
        ('IMPORTANT REMAINING WORK', 'Revoke the exposed credential; add hosted authentication.\nAudit SSRF, dependencies and parser resource isolation.\nAPIF also defaults to 8000: resolve the service conflict.\nAdd CI and measure accuracy, false alarms and usability.\nSecurity review is partial, not compliance certification.'),
        ('OWASP RISKS 01–05 — PARTIAL COVERAGE', 'ASI01 Goal hijack: prompt boundaries; adversarial tests needed.\nASI02 Tool misuse: fixed routes; authorization audit needed.\nASI03 Privilege abuse: credential fix; revocation still needed.\nASI04 Supply chain: contracts; dependency pinning needed.\nASI05 Code execution: no LLM executor; parser isolation needed.'),
        ('OWASP RISKS 06–10 — PARTIAL COVERAGE', 'ASI06 Context poisoning: stale-result guards; corpus audit needed.\nASI07 Agent communication: typed APIs; service identity needed.\nASI08 Cascading failures: limits/timeouts; circuit breakers needed.\nASI09 Over-trust: evidence wording; usability tests needed.\nASI10 Rogue agents: no deployed agent; future controls needed.'),
    ]
elements = [{'type':'text','x':40,'y':20,'width':1340,'height':80,
             'text':'PHISHERMANAI — ORCHESTRATOR OVERVIEW\nComponents, key tradeoffs and security gaps • 2026-10-03\nArrows indicate reading order, not API calls.',
             'strokeColor':'#1e293b','backgroundColor':'transparent'}]
for index, (title, body) in enumerate(sections):
    title = textwrap.fill(title, width=64)
    body = '\n'.join(textwrap.fill(line, width=64) if line else '' for line in body.splitlines())
    x = 40 + (index % 2) * 710
    card_height = 385 if detailed else 235
    y = 140 + (index // 2) * (card_height + 40)
    is_gap = index == (17 if detailed else 7)
    color = '#dc2626' if is_gap else '#2563eb'
    elements.append({'type':'rectangle','x':x,'y':y,'width':670,'height':card_height,
                     'strokeColor':color,'backgroundColor':'#fee2e2' if is_gap else '#eff6ff'})
    elements.append({'type':'text','x':x+18,'y':y+16,'width':634,'height':card_height-35,
                     'text':title+'\n\n'+body,'strokeColor':'#1e293b','backgroundColor':'transparent'})
    if index % 2 == 0:
        elements.append({'type':'arrow','x':x+675,'y':y+150,'width':30,'height':0,
                         'points':[[0,0],[30,0]],'strokeColor':'#64748b','backgroundColor':'transparent'})
# Pasted workflow: show real data-flow arrows, with future controls explicit.
flow_y = 140 + ((len(sections) + 1) // 2) * (card_height + 40) + 70
elements.append({'type':'text','x':40,'y':flow_y,'width':1340,'height':85,
    'text':'SECURE REQUEST FLOW — EVERY ARROW IS A TRUST BOUNDARY\nCurrent checks + proposed policy controls. Detection does not authorize actions.\nBERT integration, crawler isolation and agent audit/kill switch remain proposed here.',
    'strokeColor':'#1e293b','backgroundColor':'transparent'})
flow = [
 ('UNTRUSTED INPUT', 'Webpage · WhatsApp · URL · email · PDF text\nContent is evidence, never an instruction.'),
 ('VALIDATE AND EXTRACT', 'Parse URLs and typed input; enforce document limits.\nProposed: centralized validation and policy checks.'),
 ('LOCAL SECURITY CHECKS', 'Rules · URL features · form destinations · behavior\nReturn initial result; preserve evidence and coverage.'),
 ('OPTIONAL ANALYSIS', 'Backend URL/identity/financial checks by selected mode.\nBERT service is separate; unified crawler is proposed.'),
 ('VERDICT ENGINE', 'Combine available evidence; retain strong findings.\nMissing or failed checks mean UNKNOWN, not safe.'),
 ('POLICY / SAFETY GATE', 'Proposed: deterministic action permissions and approval.\nModel classification does not authorize global blocking.'),
 ('USER RESULT AND DECISION', 'No strong signals · caution · high risk · not checked\nShow reasons and next action; do not guarantee safety.'),
 ('FEEDBACK → REVIEW GATE', 'Existing: local/pending reports; expiring personal exceptions.\nProposed: provenance review before approved knowledge.'),
]
node_y = flow_y + 110
for index, (title, body) in enumerate(flow):
    y = node_y + index * 175
    proposed = index in {5,7}
    elements.append({'type':'rectangle','x':40,'y':y,'width':650,'height':125,
        'strokeColor':'#d97706' if proposed else '#2563eb',
        'backgroundColor':'#fef3c7' if proposed else '#eff6ff'})
    elements.append({'type':'text','x':58,'y':y+16,'width':614,'height':95,
        'text':title+'\n\n'+'\n'.join(textwrap.fill(line,width=63) for line in body.splitlines()),
        'strokeColor':'#1e293b','backgroundColor':'transparent'})
    if index < len(flow)-1:
        elements.append({'type':'arrow','x':365,'y':y+130,'width':0,'height':40,
            'points':[[0,0],[0,40]],'strokeColor':'#dc2626','backgroundColor':'transparent'})
        elements.append({'type':'text','x':382,'y':y+137,'width':230,'height':25,
            'text':f'B{index+1}: validate handoff','strokeColor':'#991b1b','backgroundColor':'transparent'})
controls = [
 ('INSTRUCTIONS ≠ CONTENT — ASI01 / ASI06', 'Current: untrusted-input prompt boundaries and typed output.\nProposed: adversarial tests and authority-claim validation.\nCrawler/OCR output remains untrusted; prompts alone are weak.'),
 ('TOOL PRIVILEGES — ASI02 / ASI03', 'Read/compute: domain, text and local feed checks.\nNetwork crawling needs stricter SSRF and resource controls.\nWrites: incidents/cache need scoped permission.\nGlobal blocks, reports and shared-list edits need approval.'),
 ('SUPPLY AND EXECUTION — ASI04 / ASI05', 'Current: source/date records and signed contract metadata.\nProposed: dependency/model hashes, versions and evaluation.\nCrawler: validate → isolate → restrict → extract → destroy.\nAn isolated Playwright crawler is not verified by this diagram.'),
 ('SERVICE MESSAGES — ASI07 / ASI08', 'Proposed schema: source, request ID, URL, status, signals.\nAuthenticate sender and integrity; reject stale/replayed results.\nCurrent: schemas, timeouts and generation-based invalidation.\nUnavailable detectors reduce coverage, not evidence of risk.'),
 ('TRUST AND OVERSIGHT — ASI09 / ASI10', 'Current: reasons, coverage and limited personal preferences.\nProposed audit: actor/request ID, input hash, tool, policy, time.\nDetect unusual result patterns; add kill switch and review.\nDo not store raw sensitive content merely for audit purposes.'),
 ('APPROVED KNOWLEDGE — REVIEW REQUIRED', 'Feedback is a report, not truth or an instruction.\nProposed: validation → provenance → review → approval.\nPersonal 30-day exceptions never become global safe labels.\nNo automatic learning or shared allowlist promotion implied.'),
]
for index, (title, body) in enumerate(controls):
    y = node_y + index * 230
    elements.append({'type':'rectangle','x':740,'y':y,'width':640,'height':195,
        'strokeColor':'#d97706','backgroundColor':'#fffbeb'})
    elements.append({'type':'text','x':758,'y':y+16,'width':604,'height':165,
        'text':title+'\n\n'+'\n'.join(textwrap.fill(line,width=61) for line in body.splitlines()),
        'strokeColor':'#1e293b','backgroundColor':'transparent'})
output = ROOT / 'docs/orchestrator-repository.excalidraw.json'
output.write_text(json.dumps(elements, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
allowed = {'type','x','y','width','height','text','strokeColor','backgroundColor','points'}
assert all(set(item) <= allowed for item in elements)
assert len(sections) == (28 if detailed else 10)
native = []
for index, item in enumerate(elements):
    node = {**item, 'id':f'orchestrator-{index}', 'angle':0, 'fillStyle':'solid',
            'strokeWidth':1, 'strokeStyle':'solid', 'roughness':0, 'opacity':100,
            'groupIds':[], 'frameId':None, 'roundness':None, 'seed':index+1,
            'version':1, 'versionNonce':index+1, 'isDeleted':False,
            'boundElements':None, 'updated':0, 'link':None, 'locked':False}
    if item['type'] == 'text':
        node.update(fontSize=16,fontFamily=3,textAlign='left',verticalAlign='top',
                    containerId=None,originalText=item['text'],autoResize=False,lineHeight=1.3)
    if item['type'] == 'arrow':
        node.update(startBinding=None,endBinding=None,startArrowhead=None,endArrowhead='arrow',elbowed=False)
    native.append(node)
scene = {'type':'excalidraw','version':2,'source':'https://excalidraw.com',
         'elements':native,'appState':{'viewBackgroundColor':'#ffffff','gridSize':None},'files':{}}
native_path = ROOT / 'docs/orchestrator-repository.excalidraw'
native_path.write_text(json.dumps(scene,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(f'Wrote native .excalidraw and raw array ({len(elements)} elements, {len(sections)} sections)')
