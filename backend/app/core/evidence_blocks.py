"""Offset-preserving navigation blocks; source text is never rewritten."""
from contextvars import ContextVar
from functools import lru_cache, wraps
import re

INCLUDE_TOC = ContextVar('include_toc', default=False)
HEADER = re.compile(r'الموضوع\s+الصفحة|(?:^|\n)\s*(?:فهرس(?:\s+(?:الموضوعات|المحتويات))?|المحتويات)\s*(?=\n|$)')

@lru_cache(maxsize=8192)
def blocks(text, page_type='body'):
    header = HEADER.search(text)
    if header:
        start = header.start()
        return ([{'type':'body','start':0,'end':start}] if start else []) + [
            {'type':'toc','start':start,'end':len(text)}]
    return [{'type':page_type,'start':0,'end':len(text)}]

def block_at(text, start, page_type='body'):
    return next((b['type'] for b in blocks(text,page_type) if b['start']<=start<b['end']),page_type)

def body_text(text, page_type='body'):
    chars=list(text)
    for b in blocks(text,page_type):
        if b['type']=='toc':chars[b['start']:b['end']]=' '*(b['end']-b['start'])
    return ''.join(chars)

def navigation_scope(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        token=INCLUDE_TOC.set(bool(kwargs.get('include_toc',False)))
        try:return fn(*args,**kwargs)
        finally:INCLUDE_TOC.reset(token)
    return wrapped
