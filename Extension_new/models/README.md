# models/

Ollama model definitions for the **L1 local analysis tier** in
`backend/engines/scamgate.py`.

## Quick start

From the repository root:

```powershell
.\models\setup.ps1              # Windows
```
```bash
./models/setup.sh               # macOS / Linux
```

Or manually:

```bash
ollama pull phi4-mini
ollama create phisherman-guard -f models/phisherman-guard.Modelfile
```

## The name matters more than it looks

`backend/engines/scamgate.py`:

```python
OLLAMA_MODEL = os.environ.get("SCAMGATE_MODEL", "phisherman-guard")
```

`L1LocalLLM.available()` fetches the installed-model list and tests for an
**exact** name match after stripping the `:tag` suffix. It is not a prefix
match, so `phisherman-guard` does **not** match `phisherman-guard-fast`.

When the name does not match, `available()` returns `False` and the
pipeline skips L1 and continues at L0/L2. **No exception, no log line, no
error in the UI** — just quietly weaker analysis. This is the single most
likely way to end up with a working-looking install that never uses the
model you built.

| You build | You must also set |
|---|---|
| `phisherman-guard` | nothing |
| `phisherman-guard-fast` | `SCAMGATE_MODEL=phisherman-guard-fast` |

Build `phisherman-guard` unless you have a reason not to.

## Variants

| | `phisherman-guard` | `phisherman-guard-fast` |
|---|---|---|
| Base | phi4-mini | phi4-mini |
| `num_ctx` | 8192 | 4096 |
| `num_predict` | 200 | 160 |
| Trade-off | fits scamgate's full 3000-char cut | long pages lose their tail |

Both are the same weights. "Fast" saves prompt-processing and decode time by
truncating earlier, which is fine for chat messages and short pages and
costs you real signal on a long investment-pitch page.

## If phi4-mini is unavailable

Edit the `FROM` line. `llama3.2:3b` and `qwen2.5:3b` both work with this
prompt. Expect somewhat weaker instruction-following — the model may return
prose around the JSON. `L1LocalLLM.analyze()` already handles that: it
searches for the outermost `{`...`}` and falls back to a `suspicious`
verdict at 0.5 confidence if parsing fails, so a chatty model degrades
rather than breaks.

## This tier is optional

Without Ollama the extension still works. `scamgate` falls through to the
L0 pattern detector (offline, bundled) and, if configured, the L2 cloud
tier. The offline local gate in `extension/content_script.js` is unaffected
either way — it never depended on this.

Verify what is actually running:

```bash
curl http://localhost:8799/health
```
