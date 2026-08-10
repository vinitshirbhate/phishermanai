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

## Two things that are deliberately not real

Both say so on screen:

1. **Demo fixtures are recorded, not computed.** They're shaped exactly like what
   `POST /api/v1/verify` returns, so swapping in a live call changes where the data
   comes from, not what the UI reads.
2. **The in-browser rule preview is a subset.** It runs the claim/money rules locally
   and uploads nothing, so it can only ever land on `FRAUDULENT` or `NO_RISK_FOUND` —
   it can't prove a sender or check a filing, and it says so.
