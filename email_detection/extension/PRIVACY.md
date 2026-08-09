# PhishermanAI browser extension — privacy and platform compliance

This document states exactly what the extension does, why it is built the way
it is, and how it stays inside WhatsApp's rules. It is written to be checked
against the source: every claim below corresponds to code in
`content/content.js`, `background/service_worker.js`, and `manifest.json`.

---

## Why an extension rather than the WhatsApp Business API

The WhatsApp Cloud API requires Meta Business verification, which takes weeks
and is granted to a business entity, not a hackathon project. More importantly,
it is the wrong shape for this problem: a Business API bot receives messages
that users deliberately forward to a bot number, which means the user has
already decided the message is suspicious and has already shared the whole
conversation with a third party.

An extension on WhatsApp **Web** inverts that. The message never leaves the
user's own machine unless they ask for a check, the user picks exactly which
message to check, and the verification runs against a server they control. It is
a better privacy posture than the official API path, not a workaround for it.

---

## The rules this extension follows

### 1. It never automates WhatsApp

This is the constraint that matters most for platform compliance. WhatsApp's
Terms of Service prohibit automated or bulk use of the service and unofficial
clients. The extension therefore **never writes to WhatsApp at all**:

- it does not send messages,
- it does not reply, forward, or react,
- it does not type into the composer,
- it does not click any WhatsApp control on the user's behalf,
- it does not read or enumerate contacts, groups, or chat lists,
- it does not export, sync, or back up conversations.

It adds its own button and its own panel on top of the page, and reads the text
of one message when the user asks. It is a reading aid, not a client.

If the user wants to warn the group, they download the warning card and forward
it themselves. That is a deliberate design decision: the human stays in the loop
for every outbound action.

### 2. Nothing happens without an explicit click

There is no background scanning. There is no periodic sweep. There is no
"analyse this chat" mode. The `MutationObserver` in `content.js` exists to
attach a hover button to new message bubbles — it reads no message content, and
`extractMessageText()` is called only from the button's click handler.

Consent is separate and comes first: the initial check shows a panel explaining
what will be sent and where, and nothing is transmitted until the user accepts.
Consent can be withdrawn at any time from the toolbar popup, and
`consent` is never defaulted to `true` on install.

### 3. Data minimisation, applied before transmission

The only thing sent is the text of the selected message, after local redaction:

| Data | Sent? | Why |
|---|---|---|
| Selected message text | Yes | It is what is being checked |
| Phone numbers in that text | **Redacted locally** | Not needed to detect fraud |
| Email addresses in that text | **Redacted locally** | Not needed to detect fraud |
| UPI addresses (`name@ybl`) | Yes | This is the strongest fraud signal — where the money goes |
| URLs and domains | Yes | Needed for lookalike-domain detection |
| Sender name / phone number | No | Never read |
| Other messages in the chat | No | Never read |
| Contact list, group members | No | Never read |
| The user's own number | No | Never read |
| Media, attachments | No | Never read |

Redaction happens in `redact()` in the content script, before the message is
handed to the service worker — so unredacted text never reaches the network
layer at all.

### 4. The user chooses the destination

`host_permissions` is limited to `127.0.0.1:8000` and `localhost:8000`. The
extension cannot reach any other host without the user changing the manifest.
The default endpoint is the user's own machine. There is no vendor server, no
analytics, no telemetry, and no third-party SDK in this extension.

### 5. Nothing is retained

The extension writes only two things to `chrome.storage.local`: the endpoint URL
and the consent boolean. Message text is never stored — it lives in a local
variable for the duration of one request and is discarded with the panel.

The verifier it talks to persists a SHA-256 hash of the normalised content plus
the derived verdict, never the message body. The hash exists so that repeated
reports of identical content can be recognised as one fraud campaign rather than
many separate incidents. A hash of a message cannot be turned back into the
message.

---

## What a user should still know

- **A verdict is not advice.** UNVERIFIED genuinely means "we could not check
  this", not "this is safe".
- **The check is only as good as the corpus.** Filing cross-checks cover listed
  companies whose announcements are in the local corpus.
- **The endpoint is trusted by you.** If you point the extension at a server you
  do not control, you are sending message text to whoever runs it. The default
  avoids this entirely.

---

## Permissions, and why each is needed

| Permission | Reason |
|---|---|
| `storage` | Persist the endpoint URL and the consent flag. Nothing else. |
| `host_permissions: 127.0.0.1:8000, localhost:8000` | Send the check request to the user's own verifier. |
| `content_scripts` on `https://web.whatsapp.com/*` | Attach the "Check this" button and render the verdict panel. |

There is deliberately **no** `tabs`, `<all_urls>`, `webRequest`, `cookies`,
`history`, `clipboardRead`, or `scripting` permission. The extension cannot see
any site other than WhatsApp Web, and cannot see anything on WhatsApp Web that
the user has not asked it to check.
