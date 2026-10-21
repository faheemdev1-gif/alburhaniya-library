"""Supervisor-visible, thread-safe lexical checkpoints and cancellation.

Context propagation shares the Trace object, not independent worker-local state.
A timeout response uses only immutable copies of validated evidence. Cancellation
is cooperative at stage boundaries and SQLite progress callbacks.
"""
from contextvars import ContextVar
from threading import RLock, Event
from copy import deepcopy
import time,uuid
CURRENT_TRACE=ContextVar('search_trace',default=None)

class SearchTrace:
    def __init__(self):
        self.request_id=uuid.uuid4().hex;self.started=time.monotonic()
        self.lock=RLock();self.cancelled=Event();self.events=[];self.active='queue_wait'
        self.rows=[];self.checkpoint_id=None;self.completed=None
    def start(self,stage):
        with self.lock:
            self.active=stage
            self.events.append({'stage':stage,'event':'start','elapsed_ms':round((time.monotonic()-self.started)*1000,3)})
            self.events=self.events[-128:]
    def publish(self,rows,stage):
        # Callers publish only source-validated rows, before optional work.
        with self.lock:
            self.rows=deepcopy(rows);self.completed=stage
            self.checkpoint_id=f'{self.request_id}:{len(self.events)}:{len(rows)}'
            self.events.append({'stage':stage,'event':'checkpoint','count':len(rows),
                                'elapsed_ms':round((time.monotonic()-self.started)*1000,3)})
    def snapshot(self):
        with self.lock:
            return {'trace_id':self.request_id,'active_stage':self.active,
                    'last_completed_stage':self.completed,'checkpoint_id':self.checkpoint_id,
                    'checkpoint_count':len(self.rows),'events':deepcopy(self.events)}
    def evidence(self):
        with self.lock:return deepcopy(self.rows)

def stage(name):
    trace=CURRENT_TRACE.get()
    if trace:trace.start(name)

def checkpoint(rows,name):
    trace=CURRENT_TRACE.get()
    if trace:trace.publish(rows,name)

def partial_response(trace,kwargs):
    from app.services.compact_response import compact_search_response,slim_response
    from app.mcp_contract import TOOL_META
    rows=trace.evidence();rows.sort(key=lambda r:(-r.get('score',0),r['book_id'],r['seq']))
    if kwargs.get('operator')=='AND' and len(kwargs.get('queries') or [])>1:
        # A checkpoint may precede the multi-query intersection. Do not return
        # an OR union as evidence satisfying the caller's AND semantics.
        rows=[]
    offset=max(0,kwargs.get('offset',0));limit=max(1,min(20,kwargs.get('limit',8)))
    selected=rows[offset:offset+limit]
    if kwargs.get('min_score'):selected=[r for r in selected if r['score']>=kwargs['min_score']]
    payload=compact_search_response(selected,limit=limit,offset=offset,has_more=len(rows)>offset+limit,
                                    ultra=kwargs.get('mode')=='ultra_compact')
    payload.update(completion='partial',status={'execution':'partial','evidence_status':'candidates' if selected else 'unknown_due_to_budget'},
       evidence_strength='candidate' if selected else 'weak',answer_verified=False,
       request_id=trace.request_id,contract=dict(TOOL_META),truncated_by_budget=True,
       stages_skipped=[trace.active],diagnostics=trace.snapshot(),
       stage=trace.active,partial_results_available=bool(selected),
       reformulation_status='degraded',timing={'total_ms':round((time.monotonic()-trace.started)*1000,3),'scope':'queue_and_worker_wall'})
    if not selected:payload['error']={'code':'time_budget_exceeded','message':'No validated evidence before deadline','retryable':True,'request_id':trace.request_id}
    return slim_response(payload,detail=kwargs.get('detail','summary'),ultra=kwargs.get('mode')=='ultra_compact')
