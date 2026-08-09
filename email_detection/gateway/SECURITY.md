# Gateway security controls

## This build is NOT hardened for public internet exposure

Read this first. The gateway is a **receiving SMTP server**. Exposing one to the
internet carelessly gets you abused as an open relay, blacklisted, or used to
deliver mail in someone else's name.

This build has **no TLS, no SMTP AUTH, no spam filtering, no greylisting, no
DNSBL checks, and no connection throttling beyond a simple per-IP counter**. It
is built to sit behind an existing mail server on a trusted network, or to run
on loopback for a demonstration. Do not put it on a public IP and walk away.

## Controls that are implemented

| Control | Default | Where |
|---|---|---|
| Loopback binding | `127.0.0.1` | `config.yaml: host` |
| Non-privileged port | `1025` (never 25) | `config.yaml: port` |
| Recipient allowlist | required, empty = deny all | `config.recipient_allowed()` |
| Message size cap | 25 MB → `552` | `smtp_server.handle_DATA` |
| Per-IP rate limit | 100/min → `421` | `smtp_server.RateLimiter` |
| Forged-header stripping | always | `stamping.strip_verdict_headers()` |
| Body never logged | always | `smtp_server.handle_DATA` |
| Body never stored | always | `store.record()` |

### Recipient allowlist — the open-relay defence

`RCPT TO` for an address not on the allowlist is rejected with **550**. Without
this, anyone could connect and have the gateway relay mail to any address on the
internet, and the abuse would be attributed to your host.

An **empty allowlist denies everything**. This is the one place the gateway
fails *closed*, deliberately: the failure mode of an over-permissive allowlist
is third-party abuse, whereas the failure mode of an over-strict one is a
bounce to a sender who can see and report it.

Entries are a full address (`demo@local`) or a domain (`@example.com`).

### Forged verdict headers — a real spoofing vector

Anyone can put `X-PhishermanAI-Verdict: GENUINE` in a message they send. If the
gateway only appended its own header, the delivered message would carry two, and
which one a downstream Gmail filter matches is undefined — so an attacker could
mark their own phishing mail as verified.

Every header beginning with a known verdict prefix is therefore **removed before
ours is written**. Both `X-PhishermanAI-` and the legacy `X-SatyaCheck-` prefix
are stripped regardless of which is configured, so changing `header_prefix`
cannot leave a stale prefix an attacker could forge into. The attempt is
recorded in `X-PhishermanAI-Stripped` rather than being discarded silently.

Tested by `TestForgedHeaders` in `tests/test_gateway.py`.

## The failure policy: never fail closed

Verification failure **never** stops delivery. Engine down, engine timeout,
engine returning nonsense, message unparseable — the message is delivered,
marked `UNVERIFIED`, with `X-PhishermanAI-Error` explaining why.

This is a deliberate security decision, not laziness. A mail gateway that
quarantines or drops messages when its scanner is unhappy loses real mail, and
an operator who loses real mail switches the gateway off — at which point it
protects nobody. An honestly-labelled unverified message is strictly better.

The only refusals are abuse controls (550 / 552 / 421), and all three happen at
`RCPT`/`DATA` time, so the sending server retries or reports a bounce. Nothing
is silently swallowed.

Tested by `TestNeverFailClosed`, which is the group to keep green.

## Privacy

Stored per message: Message-ID, envelope From/To, the original subject, the
verdict, confidence, reason codes and latency. **The body is never written to
disk or to the database**, and never appears in a log line.

The subject is retained because the gateway rewrites it, and an operator needs
the original to explain to a recipient what they are looking at.

## Before exposing this publicly

At minimum you would need:

1. **STARTTLS** with a real certificate (`aiosmtpd` supports `tls_context`).
2. **SMTP AUTH**, or IP-restricted access from your own MTA only.
3. A real MTA in front (Postfix/Exim) doing spam, DNSBL and rate control, with
   this gateway as a downstream content filter rather than the edge listener.
4. Per-connection and per-sender limits well beyond the simple counter here.
5. Monitoring on the `451` relay-failure path.

The intended production shape is **behind** an existing mail server, not in
front of one:

```
internet -> Postfix (TLS, auth, spam) -> PhishermanAI gateway -> mailbox store
```

## Reporting

This is hackathon software. It has not had a security review or a penetration
test, and the threat model above is the author's own. Treat findings
accordingly.
