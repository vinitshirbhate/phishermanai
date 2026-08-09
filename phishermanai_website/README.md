# PhishermanAI — website

Marketing and demo frontend for PhishermanAI, built to SEBI Problem Statement 1.
Next.js 16 (App Router) · TypeScript · Tailwind v4 · shadcn/ui (radix base).

```bash
npm run dev     # http://localhost:3000
npm run build   # static prerender of all 12 routes
npm run lint
```

## The argument the site makes

The problem statement names two dimensions, and the site gives them equal weight:

1. **Detection** of AI-generated threats across email, voice, video, social and the web.
2. **Verification** that a communication really is from SEBI, an exchange, a listed
   company or a registered intermediary — a positive confirmation, not merely the
   absence of a flag.

Every channel page states the same four things the problem statement asks for: its
**target users**, the **channels addressed**, its **evidence of performance**, and the
state it is honestly in. No channel is presented as the flagship.

## Routes

| Route                    | What it is                                                                    |
| ------------------------ | ----------------------------------------------------------------------------- |
| `/`                      | Landing — threat landscape, the two halves, all five channels, target users   |
| `/product/email`         | 01 · Email & messaging — the pipeline, tamper detection, direction rules      |
| `/product/voice`         | 02 · Voice — and the two capabilities removed rather than left looking useful |
| `/product/video`         | 03 · Video — frame analysis and the generalisation problem                    |
| `/product/social`        | 04 · Social & coordination — why it stayed an explainable heuristic           |
| `/product/extension`     | 05 · Browser extension — four lanes, install, targets met and missed          |
| `/product/authenticity`  | The verification half — six layers, and the standards gap                      |
| `/how-it-works`          | Routing across channels, fusion, the messaging pipeline, freshness guards     |
| `/features`              | Everything, channel by channel, plus the shared mechanics                     |
| `/evidence`              | Metrics, the ablation, the failing numbers, every limitation                  |
| `/demo`                  | Interactive console — four fixtures + in-browser rule preview                 |

Fixtures are deep-linkable, matching the engine's own web UI:
`/demo?demo=tampered_01.eml`.

## Design system

Defined once in [src/app/globals.css](src/app/globals.css), from
[docs/schema.md](docs/schema.md):

- **Cream `#f6ede4` · navy `#0b1530` · burnt orange `#e6500f`.** Sections alternate
  cream → navy → cream. A navy band carries the `.dark` class, which flips every
  shadcn token so primitives nested inside it invert without per-component overrides.
- **Inter** headings (500), **Source Serif 4** body copy, **Instrument Serif italic**
  for eyebrow labels and accent phrases, **JetBrains Mono** inside the dark technical
  graphics.
- Utilities: `.eyebrow`, `.copy`, `.copy-lg`, `.h-display`, `.h-section`, `.h-accent`,
  `.mono-label`, `.container-page`, `.grid-lines`, `.dashed-rule`.
- Verdict colours are indirected through `--verdict-*` so navy bands can lift them for
  contrast without changing what each colour means.

## Where the content lives

| File                                                 | Contents                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------- |
| [src/lib/content.ts](src/lib/content.ts)             | Channels, auth layers, target users, threat vectors, metrics        |
| [src/lib/analysis.ts](src/lib/analysis.ts)           | Verdict contract, pipeline stages, the four demo fixtures           |
| [src/lib/preview-rules.ts](src/lib/preview-rules.ts) | The in-browser rule subset                                          |
| [src/lib/site.ts](src/lib/site.ts)                   | Navigation, derived from the channel list                           |

Copy is data, not JSX. Adding a channel to `channels` puts it in the nav, the hero
strip, the landing grid, the carousel and the features page at once. Each channel page
is a thin wrapper over
[src/components/product/channel-page.tsx](src/components/product/channel-page.tsx) plus
its own bespoke sections.

## Two things that are deliberately not real

Both are labelled as such in the UI, because a site about provenance should not
overclaim:

1. **Fixture verdicts are recorded**, not computed. They are held in the same shape
   `POST /api/v1/verify` returns, so swapping them for a live call changes where the
   object comes from, not what the UI reads. Live scoring is a backend integration and
   is not wired up.
2. **The browser preview is a rule subset.** It runs the direction-aware claim and
   money rules in the tab and uploads nothing. It cannot prove a sender or reach the
   filings corpus, so it returns only `FRAUDULENT` or `NO_RISK_FOUND` — the two
   verdicts reachable without either — and says so on screen.

The preview enforces the same shape rule the Python engine does: a rule that declares
no action may not exceed severity 1, asserted at module load.

## Source specs

In [docs/](docs/), moved there so `create-next-app` could scaffold at the repo root:
`securitites.md` (engine), `extension.md` (Chrome extension), `ai_prop.md` (APIF
intelligence), `deep-research-report.md` (threat landscape and stakeholders),
`schema.md` (design system).
