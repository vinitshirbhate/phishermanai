# Build the ScamGate L1 model and verify the backend can find it.
#
# Run from the repository root:
#   .\models\setup.ps1
#
# The verification step is the point of this script. `ollama create` reports
# success as long as the Modelfile parses, which tells you nothing about
# whether scamgate will use the result — the name has to match what the code
# looks for, and a mismatch fails silently at runtime.

param(
    [ValidateSet("default", "fast")]
    [string]$Variant = "default"
)

$ErrorActionPreference = "Stop"

if ($Variant -eq "fast") {
    $ModelName = "phisherman-guard-fast"
    $ModelFile = "models/phisherman-guard-fast.Modelfile"
} else {
    $ModelName = "phisherman-guard"
    $ModelFile = "models/phisherman-guard.Modelfile"
}

if (-not (Test-Path $ModelFile)) {
    Write-Host "Cannot find $ModelFile" -ForegroundColor Red
    Write-Host "Run this from the repository root (the folder containing backend\ and extension\)."
    exit 1
}

# Is Ollama actually running? `ollama create` gives a confusing error if the
# daemon is down, so check first and say so plainly.
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
} catch {
    Write-Host "Ollama is not responding on http://localhost:11434" -ForegroundColor Red
    Write-Host "Start it (`ollama serve`, or launch the Ollama app) and re-run."
    exit 1
}

Write-Host "Pulling base model phi4-mini (~2.5 GB, skipped if present)..." -ForegroundColor Cyan
ollama pull phi4-mini
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not pull phi4-mini." -ForegroundColor Red
    Write-Host "If your Ollama build does not have it, edit the FROM line in"
    Write-Host "$ModelFile to a model you do have — llama3.2:3b and qwen2.5:3b"
    Write-Host "both work with this prompt, with somewhat lower accuracy."
    exit 1
}

Write-Host "Building $ModelName..." -ForegroundColor Cyan
ollama create $ModelName -f $ModelFile
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed." -ForegroundColor Red; exit 1 }

# --- Verification -------------------------------------------------------- #
# Reproduces exactly what L1LocalLLM.available() does: fetch /api/tags, strip
# the :tag suffix from each installed model, and test for EXACT membership.
# Not prefix matching — "phisherman-guard" does not match
# "phisherman-guard-fast", which is precisely the trap this catches.
$tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
$installed = $tags.models | ForEach-Object { ($_.name -split ":")[0] }

if ($installed -contains $ModelName) {
    Write-Host "Model '$ModelName' is installed." -ForegroundColor Green
} else {
    Write-Host "Built, but '$ModelName' is not in the installed list." -ForegroundColor Red
    Write-Host "Installed: $($installed -join ', ')"
    exit 1
}

$expected = if ($env:SCAMGATE_MODEL) { $env:SCAMGATE_MODEL } else { "phisherman-guard" }
if ($expected -eq $ModelName) {
    Write-Host "The backend will use this model. No further configuration needed." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "NAME MISMATCH — the backend will NOT use this model." -ForegroundColor Yellow
    Write-Host "  built:            $ModelName"
    Write-Host "  backend looks for: $expected"
    Write-Host ""
    Write-Host "Fix it for this session:" -ForegroundColor Yellow
    Write-Host "  `$env:SCAMGATE_MODEL = `"$ModelName`""
    Write-Host "Or permanently:"
    Write-Host "  [Environment]::SetEnvironmentVariable('SCAMGATE_MODEL','$ModelName','User')"
    Write-Host ""
    Write-Host "Left unset, the L1 tier is skipped silently — no error, just"
    Write-Host "weaker analysis."
}

Write-Host ""
Write-Host "Smoke test:" -ForegroundColor Cyan
$body = @{
    model  = $ModelName
    stream = $false
    messages = @(
        @{ role = "user"; content = "Congratulations! You won 25 lakh in the KBC lucky draw. Send your Aadhaar and pay a 5000 processing fee to claim." }
    )
} | ConvertTo-Json -Depth 5

try {
    $r = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post `
        -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host $r.message.content
    Write-Host ""
    Write-Host "Expect a JSON object with a non-safe verdict. If you got prose" -ForegroundColor DarkGray
    Write-Host "instead of JSON, the parser still recovers it, but the base" -ForegroundColor DarkGray
    Write-Host "model is weaker at instruction-following than phi4-mini." -ForegroundColor DarkGray
} catch {
    Write-Host "Smoke test failed: $_" -ForegroundColor Yellow
}
