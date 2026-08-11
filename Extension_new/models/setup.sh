#!/usr/bin/env bash
# Build the ScamGate L1 model and verify the backend can find it.
# Run from the repository root:  ./models/setup.sh [default|fast]
#
# The verification step is the point. `ollama create` succeeds whenever the
# Modelfile parses, which says nothing about whether scamgate will actually
# use the result -- the name must match what the code looks for, and a
# mismatch fails silently at runtime.
set -euo pipefail

VARIANT="${1:-default}"
if [ "$VARIANT" = "fast" ]; then
  MODEL_NAME="phisherman-guard-fast"
  MODEL_FILE="models/phisherman-guard-fast.Modelfile"
else
  MODEL_NAME="phisherman-guard"
  MODEL_FILE="models/phisherman-guard.Modelfile"
fi

[ -f "$MODEL_FILE" ] || {
  echo "Cannot find $MODEL_FILE"
  echo "Run this from the repository root (the folder containing backend/ and extension/)."
  exit 1
}

curl -sf http://localhost:11434/api/tags >/dev/null || {
  echo "Ollama is not responding on http://localhost:11434"
  echo "Start it (ollama serve) and re-run."
  exit 1
}

echo "Pulling base model phi4-mini (~2.5 GB, skipped if present)..."
ollama pull phi4-mini || {
  echo "Could not pull phi4-mini."
  echo "Edit the FROM line in $MODEL_FILE to a model you have."
  echo "llama3.2:3b and qwen2.5:3b both work, with somewhat lower accuracy."
  exit 1
}

echo "Building $MODEL_NAME..."
ollama create "$MODEL_NAME" -f "$MODEL_FILE"

# Reproduces L1LocalLLM.available(): strip the :tag suffix, test EXACT
# membership. Not a prefix match -- "phisherman-guard" does NOT match
# "phisherman-guard-fast", which is the trap this catches.
INSTALLED=$(curl -sf http://localhost:11434/api/tags \
  | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | cut -d: -f1 | sort -u)

if echo "$INSTALLED" | grep -qx "$MODEL_NAME"; then
  echo "Model '$MODEL_NAME' is installed."
else
  echo "Built, but '$MODEL_NAME' is not in the installed list."
  echo "Installed: $(echo "$INSTALLED" | tr '\n' ' ')"
  exit 1
fi

EXPECTED="${SCAMGATE_MODEL:-phisherman-guard}"
if [ "$EXPECTED" = "$MODEL_NAME" ]; then
  echo "The backend will use this model. No further configuration needed."
else
  echo
  echo "NAME MISMATCH -- the backend will NOT use this model."
  echo "  built:             $MODEL_NAME"
  echo "  backend looks for: $EXPECTED"
  echo
  echo "Fix:  export SCAMGATE_MODEL=$MODEL_NAME"
  echo
  echo "Left unset, the L1 tier is skipped silently -- no error, just"
  echo "weaker analysis."
fi

echo
echo "Smoke test:"
curl -sf http://localhost:11434/api/chat -H 'Content-Type: application/json' -d "{
  \"model\": \"$MODEL_NAME\", \"stream\": false,
  \"messages\": [{\"role\":\"user\",\"content\":\"Congratulations! You won 25 lakh in the KBC lucky draw. Send your Aadhaar and pay a 5000 processing fee to claim.\"}]
}" | python3 -c "import sys,json; print(json.load(sys.stdin)['message']['content'])" 2>/dev/null \
  || echo "Smoke test failed."
