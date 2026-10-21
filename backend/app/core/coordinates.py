"""Source coordinates shared by search, page and passage APIs.

Offsets are Python Unicode code points into the exact, unformatted pages.text.
No HTML stripping, display formatting or Unicode normalization is permitted here.
"""
from functools import lru_cache
import hashlib

REPRESENTATION = 'canonical-page-text-v1'

@lru_cache(maxsize=8192)
def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def coordinate_contract(text):
    return {'offset_unit':'unicode_codepoint','offset_scope':'page_text',
            'range':'[start,end)','representation_id':REPRESENTATION,
            'text_version':_digest(text)[:16],'text_sha256':_digest(text),
            'page_chars':len(text)}

def source_span(text,start,end):
    start,end=int(start),int(end)
    if not 0 <= start < end <= len(text):
        raise ValueError('Invalid canonical source coordinates')
    return {'start':start,'end':end,'source_quote':text[start:end]}
