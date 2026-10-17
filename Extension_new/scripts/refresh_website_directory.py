"""Import exact government hosts from official directories, with provenance.

Popularity and shared hosting are never evidence that a page is safe.
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ['https://igod.gov.in/', 'https://www.india.gov.in/', 'https://www.usa.gov/agency-index']

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href: self.links.append(href)

def government_host(host):
    return bool(host and host not in {'gov.in', 'nic.in'} and
                (host.endswith('.gov.in') or host.endswith('.nic.in') or host.endswith('.gov')))

def refresh():
    path = ROOT / 'extension/data/website_allowlist.json'
    doc = json.loads(path.read_text(encoding='utf-8'))
    entries = {e['hostname']: e for e in doc['entries']}
    today = datetime.now(timezone.utc).date().isoformat()
    report = {'fetchedAt': today, 'sources': [], 'added': 0, 'reviewed': 0}
    for source in SOURCES:
        try:
            request = Request(source, headers={'User-Agent': 'PhishermanAI-directory-refresh/1.0'})
            with urlopen(request, timeout=20) as response:
                if urlsplit(response.url).hostname != urlsplit(source).hostname:
                    raise ValueError('Unexpected cross-host source redirect')
                html = response.read(3_000_000).decode('utf-8', errors='replace')
            parser = Links(); parser.feed(html)
            hosts = set()
            for link in parser.links:
                url = urlsplit(urljoin(source, link))
                host = (url.hostname or '').lower().rstrip('.')
                if url.scheme in {'http', 'https'} and not url.username and government_host(host): hosts.add(host)
            for host in hosts:
                old = entries.get(host, {})
                if not old: report['added'] += 1
                entries[host] = {**old, 'hostname': host, 'scope': 'exact', 'source': source,
                    'reviewStatus': 'official-directory-listed', 'reviewedAt': today,
                    'addedAt': old.get('addedAt', today), 'category': 'government',
                    'note': 'Directory identity context; not a safety guarantee for content.'}
                report['reviewed'] += 1
            report['sources'].append({'url': source, 'hosts': len(hosts)})
        except Exception as error:
            report['sources'].append({'url': source, 'error': str(error)})
    # Local and unspecified addresses are not publicly reviewed websites.
    for host in list(entries):
        try:
            if not ipaddress.ip_address(host).is_global: entries.pop(host)
        except ValueError: pass
    doc['entries'] = sorted(entries.values(), key=lambda e: e['hostname'])
    doc['version'] = 'directory-' + today
    doc['note'] = 'Exact-host identity context. Directory-listed entries retain source/date; inherited entries need ownership review.'
    if not any(s.get('hosts') for s in report['sources']): raise RuntimeError(json.dumps(report))
    path.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    report['total'] = len(entries)
    (ROOT / 'eval/website_directory_refresh.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': refresh()
