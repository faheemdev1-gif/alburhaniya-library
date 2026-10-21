"""Exclusive nested phase durations for one tool execution."""
from contextvars import ContextVar
from functools import wraps
from time import perf_counter
_phases=ContextVar('research_phases',default=None);_started=ContextVar('research_started',default=None);_candidates=ContextVar('research_candidates',default=None);_query_candidates=ContextVar('research_query_candidates',default=None)
def start_phases():
 _candidates.set(None);_query_candidates.set(None);_started.set(perf_counter());return _phases.set([])
def phase_snapshot():
 now=perf_counter();start=_started.get() or now;intervals=_phases.get() or [];points=sorted({start,now,*[x for _,a,b in intervals for x in (max(start,a),min(now,b))]});values={}
 for a,b in zip(points,points[1:]):
  active=[x for x in intervals if x[1]<=a and x[2]>=b];name=min(active,key=lambda x:x[2]-x[1])[0] if active else 'other_tool_execution';values[name]=values.get(name,0)+(b-a)*1000
 return {k:round(v,3) for k,v in values.items()}
def reset_phases(token):_phases.reset(token)
def record_phase(name,started):
 phases=_phases.get()
 if phases is not None:phases.append((name,started,perf_counter()))
def profiled(name):
 def decorate(fn):
  @wraps(fn)
  def wrapped(*a,**kw):
   from app.core.search_trace import stage
   stage(name)
   t=perf_counter()
   try:return fn(*a,**kw)
   finally:record_phase(name,t)
  return wrapped
 return decorate
def record_candidates(identities,per_query=None):_candidates.set(set(identities));_query_candidates.set(per_query)
def candidate_snapshot():return _candidates.get()
def query_candidate_snapshot():return _query_candidates.get()
