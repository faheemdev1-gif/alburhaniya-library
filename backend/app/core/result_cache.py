"""Bounded cross-worker cache with corpus hash and complete request controls."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
import hashlib,json,os,sqlite3,time
from app.core.config import get_settings
from app.core.evidence_blocks import INCLUDE_TOC
_CACHE=OrderedDict();_LOCK=RLock();_DIGEST={}
_SHARED_PATH=os.environ.get('RESULT_CACHE_PATH','/tmp/alburhaniya-result-cache.sqlite3')

def _shared():
 c=sqlite3.connect(_SHARED_PATH,timeout=.25)
 c.execute('PRAGMA busy_timeout=250')
 c.execute('CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL)')
 return c
def key(function,args,kwargs):
 from app.mcp_contract import SERVER_VERSION
 path=os.path.abspath(get_settings().library_db_path);st=os.stat(path);stamp=(path,st.st_mtime_ns,st.st_size,st.st_ino)
 with _LOCK:
  if stamp not in _DIGEST:
   with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as c:row=c.execute("SELECT value FROM discovery_meta WHERE key='corpus_digest'").fetchone()
   _DIGEST.clear();_DIGEST[stamp]=row[0] if row else None
  digest=_DIGEST[stamp]
 return hashlib.sha256(json.dumps([SERVER_VERSION,function,args,kwargs,stamp,digest,INCLUDE_TOC.get()],sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
def get(k):
 with _LOCK:
  value=_CACHE.get(k)
  if value is not None:_CACHE.move_to_end(k);return deepcopy(value)
 try:
  with _shared() as c:
   row=c.execute('SELECT value FROM results WHERE key=?',(k,)).fetchone()
  if row:
   value=json.loads(row[0])
   with _LOCK:_CACHE[k]=value;_CACHE.move_to_end(k)
   return deepcopy(value)
 except (OSError,sqlite3.Error,ValueError):
  pass  # Read-only deployments retain the bounded process cache.
def put(k,value):
 if value.get('error') or value.get('completion')=='partial' or value.get('truncated_by_budget'):return
 with _LOCK:
  _CACHE[k]=deepcopy(value);_CACHE.move_to_end(k)
  while len(_CACHE)>128:_CACHE.popitem(last=False)
 try:
  with _shared() as c:
   c.execute('INSERT OR REPLACE INTO results VALUES (?,?,?)',(k,json.dumps(value,ensure_ascii=False,default=str),time.time()))
   c.execute('DELETE FROM results WHERE key IN (SELECT key FROM results ORDER BY created DESC LIMIT -1 OFFSET 512)')
 except (OSError,sqlite3.Error,TypeError):
  pass
def clear():
 with _LOCK:_CACHE.clear()
 try:
  with _shared() as c:c.execute('DELETE FROM results')
 except (OSError,sqlite3.Error):pass
