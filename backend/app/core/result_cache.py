"""Bounded process cache with corpus hash and complete request controls."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
import hashlib,json,os,sqlite3
from app.core.config import get_settings
from app.core.evidence_blocks import INCLUDE_TOC
_CACHE=OrderedDict();_LOCK=RLock();_DIGEST={}
def key(function,args,kwargs):
 path=os.path.abspath(get_settings().library_db_path);st=os.stat(path);stamp=(path,st.st_mtime_ns,st.st_size,st.st_ino)
 with _LOCK:
  if stamp not in _DIGEST:
   with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as c:row=c.execute("SELECT value FROM discovery_meta WHERE key='corpus_digest'").fetchone()
   _DIGEST.clear();_DIGEST[stamp]=row[0] if row else None
  digest=_DIGEST[stamp]
 return hashlib.sha256(json.dumps([function,args,kwargs,stamp,digest,INCLUDE_TOC.get()],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
def get(k):
 with _LOCK:
  value=_CACHE.get(k)
  if value is not None:_CACHE.move_to_end(k);return deepcopy(value)
def put(k,value):
 if value.get('error') or value.get('completion')=='partial' or value.get('truncated_by_budget'):return
 with _LOCK:
  _CACHE[k]=deepcopy(value);_CACHE.move_to_end(k)
  while len(_CACHE)>128:_CACHE.popitem(last=False)
def clear():
 with _LOCK:_CACHE.clear()
