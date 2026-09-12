"""Per-call timings; nested phase values are inclusive, not additive."""
from contextvars import ContextVar
from functools import wraps
from time import perf_counter

_phases = ContextVar('research_phases', default=None)

def start_phases():
    _candidates.set(None)
    return _phases.set({})

def phase_snapshot():
    return {key: round(value, 2) for key, value in (_phases.get() or {}).items()}

def reset_phases(token):
    _phases.reset(token)

def record_phase(name, started):
    phases = _phases.get()
    if phases is not None:
        phases[name] = phases.get(name, 0.0) + (perf_counter()-started)*1000

def profiled(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            started = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                record_phase(name, started)
        return wrapped
    return decorate

_candidates = ContextVar('research_candidates', default=None)

def record_candidates(identities):
    _candidates.set(set(identities))

def candidate_snapshot():
    return _candidates.get()
