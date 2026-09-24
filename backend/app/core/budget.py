from contextvars import ContextVar
import time
DEADLINE=ContextVar('deadline',default=None)
QUEUE_WAIT=ContextVar('queue_wait_ms',default=0.0)
AUTH_TIME=ContextVar('auth_ms',default=0.0)
class BudgetExceeded(RuntimeError):pass
def expired():
 deadline=DEADLINE.get();return deadline is not None and time.monotonic()>=deadline
def check():
 if expired():raise BudgetExceeded('Request time budget exhausted')
