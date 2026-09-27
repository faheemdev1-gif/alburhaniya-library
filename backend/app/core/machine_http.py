"""Machine-route authentication/quota and bounded threaded SDK execution."""
import hashlib,hmac,json,sqlite3,time
from functools import wraps
from app.core.config import get_settings
from app.core.budget import QUEUE_WAIT,AUTH_TIME,DEADLINE
class MachineHTTP:
 def __init__(self,app):self.app=app
 async def __call__(self,scope,receive,send):
  if scope['type']!='http' or not (scope.get('path','')=='/mcp' or scope.get('path','').startswith('/mcp/')):return await self.app(scope,receive,send)
  async def error(status,code,message,extra=None,retry=None):
   body=json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':code,'message':message,'data':extra or {}}}).encode();headers=[(b'content-type',b'application/json'),(b'cache-control',b'no-store')]
   if retry is not None:headers.append((b'retry-after',str(retry).encode()))
   await send({'type':'http.response.start','status':status,'headers':headers});await send({'type':'http.response.body','body':body})
  settings=get_settings();headers=dict(scope.get('headers',[]));auth=headers.get(b'authorization',b'').decode(errors='replace');keys=[k.strip() for k in settings.mcp_api_keys.split(',') if k.strip()];started=time.perf_counter()
  if keys and not any(hmac.compare_digest(auth,'Bearer '+k) for k in keys):return await error(401,-32001,'Authentication required')
  auth_token=AUTH_TIME.set((time.perf_counter()-started)*1000);identity=auth if keys else str(scope.get('client',('unknown',0))[0]);client=hashlib.sha256(identity.encode()).hexdigest();minute=int(time.time())//60
  try:
   with sqlite3.connect(settings.rate_limit_db_path,timeout=.3) as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS budgets(client TEXT,minute INTEGER,used INTEGER,PRIMARY KEY(client,minute))');conn.execute('DELETE FROM budgets WHERE minute<?',(minute-2,));used=conn.execute('INSERT INTO budgets VALUES(?,?,1) ON CONFLICT(client,minute) DO UPDATE SET used=used+1 RETURNING used',(client,minute)).fetchone()[0]
   if used>settings.mcp_requests_per_minute:
    retry=60-int(time.time())%60;return await error(429,-32029,'Client request budget exhausted',{'retry_after_ms':retry*1000,'remaining_budget':0},retry)
   blocked=False
   async def guarded(message):
    nonlocal blocked
    if message['type']=='http.response.start' and b'text/html' in dict(message.get('headers',[])).get(b'content-type',b''):
     blocked=True;await error(502,-32002,'Non-machine response blocked at application origin');return
    if not blocked:await send(message)
   await self.app(scope,receive,guarded)
  except sqlite3.Error:await error(503,-32003,'Quota service temporarily unavailable',{'retry_after_ms':1000},1)
  finally:AUTH_TIME.reset(auth_token)
def enable_threaded_tools(mcp):
 import anyio
 limiter=anyio.CapacityLimiter(2)
 for tool in mcp._tool_manager.list_tools():
  if tool.is_async:continue
  fn=tool.fn
  @wraps(fn)
  async def threaded(*args,__fn=fn,**kwargs):
   enqueued=time.perf_counter()
   def execute():
    token=QUEUE_WAIT.set((time.perf_counter()-enqueued)*1000)
    try:return __fn(*args,**kwargs)
    finally:QUEUE_WAIT.reset(token)
   seconds=min(19.0,max(.01,get_settings().request_budget_seconds));token=DEADLINE.set(time.monotonic()+seconds)
   try:
    with anyio.fail_after(seconds):return await anyio.to_thread.run_sync(execute,limiter=limiter,abandon_on_cancel=True)
   except TimeoutError:
    from app.core.resilience import safe_error_payload
    result=safe_error_payload('time_budget_exceeded','Request budget exhausted; narrow the query.',retryable=True);result['truncated_by_budget']=True;result['stage']='queue_or_worker_deadline';result['candidate_counts']={};result['partial_results_available']=False;result['timing']={'total_ms':round((time.perf_counter()-enqueued)*1000,3),'scope':'queue_and_worker_wait'};return result
   finally:DEADLINE.reset(token)
  tool.fn=threaded;tool.is_async=True
