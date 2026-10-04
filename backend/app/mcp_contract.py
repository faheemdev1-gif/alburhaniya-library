"""Immutable public contract for the Al Burhania MCP surface."""
from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
from typing import Any


SERVER_VERSION = "2.10.9"
TOOL_CONTRACT_VERSION = "12.0"
TOOL_CONTRACT_ID = "alburhaniya-tools-v12"

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
    return {
        "changes_since_previous":["Nouns written with the article never lose a verb prefix (التوكل is not وكل, التسليم is not سليم); removes false relation candidates for such subjects","Blessing formula عليه أفضل الصلاة والسلام is masked during scoring, so it no longer counts as virtue (فضل) or prayer evidence","Rare construct comparison subjects reduce to their head noun (خوف العقاب -> الخوف); established compounds such as علم اليقين are kept","Attached ب/ل/ك is stripped from subject words when the bare word is the attested one (بعين اليقين -> عين اليقين); ما المقصود and ما حقيقة are question frames","A passage naming the protected subject is kept as topic-only evidence when the only missing question words are verbs (يضر، يخاف)","ينبغي and يجب are frame words; path words (سلوك، طريق) are generic context like المريد"],
        "known_issues":["Independent source and documentary review remains open","Retrieval still depends on wording: about half of unseen paraphrases find the reviewed evidence; synonym gaps (درجات/مراتب، خشية/خوف، سيدنا محمد/النبي), remedy questions and adjective-to-noun forms remain","Automated relation labels are candidates, not verified answers","Private held-out and deployed acceptance are pending","Seven-day monitoring and client latency acceptance pending","Client schema refresh must be verified in each client"],
        "reformulation_status_policy":{"ok":"All planned discovery stages completed; not an answer-quality judgement","degraded":"A stage was skipped or stopped; inspect partial results","not_needed":"Literal/terms/lexeme path, no question rewrite"},
        "coverage_register":[{"topic":"raising children","status":"weak_coverage","basis":"Supplied audit: two passing mentions, no substantive guidance","grading_policy":"exclude from direct-answer denominator; do not invent filler"}],
        "result_defaults_policy":"Search hits inherit result_defaults; explicit hit fields override defaults. Contract 12 clients must expand defaults.",
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
