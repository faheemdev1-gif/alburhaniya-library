"""Source-quality warnings never silently rewrite quoted religious text."""
from functools import lru_cache
import json
from pathlib import Path

@lru_cache(maxsize=1)
def _entries():
    path = Path(__file__).resolve().parents[2] / 'data' / 'text_errata.json'
    return json.loads(path.read_text(encoding='utf-8')).get('entries', [])

def warnings(book_id, seq):
    return [dict(entry, source_text_preserved=True) for entry in _entries()
            if entry.get('book_id') == book_id and entry.get('seq') == seq]
