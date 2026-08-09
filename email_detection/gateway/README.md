# PhishermanAI SMTP gateway

Verify financial email **at delivery time**, with no action from the recipient.

```
sender ──▶ [PhishermanAI gateway] ──▶ verify ──▶ stamp headers ──▶ relay ──▶ mailbox
```

This is a **receiving** SMTP server, not a client. Mail is delivered to it, it
verifies the message against SEBI registrations and exchange filings, writes the
verdict into headers, and hands the message onward unchanged otherwise.

## Why a gateway

The web UI and the browser extension both require the investor to *suspect
something first*. Most people who lose money never reach that point — the
message looked fine.

A gateway is deployed by a **broker, listed company, RTA or exchange** in front
of the mail they already send or receive, so every message is checked
automatically. That addresses the intermediaries and market infrastructure
institutions named in the problem statement, not just retail investors. It is
also a direct answer to SEBI's July 2026 "Boss Scam" advisory, whose prescribed
remedy is for the recipient to phone the sender and check by hand.

## Quick start

```bash
# 1. the verification engine must be running
uvicorn api.main:app

# 2. start the gateway (separate terminal)
python -m gateway.run

# 3. push the fixtures through it (separate terminal)
python -m gateway.send_fixtures
```

`send_fixtures` starts its own gateway on a free port, so step 2 is not required
for it. Expected output:

```
FIXTURE                             EXPECTED    VERDICT      CONF     ms
genuine_01.eml                      GENUINE     GENUINE        62    189
tampered_01.eml                     TAMPERED    TAMPERED       79    166
fraud_02_guaranteed_returns.eml     FRAUDULENT  FRAUDULENT     61    209
edge_01_unregistered_but_real.eml   UNVERIFIED  UNVERIFIED     12    752
  matched expected verdict : 16/16
  gateway latency          : p50 184 ms | p95 260 ms
```

Everything above runs **offline**. The only network call is to `127.0.0.1:8000`,
and if that is down every message is still delivered, marked `UNVERIFIED`.

## Headers written

| Header | Example |
|---|---|
| `X-PhishermanAI-Verdict` | `TAMPERED` |
| `X-PhishermanAI-Confidence` | `79` |
| `X-PhishermanAI-Reasons` | `TAMPERED_FIELD;PAYMENT_INSTRUCTION_NOT_IN_FILING` |
| `X-PhishermanAI-Checks` | `MONEY=fail;ENTITY=pass;CLAIM=pass;DELIVERY=na` |
| `X-PhishermanAI-Filing` | `id=2541 BSE 2026-07-09 tier=STRUCTURED` |
| `X-PhishermanAI-Id` | `777` — look up via `GET /gateway/messages/{id}` |
| `X-PhishermanAI-Version` | `1.0` |
| `X-PhishermanAI-Error` | set only when verification could not run |
| `X-PhishermanAI-Stripped` | set only when forged verdict headers were removed |

> **Header prefix.** The Phase 7 brief specified `X-SatyaCheck-*`; this build
> uses `X-PhishermanAI-*` to match the project's current name. Change
> `header_prefix` in `config.yaml` to switch — every header, filter and doc
> follows that one value. Both prefixes are always *stripped* from inbound mail
> regardless of the setting, so the change cannot open a spoofing gap.

### Subject tagging

Prepended when the verdict is not `GENUINE` (`subject_tagging: true`):

| Verdict | Tag |
|---|---|
| `FRAUDULENT` | `[!! FRAUD] ` |
| `TAMPERED` | `[!! ALTERED] ` |
| `UNVERIFIED` | `[? UNVERIFIED] ` |
| `GENUINE` | *(none — normal mail stays uncluttered)* |

RFC 2047 encoded subjects are decoded, tagged, and re-encoded, so a Devanagari
or emoji subject survives intact.

## Getting real mail into the gateway

### a) Local only — always works, use this for the demo

```bash
python -m gateway.send_fixtures
```

No network, no DNS, no external service. **This is the demo path.** Use it.

### b) Gmail auto-forward — live demo

1. Expose the gateway with a TCP tunnel:
   ```bash
   ngrok tcp 1025          # note the host:port it prints
   ```
