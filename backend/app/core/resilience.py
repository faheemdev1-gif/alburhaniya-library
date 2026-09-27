"""Bounded retry and API-safe failure helpers for read-only research tools."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import logging
import re
import sqlite3
import time
import uuid
import json
from app.core.budget import DEADLINE,expired,BudgetExceeded,QUEUE_WAIT,AUTH_TIME
from app.core.config import get_settings
from app.core.observability import start_phases, phase_snapshot


logger = logging.getLogger(__name__)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_TRANSIENT_SQLITE_MARKERS = ("locked", "busy", "interrupted", "temporarily unavailable")


def new_request_id(value: str | None = None) -> str:
    supplied = re.sub(r"[^A-Za-z0-9._:-]", "", (value or "").strip())[:128]
    request_id = supplied or uuid.uuid4().hex
    _request_id.set(request_id)
    return request_id


def current_request_id() -> str:
    return _request_id.get() or new_request_id()


def is_transient_sqlite_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and any(
        marker in message for marker in _TRANSIENT_SQLITE_MARKERS
    )


def safe_error_payload(
    code: str, message: str, *, retryable: bool, retry_after_seconds: int | None = None,
) -> dict:
    error = {
        "code": code,
        "message": message,
        "retryable": bool(retryable),
        "request_id": current_request_id(),
    }
    if retry_after_seconds is not None:
        error["retry_after_seconds"] = int(retry_after_seconds)
    from app.mcp_contract import TOOL_META
    return {"error": error, "contract": dict(TOOL_META), "request_id": current_request_id()}


def safe_tool_call(function):
    """Retry transient SQLite reads and never expose raw infrastructure data."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        request_id = new_request_id()
        started = time.perf_counter()
        start_phases()
        from app.services.question_search import SEARCH_STATE
        SEARCH_STATE.set(None)
        from app.mcp_contract import TOOL_META
        def finish(payload, attempts):
            if isinstance(payload, dict):
                if isinstance(payload.get("error"), str):
                    payload["error"] = {"code":"invalid_selector", "message":payload["error"],
                                        "retryable":False,"request_id":request_id}
                payload["contract"] = dict(TOOL_META)
                if payload.get('error'):
                    from app.services.question_search import SEARCH_STATE
                    state=SEARCH_STATE.get() or {}
                    payload['stage']=state.get('stages_completed',['validation_or_initial_candidates'])[-1] if state.get('stages_completed') else 'validation_or_initial_candidates'
                    payload['candidate_counts']=state.get('candidate_counts',{})
                    payload['partial_results_available']=bool(state.get('candidate_counts',{}).get('phrase_candidates'))
                    query=kwargs.get('query') or (kwargs.get('queries') or [''])[0]
                    from app.services.query_language import subject_phrase
                    payload['retry']={'query':subject_phrase(query),'match_mode':'exact','include_counts':False}
                payload["request_id"] = request_id
                from app.core.observability import record_phase
                serialized=time.perf_counter();json.dumps(payload,ensure_ascii=False,default=str);record_phase('serialization_probe',serialized)
                phases=phase_snapshot();phases['queue_wait']=round(QUEUE_WAIT.get(),3);phases['authentication']=round(AUTH_TIME.get(),3)
                payload['timing']={'total_ms':round(sum(phases.values()),3),'attempts':attempts,'phases_ms':phases,'phase_semantics':'exclusive','scope':'tool_execution_plus_measured_queue_and_auth; excludes network and final transport serialization'}
                if expired():payload['truncated_by_budget']=True
            return payload
        for attempt, delay in enumerate((0.0, 0.05, 0.15), start=1):
            if delay:
                time.sleep(delay)
            try:
                from app.core.budget import check
                from app.core.observability import record_phase
                check()
                from app.core import result_cache
                k=None;cache_started=time.perf_counter()
                if function.__name__=='search_library' and not (kwargs.get('include_counts') or kwargs.get('check_completeness')):
                    k=result_cache.key(function.__name__,args,kwargs)
                    cached=result_cache.get(k)
                    if cached is not None:
                        cached['cache']={'status':'hit','scope':'process','corpus_bound':True}
                        record_phase('cache_lookup',cache_started)
                        return finish(cached,attempt)
                record_phase('cache_lookup',cache_started)
                execution=time.perf_counter()
                try:payload=function(*args, **kwargs)
                finally:record_phase('response_building',execution)
                if k is not None and isinstance(payload,dict):
                    result_cache.put(k,payload)
                    payload['cache']={'status':'miss','scope':'process','corpus_bound':True}
                return finish(payload, attempt)
            except BudgetExceeded:
                result=safe_error_payload('time_budget_exceeded','Request budget exhausted; retry the supplied subject phrase without counts.',retryable=True);result['truncated_by_budget']=True
                return finish(result,attempt)
            except ValueError as exc:
                logger.info(
                    "invalid tool request operation=%s request_id=%s error=%s",
                    function.__name__, request_id, exc,
                )
                return finish(safe_error_payload(
                    "invalid_request", str(exc), retryable=False,
                ),attempt)
            except sqlite3.OperationalError as exc:
                if expired():
                    result=safe_error_payload("time_budget_exceeded","Request budget exhausted; retry the supplied subject phrase without counts.",retryable=True);result["truncated_by_budget"]=True
                    return finish(result,attempt)
                if is_transient_sqlite_error(exc) and attempt < 3:
                    logger.warning(
                        "transient sqlite error operation=%s request_id=%s attempt=%d",
                        function.__name__, request_id, attempt,
                    )
                    continue
                logger.error(
                    "database operation failed operation=%s request_id=%s exception_type=%s",
                    function.__name__, request_id, type(exc).__name__,
                )
                return finish(safe_error_payload(
                    "temporary_unavailable",
                    "The library is temporarily unavailable. Retry the request shortly.",
                    retryable=is_transient_sqlite_error(exc),
                    retry_after_seconds=1 if is_transient_sqlite_error(exc) else None,
                ),attempt)
            except Exception as exc:
                logger.error(
                    "tool operation failed operation=%s request_id=%s exception_type=%s",
                    function.__name__, request_id, type(exc).__name__,
                )
                return finish(safe_error_payload(
                    "internal_error",
                    "The request could not be completed. Use the request_id when reporting it.",
                    retryable=False,
                ),attempt)
        return safe_error_payload(
            "temporary_unavailable",
            "The library is temporarily unavailable. Retry the request shortly.",
            retryable=True,
            retry_after_seconds=1,
        )

    @wraps(function)
    def scoped(*args,**kwargs):
        inherited=DEADLINE.get();deadline=time.monotonic()+min(19.0,max(.01,get_settings().request_budget_seconds));token=DEADLINE.set(min(inherited,deadline) if inherited is not None else deadline)
        try:return wrapped(*args,**kwargs)
        finally:DEADLINE.reset(token)
    return scoped
