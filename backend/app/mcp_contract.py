"""Immutable public contract for the Al Burhania MCP surface."""
from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
from typing import Any


SERVER_VERSION = "2.10.16"
TOOL_CONTRACT_VERSION = "15.0"
TOOL_CONTRACT_ID = "alburhaniya-tools-v15"

REQUIRED_TOOLS = frozenset({
    "search_library",
    "get_passage",
    "get_page",
    "get_book",
    "list_books",
})

SCHEMA_CAPABILITIES = {
    "search_library": {
        "match_modes": ["auto", "exact", "terms", "hybrid", "lexeme"],
        "response_modes": ["compact", "ultra_compact"],
        "ultra_summary_encoding": "lossless-15",
        "ultra_contract_digests": "keys v=server_version,d=schema_digest,t=tool_schema_digest; 8-character digest prefixes; full values in get_book/list_books or detail=full",
        "supported_parameters": [
            "query", "queries", "book_ids", "book_scope", "qasida_number",
            "include_counts", "check_completeness", "include_toc", "include_topic_only", "count_basis", "whole_word", "min_tier",
            "expand_top", "expand_chars", "min_score", "match_mode", "mode",
            "operator", "limit", "offset", "source_code", "page_from", "page_to",
            "detail", "keep_terms", "context_chars", "search_mode", "ranking", "diversify_books", "max_per_book",
        ],
    },
    "get_passage": {
        "supported_parameters": ["match_id", "match_ids", "stable_id", "qasida_number", "context_mode", "max_chars", "context_chars", "query", "include_parallels", "parallel_limit"],
        "selector_policy": "exactly_one; qasida_number_returns_full_structure",
        "selectors": ["match_id", "match_ids", "stable_id", "qasida_number"],
        "parallel_candidates": True,
        "context_modes": ["bounded", "paragraph"],
        "default_max_chars": 12000,
        "cross_page_context": True,
        "max_context_pages": 3,
        "numbered_heading_section": True,
    },
    "get_page": {"default_max_chars": 20000, "declares_truncation": True, "effective_cap_disclosed": True, "ultra_compact": "omits_book_metadata"},
    "list_books": {"supported_parameters": ["include_legend", "projection", "book_ids"],
                   "projections": ["compact", "ids", "full"]},
}
SCHEMA_DIGEST = hashlib.sha256(
    json.dumps(
        SCHEMA_CAPABILITIES, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

TOOL_META: dict[str, str | int] = {
    "server_version": SERVER_VERSION,
    "tool_contract_version": TOOL_CONTRACT_VERSION,
    "tool_contract": TOOL_CONTRACT_ID,
    "tool_count": len(REQUIRED_TOOLS),
    "schema_digest": SCHEMA_DIGEST,
}


def validate_tool_names(names: Iterable[str]) -> tuple[str, ...]:
    """Return a deterministic tool list or fail on any contract drift."""
    ordered = tuple(names)
    duplicates = sorted({name for name in ordered if ordered.count(name) > 1})
    actual = set(ordered)
    if duplicates or actual != REQUIRED_TOOLS:
        missing = sorted(REQUIRED_TOOLS - actual)
        unexpected = sorted(actual - REQUIRED_TOOLS)
        raise RuntimeError(
            "BROKEN MCP TOOLSET: "
            f"expected={sorted(REQUIRED_TOOLS)}, received={sorted(actual)}, "
            f"missing={missing}, unexpected={unexpected}, duplicates={duplicates}"
        )
    return tuple(sorted(actual))


def registered_tool_names(server: Any) -> tuple[str, ...]:
    """Read the FastMCP registry that directly backs protocol tools/list."""
    manager = getattr(server, "_tool_manager", None)
    if manager is None or not hasattr(manager, "list_tools"):
        raise RuntimeError("FastMCP tool registry is unavailable")
    return tuple(tool.name for tool in manager.list_tools())


def validate_registered_tools(server: Any) -> tuple[str, ...]:
    """Fail startup when the protocol-facing registry violates the contract."""
    return validate_tool_names(registered_tool_names(server))


def contract_metadata(tools: Iterable[str] | None = None) -> dict[str, Any]:
    """Versioned metadata for health checks and deployment diagnostics."""
    actual = validate_tool_names(tools or REQUIRED_TOOLS)
    from app.services.compact_response import ULTRA_FIELDS,BASE_FIELDS,VALUE_CODES,NESTED_KEYS,CODE_SYMBOLS,ENVELOPE_KEYS,BOOK_KEYS
    from app.services.traffic_metrics import traffic_summary
    return {
        "changes_since_previous":[
            "Persistent source evidence units, bounded route-family fusion and explicit caps",
            "Subject-preserving question frames and typed unreviewed discovery links",
            "Canonical get_page text with source-resolving code-point spans on every search path",
            "Unreliable printed labels omitted; speaker and support metadata validated before projection",
            "Supervisor-visible validated lexical checkpoints and cooperative cancellation",
            "Reversible compact/ultra evidence projections and separate full diagnostics",
            "Configurable all-traffic attempt metrics separate from scheduled samples"],
        "known_issues":[
            "No independent held-out Direct@5 or 10/10 rating established",
            "Domain lexicon and automated support labels remain unreviewed and uncalibrated",
            "Documentary provenance and unresolved printed labels need original scans and review",
            "Production latency, client schema refresh and durable seven-day monitoring need deployment verification",
            "No cross-encoder or contextual morphology model has been independently benchmarked"],
        "reformulation_status_policy":{"ok":"All planned discovery stages completed; not an answer-quality judgement","degraded":"A stage was skipped or stopped; inspect partial results","not_needed":"Literal/terms/lexeme path, no question rewrite"},
        "coverage_register":[{"topic":"raising children","status":"weak_coverage","basis":"Supplied audit: two passing mentions, no substantive guidance","grading_policy":"exclude from direct-answer denominator; do not invent filler"}],
        "result_defaults_policy":"Search hits inherit result_defaults; explicit hit fields override defaults. Contract 12 clients must expand defaults.",
        "ultra_aliases":{**BASE_FIELDS,**{v:k for k,v in ULTRA_FIELDS.items()}},
        "minimal_encoding":{"id":"lossless-15","timing":"ms=total milliseconds","versions":"i=index,l=lexicon,c=cues,r=ranker","value_codes":dict(zip(CODE_SYMBOLS,VALUE_CODES)),"literal_escape":"prefix ~","envelope_keys":ENVELOPE_KEYS,"book_keys":BOOK_KEYS,"nested_keys":NESTED_KEYS,"derived_fields":"book_id/seq from match_id, absent rank from 1-based array order; @printed citation from book title + ، الصفحة + printed label", "objects":"integer references for object-valued sp/matched_terms/sup", "qasidas":"qref inherits exact metadata from qasidas table", "expanded_passages":"from_hit lists exactly inherited fields","span":"[start,end,optional_source_quote]","decoder":"app.services.compact_response.decode_search_response"},
        "coordinate_policy":"Unicode code points in canonical unformatted get_page.text; half-open spans",
        "traffic_monitoring":traffic_summary(),
        "monitoring":__import__("app.services.monitoring",fromlist=["monitoring_summary"]).monitoring_summary(),
        "rate_limit":{"requests_per_minute":__import__("app.core.config",fromlist=["get_settings"]).get_settings().mcp_requests_per_minute,"scope":"authenticated_client_or_peer_ip","retry_policy":"HTTP 429 JSON-RPC with Retry-After and retry_after_ms"},
        "server_version": SERVER_VERSION,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "tool_contract": TOOL_CONTRACT_ID,
        "tool_count": len(actual),
        "tools": list(actual),
        "schema_digest": SCHEMA_DIGEST,
        "tool_schema_digest": TOOL_META.get("tool_schema_digest"),
        "schema_digest_kind": "capability_manifest",
        "schema_capabilities": SCHEMA_CAPABILITIES,
        "compatibility_policy": "Compare tool_contract_version, schema_digest and tool_schema_digest on every response. Any digest change requires refreshing tools/list before the next call. A major version change may alter semantics; minor changes are additive. tool_count is cardinality, not a version.",
    }


def bind_callable_schema(server: Any) -> None:
    """Validate capabilities against tools/list and fingerprint callable schemas."""
    tools = server._tool_manager.list_tools()
    # The callable declarations are authoritative for every advertised argument.
    for tool in tools:
        SCHEMA_CAPABILITIES.setdefault(tool.name,{})["supported_parameters"]=sorted(tool.parameters.get("properties",{}))
    from app.services.compact_response import encoding_guide
    SCHEMA_CAPABILITIES['search_library']['decoder_digest']=hashlib.sha256(json.dumps(encoding_guide(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    global SCHEMA_DIGEST
    SCHEMA_DIGEST=hashlib.sha256(json.dumps(SCHEMA_CAPABILITIES,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    TOOL_META['schema_digest']=SCHEMA_DIGEST
    schemas = {tool.name: tool.parameters for tool in tools}
    for name, capability in SCHEMA_CAPABILITIES.items():
        properties = schemas[name].get('properties', {})
        missing = set(capability.get('supported_parameters', [])) - properties.keys()
        if missing:
            raise RuntimeError(f'Advertised parameters missing from {name}: {sorted(missing)}')
    paragraph = schemas['get_passage']['properties']['context_mode']
    if set(paragraph.get('enum', [])) != {'bounded', 'paragraph'}:
        raise RuntimeError('get_passage paragraph capability differs from callable schema')
    TOOL_META['tool_schema_digest'] = hashlib.sha256(json.dumps(
        schemas, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    ).encode()).hexdigest()
    from app.core.config import get_settings
    configured=get_settings().client_schema_digests
    if configured:
        clients=json.loads(configured)
        stale=[name for name,digest in clients.items() if digest!=TOOL_META['tool_schema_digest']]
        if stale:raise RuntimeError('Client schema refresh required: '+', '.join(stale))
    for tool in tools:
        if tool.meta is not None:
            tool.meta.update(TOOL_META)
