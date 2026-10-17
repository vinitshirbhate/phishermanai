"""Remove a tracked literal credential without displaying it."""
from pathlib import Path
import re
path = Path(__file__).resolve().parents[2] / 'fake_propaganda/main.py'
text = path.read_text(encoding='utf-8')
text, count = re.subn(r'^FIRECRAWL_API_KEY\s*=\s*["\'][^"\']*["\']\s*$',
                    'FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")', text, flags=re.M)
path.write_text(text, encoding='utf-8')
print(f'Replaced {count} literal credential assignment(s). Provider revocation still required.')
