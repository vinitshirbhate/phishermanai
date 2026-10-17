"""Update extension endpoints and contract metadata to the unified local API."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = [ROOT / 'extension' / 'background.js', ROOT / 'extension/options/options.js',
         ROOT / 'extension/options/options.html', ROOT / 'extension/manifest.json']
files += list((ROOT / 'extension/contracts').glob('*.json'))
for path in files:
    text = path.read_text(encoding='utf-8')
    path.write_text(text.replace('127.0.0.1:8799', '127.0.0.1:8000'), encoding='utf-8')
