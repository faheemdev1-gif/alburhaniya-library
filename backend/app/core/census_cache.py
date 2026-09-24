"""Bounded cache including source identity, corpus digest and navigation scope."""
import os,json,threading,copy
from collections import OrderedDict
from functools import wraps
_cache=OrderedDict();_lock=threading.Lock()
def cached_census(fn):
 @wraps(fn)
 def wrapped(*a,**kw):
  from app.core.config import get_settings
  from app.core.evidence_blocks import INCLUDE_TOC
  from app.services.library_db import _connection
  path=os.path.abspath(get_settings().library_db_path);st=os.stat(path)
  try:row=_connection().execute("SELECT value FROM discovery_meta WHERE key='corpus_digest'").fetchone();digest=row[0] if row else ''
  except Exception:digest='unavailable'
  key=(path,st.st_ino,st.st_size,st.st_mtime_ns,digest,INCLUDE_TOC.get(),json.dumps([a,kw],ensure_ascii=False,sort_keys=True,default=str))
  with _lock:
   if key in _cache:return copy.deepcopy(_cache[key])
  value=fn(*a,**kw)
  with _lock:
   _cache[key]=copy.deepcopy(value)
   while len(_cache)>256:_cache.popitem(last=False)
  return value
 return wrapped