2. Gmail → **Settings → Forwarding and POP/IMAP → Add a forwarding address**.
3. Gmail sends a confirmation code to that address. It must arrive in your
   Maildir (`gateway/maildir/new/`) — read the code from there and confirm.
4. Add the forwarding address to `recipient_allowlist` in `config.yaml`.

> **This is fragile and must never be your only demo path.** Gmail's forwarding
> confirmation is finicky, ngrok TCP endpoints change on every restart, Gmail
> will not forward to a host with no valid MX in some configurations, and
> venue Wi-Fi may block outbound SMTP entirely. Have (a) ready as the fallback,
> and rehearse (a) even if you intend to show (b).

### c) Your own test domain — most realistic

1. Point an MX record at the host running the gateway:
   ```
   demo.yourdomain.in.   MX  10  gw.yourdomain.in.
   ```
2. Run the gateway on port 25 **behind a real MTA** — read `SECURITY.md` first,
   because this build is not hardened for direct internet exposure.
3. Add `@demo.yourdomain.in` to `recipient_allowlist`.

## Acting on the verdict downstream

The point of writing headers rather than modifying the body is that ordinary
mail clients can route on them.

**Gmail** — Settings → Filters → Create a new filter → *Has the words*:

```
X-PhishermanAI-Verdict:FRAUDULENT
```

→ Apply label "Fraud", Mark as important, **Never send it to Spam** (so the
recipient sees the warning rather than never seeing the message at all).

Repeat with `X-PhishermanAI-Verdict:TAMPERED`.

**Thunderbird** — Tools → Message Filters → New → *Customize…* → add header
`X-PhishermanAI-Verdict` → *is* → `FRAUDULENT` → Move to folder.

**Outlook** — Rules → *Advanced Options* → "specific words in the message
header" → `X-PhishermanAI-Verdict: FRAUDULENT`.

## Configuration

`gateway/config.yaml`, overridable by `PHAI_GW_*` environment variables and by
CLI flags (in that order of precedence).

```yaml
host: "127.0.0.1"          # loopback only; public binding is opt-in
port: 1025                 # never 25
engine_url: "http://127.0.0.1:8000"
engine_timeout: 8.0        # on timeout: DELIVER, marked UNVERIFIED
relay_mode: "maildir"      # maildir | smtp | discard
maildir_path: "gateway/maildir"
header_prefix: "X-PhishermanAI"
subject_tagging: true
max_size_mb: 25            # over this: 552
rate_limit_per_min: 100    # over this: 421
recipient_allowlist:       # not listed: 550. Empty = deny all.
  - "demo@local"
  - "investor@example.com"
```

```bash
python -m gateway.run --port 1025 --relay maildir --allowlist demo@local
PHAI_GW_PORT=2025 python -m gateway.run
```

## Reading results back

```bash
curl http://127.0.0.1:8000/gateway/messages | jq
curl http://127.0.0.1:8000/gateway/messages/'<test-001@example.net>' | jq
```

Deduplicated by RFC `Message-ID`: the same message re-delivered (an SMTP retry,
or a copy to a second allowlisted recipient) reuses the stored verdict instead
of being verified again. Messages with no `Message-ID` get a stable
content-derived one, so retransmissions still deduplicate.

## Measured performance

48 messages (16 fixtures × 3), engine running locally:

| | p50 | p95 | max |
|---|---|---|---|
| Total (SMTP in → relayed) | 168.5 ms | 204.9 ms | 224.6 ms |
| Verification engine | 145.5 ms | 171.6 ms | 183.2 ms |
| **Gateway overhead** | **25.5 ms** | **67.1 ms** | **94.8 ms** |

Requirement was < 500 ms of gateway overhead. Most of the wall time is the
verification itself, which is shared with the web UI and the extension.

## What this reuses

No detection logic lives in `gateway/`. It calls `POST /verify/email` on the
existing engine — the same endpoint the web UI uses — so every chokepoint,
extraction, filings match and scoring rule runs in `core/`. See the top of
`gateway/verify_client.py`.

## Tests

```bash
python -m pytest tests/test_gateway.py -v
```

34 tests. The group that matters most is `TestNeverFailClosed`: engine
unreachable, engine timeout, engine HTTP error, engine returning garbage, and
an unparseable message must all still **deliver** the mail.
