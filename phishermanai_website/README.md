# PhishermanAI — website

The marketing + demo site for PhishermanAI
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


