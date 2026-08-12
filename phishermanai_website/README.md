# PhishermanAI — website

The marketing + demo site for PhishermanAI, built for SEBI Problem Statement 1.
Next.js 16 (App Router), TypeScript, Tailwind v4, shadcn/ui.

```bash
npm run dev     # http://localhost:3000
npm run build
npm run lint
```

## What it's making the case for

Two things, weighted equally: **detecting** AI-generated fraud across email, voice,
video, social and the web, and **verifying** that a message really is from SEBI, an
exchange, a listed company, or a registered intermediary. Neither half is the headline.

## Pages

Everything channel-specific now lives on the homepage as anchored, deep-linkable
sections — clicking a channel in the nav jumps you straight there, no separate page
load.

| Route | What's there |
| --- | --- |
| `/` | Hero, the threat landscape, all five channels (deep-dive + auth framework), target users, gates |
| `/how-it-works` | Routing, fusion, the messaging pipeline, data freshness |
| `/features` | Every channel's full capability list in one place |
| `/evidence` | Metrics, the precision ablation, and every stated limitation |
| `/demo` | Four recorded fixtures + an in-browser rule preview |

Old `/product/*` links still work — they redirect to the matching homepage anchor.

## Design

Slate ground, ink-navy text, one vermilion accent used only where it means something
(the primary action, a pass/fail state). Sharp corners everywhere except the floating
pill nav. Archivo for headlines, Inter for everything else, JetBrains Mono for labels.
Tokens live in [src/app/globals.css](src/app/globals.css); motion helpers (`Reveal`,
`RevealGroup`) live in [src/components/site/motion.tsx](src/components/site/motion.tsx).

## Where the content lives

Copy is data, not JSX. [src/lib/content.ts](src/lib/content.ts) holds the channels,
auth layers, evidence and metrics; [src/lib/site.ts](src/lib/site.ts) derives the nav
from it. Add a channel there and it shows up in the nav, the hero strip, the carousel
and `/features` at once.

## Wiring it to the engine

`/demo` talks to the real verification engine in [`../email_detection`](../email_detection).

```bash
# 1. Engine
cd email_detection
pip install -e .
python -m data.load_all          # builds the corpus offline, ~30 s
uvicorn api.main:app --reload    # http://127.0.0.1:8000

# 2. UI
cd phishermanai_website
npm run dev                      # http://localhost:3000/demo
```

The console probes `/health` on load and picks its mode:

| Engine | Fixtures tab | Your-own-text tab |
| ------ | ------------ | ----------------- |
| **running** | `POST /demo/verify/{name}` — the real pipeline over `eval/fixtures` | `POST /verify` |
| **down** | recorded results | in-browser rule subset |

Either way the console says which mode it's in, and shows the live corpus counts
(filings, entities, domains, rules) when connected.

**Requests go through a proxy**, not straight to the engine. The browser calls
`/api/engine/*` and [src/app/api/engine/[...path]/route.ts](src/app/api/engine/\[...path\]/route.ts)
forwards it. The engine's CORS already permits `localhost:3000`, so this isn't
required — it just keeps the engine's address server-side instead of in the client
bundle, and means deploying the UI elsewhere needs no CORS change on the Python side.
Set `PHISHERMANAI_API_URL` to point somewhere other than `127.0.0.1:8000` (see
[.env.example](.env.example)).

### Two things about the contract worth knowing

[src/lib/engine-types.ts](src/lib/engine-types.ts) mirrors `api/schemas.py` field for
field. Two details are easy to get wrong:

1. **The engine's verdict codes are not the display strings.** It returns `GENUINE`,
   `UNVERIFIED`, `TAMPERED`, `FRAUDULENT`, and serves a separate `label` field
   (`VERIFIED`, `NO RISK FOUND`, …) *specifically* so each client doesn't keep its own
   mapping and drift. The UI renders `label`; the code is only used to pick a colour.
2. **`confidence` is 0–100 and means how much evidence was available**, not how bad the
   message is. `genuine_01.eml` scores 95 because DKIM proved the sender;
   `edge_01_unregistered_but_real.eml` scores 12 because there was nothing to see. A low
   number is "I couldn't tell", not "this is fine" — the UI labels it accordingly.

## One thing that is deliberately not real

**The in-browser rule preview is a subset.** With the engine down, pasted text runs the
claim/money rules locally and uploads nothing, so it can only land on `FRAUDULENT` or
`NO_RISK_FOUND` — it can't prove a sender or check a filing, and it says so on screen.
