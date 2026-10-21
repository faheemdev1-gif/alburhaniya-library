from contextvars import ContextVar
import time
DEADLINE=ContextVar('deadline',default=None)
QUEUE_WAIT=ContextVar('queue_wait_ms',default=0.0)
AUTH_TIME=ContextVar('auth_ms',default=0.0)
class BudgetExceeded(RuntimeError):pass
def expired():
 from app.core.search_trace import CURRENT_TRACE
 trace=CURRENT_TRACE.get()
 deadline=DEADLINE.get();return bool(trace and trace.cancelled.is_set()) or (deadline is not None and time.monotonic()>=deadline)
def check():
 if expired():raise BudgetExceeded('Request time budget exhausted')
