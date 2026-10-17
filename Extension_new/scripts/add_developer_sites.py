"""Add exact developer-service hosts; membership never certifies user content."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES = {
    'github.com': 'https://docs.github.com/en/get-started/start-your-journey/what-is-github',
    'docs.github.com': 'https://docs.github.com/',
    'api.github.com': 'https://docs.github.com/en/rest',
    'github.blog': 'https://github.blog/',
    'education.github.com': 'https://education.github.com/',
    'support.github.com': 'https://support.github.com/',
    'docs.python.org': 'https://www.python.org/',
    'pypi.org': 'https://www.python.org/',
    'developer.mozilla.org': 'https://developer.mozilla.org/',
    'docs.npmjs.com': 'https://docs.npmjs.com/',
    'learn.microsoft.com': 'https://learn.microsoft.com/',
    'developer.chrome.com': 'https://developer.chrome.com/',
    'web.dev': 'https://web.dev/',
    'docs.docker.com': 'https://docs.docker.com/',
    'hub.docker.com': 'https://docs.docker.com/docker-hub/',
    'docs.gitlab.com': 'https://docs.gitlab.com/',
    'codeberg.org': 'https://codeberg.org/',
    'askubuntu.com': 'https://askubuntu.com/',
}
path = ROOT / 'extension/data/website_allowlist.json'
doc = json.loads(path.read_text(encoding='utf-8'))
entries = {e['hostname']: e for e in doc['entries']}
added = 0
for host, source in SITES.items():
    old = entries.get(host, {})
    added += not bool(old)
    entries[host] = {**old, 'hostname': host, 'scope': 'exact', 'source': source,
        'reviewStatus': 'curated-developer-host', 'category': 'developer',
        'addedAt': old.get('addedAt', '2026-10-03'),
        'note': 'Recognized service hostname only; repositories, packages, uploads and external links are not certified.'}
doc['entries'] = sorted(entries.values(), key=lambda e: e['hostname'])
path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
print(f'Added {added} developer hosts; total {len(entries)}')
