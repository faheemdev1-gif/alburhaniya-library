#!/usr/bin/env python3
"""Post-deployment MCP-000/MCP-001 discovery and execution hard gate."""
from __future__ import annotations

import argparse
import hashlib
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.mcp_server import mcp as _local_schema_registry  # Bind the authoritative callable manifest.
from app.mcp_contract import (
    REQUIRED_TOOLS,
    SCHEMA_DIGEST,
    SERVER_VERSION,
    TOOL_CONTRACT_ID,
    TOOL_CONTRACT_VERSION,
    validate_tool_names,
)


SEARCH_REQUIRED_PROPERTIES = {
    "query", "queries", "operator", "book_scope", "book_ids",
    "include_counts", "qasida_number", "expand_top", "expand_chars",
    "min_score", "match_mode", "mode", "context_chars", "ranking",
    "whole_word", "count_basis", "min_tier", "check_completeness", "include_toc", "include_topic_only",
}
MATCH_MODES = {"auto", "exact", "terms", "hybrid", "lexeme"}
RESPONSE_MODES = {"compact", "ultra_compact"}


async def _validate_live_health(endpoint: str) -> dict[str, Any]:
    parts = urlsplit(endpoint)
    health_url = urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, trust_env=not local) as client:
        response = await client.get(health_url)
        response.raise_for_status()
    payload = response.json()
    if payload.get("server_version") != SERVER_VERSION:
        raise AssertionError("live health server version is stale")
    if payload.get("tool_contract_version") != TOOL_CONTRACT_VERSION:
        raise AssertionError("live health tool-contract version is stale")
    if set(payload.get("tools") or []) != REQUIRED_TOOLS:
        raise AssertionError("live health tool set violates the five-tool contract")
    corpus = payload.get("corpus_contract") or {}
    diwan = corpus.get("diwan") or {}
    research = corpus.get("research_indexes") or {}
    matching = corpus.get("matching_contract") or {}
    provenance = corpus.get("provenance_contract") or {}
    if not (
        corpus.get("status") == "ok"
        and diwan.get("qasidas") == 95
        and diwan.get("bayts") == 2682
        and diwan.get("continuous_bayt_numbering") is True
        and research.get("status") == "ok"
        and research.get("parallel_semantics") == "unverified_candidates_only"
        and matching.get("status") == "ok"
        and matching.get("whole_word_default") is True
        and matching.get("literal_normalization") == "safe"
        and provenance.get("status") == "ok"
    ):
        raise AssertionError(f"live corpus contract is broken or incomplete: {corpus}")
    editions = corpus.get("edition_deduplication") or {}
    if not (
        editions.get("status") == "ok"
        and editions.get("catalogue_books") == 43
        and editions.get("default_search_books") == 42
        and editions.get("default_search_pages") == 6885
        and editions.get("suppressed_editions") == ["b38"]
        and editions.get("canonical_aliases") == {"b38": "b37"}
    ):
        raise AssertionError(f"live edition-deduplication contract is broken: {editions}")
    return payload


def _enum_values(schema: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(schema, dict):
        enum = schema.get("enum")
        if isinstance(enum, list):
            values.update(str(value) for value in enum)
        for value in schema.values():
            values.update(_enum_values(value))
    elif isinstance(schema, list):
        for value in schema:
            values.update(_enum_values(value))
    return values


def _schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None)
    if not isinstance(schema, dict):
        raise AssertionError(f"{tool.name}: inputSchema is not an object")
    json.dumps(schema)
    return schema


def _validate_schemas(tools: dict[str, Any]) -> None:
    for tool in tools.values():
        _schema(tool)
        meta = getattr(tool, "meta", None) or getattr(tool, "_meta", None) or {}
        if meta.get("tool_contract") != TOOL_CONTRACT_ID:
            raise AssertionError(
                f"{tool.name}: missing tool-contract metadata {TOOL_CONTRACT_ID}"
            )

    search = _schema(tools["search_library"])
    properties = search.get("properties", {})
    missing = SEARCH_REQUIRED_PROPERTIES - set(properties)
    if missing:
        raise AssertionError(f"search_library schema missing {sorted(missing)}")
    if _enum_values(properties["match_mode"]) != MATCH_MODES:
        raise AssertionError("search_library match_mode enum is stale")
    if _enum_values(properties["mode"]) != RESPONSE_MODES:
        raise AssertionError("search_library mode enum is stale")
    if properties["context_chars"].get("default") != 60:
        raise AssertionError("search_library context_chars default must be 60")

    passage = _schema(tools["get_passage"])
    passage_properties = set(passage.get("properties", {}))
    if not {
        "match_id", "match_ids", "stable_id", "qasida_number",
        "include_parallels", "parallel_limit", "context_mode", "max_chars",
    }.issubset(passage_properties):
        raise AssertionError("get_passage schema is stale")
    if not {"projection", "book_ids", "include_legend"}.issubset(_schema(tools["list_books"]).get("properties",{})):
        raise AssertionError("list_books schema is stale")
    page = _schema(tools["get_page"])
    if page.get("properties", {}).get("max_chars", {}).get("default") != 20000:
        raise AssertionError("get_page max_chars default is stale")


def _structured(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        raise AssertionError(f"tool returned isError: {result}")
    value = getattr(result, "structuredContent", None)
    if value is None:
        value = getattr(result, "structured_content", None)
    if not isinstance(value, dict):
        raise AssertionError(f"tool returned no structured object: {result}")
    return value


async def _discover_all(session: ClientSession) -> list[Any]:
    discovered: list[Any] = []
    cursor = None
    while True:
        response = await session.list_tools(cursor=cursor)
        discovered.extend(response.tools)
        cursor = getattr(response, "nextCursor", None)
        if cursor is None:
            break
    return discovered


async def run(endpoint: str, discovery_only: bool = False) -> dict[str, Any]:
    health = await _validate_live_health(endpoint)
    local = urlsplit(endpoint).hostname in {"localhost", "127.0.0.1", "::1"}
    headers={'Authorization':'Bearer '+os.environ['MCP_MONITOR_API_KEY']} if os.environ.get('MCP_MONITOR_API_KEY') else None
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True, trust_env=not local,headers=headers) as client, \
            streamable_http_client(endpoint, http_client=client) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            if getattr(init.serverInfo, "version", None) != SERVER_VERSION:
                raise AssertionError(
                    "MCP initialize serverInfo.version mismatch: "
                    f"expected {SERVER_VERSION}, received "
                    f"{getattr(init.serverInfo, 'version', None)}"
                )
            discovered = await _discover_all(session)
            names = [tool.name for tool in discovered]
            validate_tool_names(names)
            if "get_passage" not in names:
                raise AssertionError("MCP-001 FAIL: get_passage is not discoverable")
            tools = {tool.name: tool for tool in discovered}
            _validate_schemas(tools)

            smoke: dict[str, str] = {}
            if not discovery_only:
                catalogue = _structured(await session.call_tool("list_books", {}))
                if catalogue.get("total") != 43:
                    raise AssertionError(
                        f"list_books smoke expected 43, received {catalogue.get('total')}"
                    )
                connector = catalogue.get("connector_contract") or {}
                if not (
                    connector.get("server_version") == SERVER_VERSION
                    and connector.get("tool_contract_version") == TOOL_CONTRACT_VERSION
                    and connector.get("tool_contract") == TOOL_CONTRACT_ID
                    and connector.get("tool_count") == 5
                    and connector.get("tools") == sorted(REQUIRED_TOOLS)
                    and connector.get("schema_digest") == SCHEMA_DIGEST
                ):
                    raise AssertionError("list_books MCP contract evidence is stale")
                # Compact catalogue intentionally omits the long repeated-page
                # register; compare the rest of the contract verbatim.
                expected_corpus = {k: v for k, v in health["corpus_contract"].items()
                                   if k != "repeated_printed_labels"}
                if catalogue.get("corpus_contract") != expected_corpus:
                    raise AssertionError("list_books corpus evidence differs from /health")
                smoke["list_books"] = "pass"

                catalogue_by_id = {
                    item.get("id"): item for item in catalogue.get("books") or []
                }
                b38 = catalogue_by_id.get("b38") or {}
                if not (
                    b38.get("canonical_book_id") == "b37"
                    and b38.get("edition_relation") == "duplicate_excerpt"
                    and b38.get("searchable_by_default") is False
                ):
                    raise AssertionError("list_books does not expose the b38->b37 edition policy")

                book = _structured(await session.call_tool("get_book", {"book_id": "b14"}))
                if (book.get("connector_contract") or {}).get("server_version") != SERVER_VERSION:
                    raise AssertionError("get_book does not expose the live connector version")
                b20 = _structured(await session.call_tool("get_book", {"book_id": "b20"}))
                b42 = _structured(await session.call_tool("get_book", {"book_id": "b42"}))
                if not (
                    b20.get("compiler") == "عبد الحميد بابكر"
                    and b20.get("attribution_confidence") == "high"
                    and b42.get("compiler") is None
                    and "do_not_assume_safwat" in (b42.get("provenance_status") or "")
                ):
                    raise AssertionError("live provenance policy is stale or speculative")
                smoke["get_book"] = "pass"
                smoke["provenance"] = "pass"

                search = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "المريد", "match_mode": "exact", "limit": 1,
                        "mode": "compact", "context_chars": 60,
                    },
                ))
                results = search.get("results") or []
                if not results:
                    raise AssertionError("search_library smoke returned no result")
                match_id = results[0].get("match_id") or results[0].get("m")
                if not match_id:
                    raise AssertionError("search_library smoke returned no match_id")
                smoke["search_library"] = "pass"

                edition_phrase = "عندما كنت أحشد الأجهزة الإعلامية المحلية و العالمية"
                canonical_search = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": edition_phrase, "match_mode": "exact",
                        "limit": 10, "mode": "compact", "context_chars": 60,
                        "ranking": "relevance",
                    },
                ))
                canonical_ids = {
                    item.get("book_id") for item in canonical_search.get("results") or []
                }
                if "b37" not in canonical_ids or "b38" in canonical_ids:
                    raise AssertionError(
                        f"default search did not suppress duplicate edition b38: {canonical_ids}"
                    )
                explicit_edition = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": edition_phrase, "book_ids": ["b38"],
                        "match_mode": "exact", "limit": 10,
                        "mode": "ultra_compact", "context_chars": 60,
                        "ranking": "relevance",
                    },
                ))
                from app.services.compact_response import decode_search_response
                edition_rows = decode_search_response(explicit_edition)["results"]
                if not edition_rows or any(
                    row.get("canonical_book_id") != "b37" or row.get("edition_relation") != "duplicate_excerpt"
                    for row in edition_rows
                ):
                    raise AssertionError("explicit b38 search lost canonical-edition metadata")
                smoke["edition_deduplication"] = "pass"

                scoped_census = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "الله", "book_ids": ["b14"],
                        "qasida_number": 91, "match_mode": "exact",
                        "include_counts": True, "limit": 20,
                        "mode": "compact", "context_chars": 60,
                    },
                ))
                if not (
                    scoped_census.get("returned_count") == 0
                    and scoped_census.get("literal_matching_pages") == 0
                    and scoped_census.get("literal_occurrences") == 0
                    and not scoped_census.get("suggestions")
                ):
                    raise AssertionError(
                        "qasida-scoped census leaked whole-book counts: "
                        f"{scoped_census}"
                    )
                smoke["qasida_scoped_counts"] = "pass"

                boundary_sir = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "سر", "book_ids": ["b13"],
                        "page_from": 97, "page_to": 97,
                        "match_mode": "exact", "whole_word": True,
                        "include_counts": True, "count_basis": "phrase",
                        "limit": 10, "mode": "compact", "ranking": "relevance",
                    },
                ))
                sir_rows = boundary_sir.get("results") or []
                if not sir_rows or "الي<mark>سر</mark>ى" in str(sir_rows):
                    raise AssertionError("whole-word سر regressed to substring highlighting")
                if boundary_sir.get("count_basis") != "phrase":
                    raise AssertionError("count basis is missing from live census")

                boundary_la = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "لا", "book_ids": ["b14"],
                        "page_from": 246, "page_to": 246,
                        "match_mode": "exact", "whole_word": True,
                        "limit": 10, "mode": "compact", "ranking": "relevance",
                    },
                ))
                if "ا<mark>لأ</mark>" in str(boundary_la):
                    raise AssertionError("safe normalization collapsed لا and لأ")
                smoke["whole_word_and_safe_normalization"] = "pass"

                exact_census = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "الحقيقة المحمدية", "match_mode": "exact",
                        "include_counts": True, "count_basis": "phrase",
                        "limit": 1, "mode": "compact", "ranking": "relevance",
                    },
                ))
                terms_census = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "الحقيقة المحمدية", "match_mode": "terms",
                        "include_counts": True, "count_basis": "phrase",
                        "limit": 1, "mode": "compact", "ranking": "relevance",
                    },
                ))
                if (
                    exact_census.get("census_matching_pages"),
                    exact_census.get("census_occurrences"),
                    exact_census.get("count_basis"),
                ) != (
                    terms_census.get("census_matching_pages"),
                    terms_census.get("census_occurrences"),
                    terms_census.get("count_basis"),
                ):
                    raise AssertionError("phrase counts changed with retrieval mode")
                smoke["mode_independent_counts"] = "pass"

                zero = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "أحكام زكاة الأنعام والماشية",
                        "book_ids": ["b14"], "match_mode": "auto",
                        "include_counts": True, "limit": 5,
                        "mode": "compact", "ranking": "relevance",
                    },
                ))
                diagnostics = zero.get("diagnostics") or {}
                if not (
                    zero.get("returned_count") == 0
                    and diagnostics.get("zero_result_is_not_absence_proof") is True
                    and diagnostics.get("per_term")
                    and diagnostics.get("attempted_modes") == ["exact", "terms", "hybrid", "reformulated"]
                ):
                    raise AssertionError("auto zero-result diagnostics are missing")
                smoke["auto_fallback_diagnostics"] = "pass"

                tier_limited = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "الله", "match_mode": "exact", "min_tier": 2,
                        "limit": 20, "mode": "compact", "ranking": "relevance",
                    },
                ))
                if not tier_limited.get("results") or any(
                    int(meta.get("tier", 99)) > 2
                    for meta in (tier_limited.get("books") or {}).values()
                ):
                    raise AssertionError("min_tier=2 leaked a lower-authority source")
                smoke["min_tier"] = "pass"

                full_page = _structured(await session.call_tool(
                    "get_page", {"book_id": "b44", "seq": 12, "mode": "compact"},
                ))
                if full_page.get("truncated") or full_page.get("full_chars", 0) < 8000:
                    raise AssertionError("get_page silently truncated b44 page 12")
                coordinates=full_page.get('coordinate_contract',{})
                if not (coordinates.get('representation_id')=='canonical-page-text-v1' and
                        coordinates.get('offset_unit')=='unicode_codepoint' and
                        coordinates.get('text_sha256')==hashlib.sha256(full_page['text'].encode()).hexdigest()):
                    raise AssertionError('get_page source-coordinate contract does not resolve to returned text')
                smoke["full_page_default"] = "pass"

                footnote_page = _structured(await session.call_tool(
                    "get_page", {"book_id": "b13", "seq": 97, "mode": "compact"},
                ))
                if "footnote" not in (footnote_page.get("content_types") or []):
                    raise AssertionError("page content typing lost explicit footnotes")
                smoke["content_typing"] = "pass"

                qasida = _structured(await session.call_tool(
                    "get_passage", {"qasida_number": 91},
                ))
                if not (
                    qasida.get("complete") is True
                    and qasida.get("returned_bayts") == 22
                    and qasida.get("prosody", {}).get("status") == "not_curated"
                    and not any(
                        "-242 -" in row.get("text", "")
                        or "-243 -" in row.get("text", "")
                        or "***----------------" in row.get("text", "")
                        for row in qasida.get("bayts") or []
                    )
                ):
                    raise AssertionError("full qasida retrieval is incomplete or misleading")
                smoke["full_qasida_context"] = "pass"

                parallel = _structured(await session.call_tool(
                    "get_passage",
                    {
                        "stable_id": "b14-q001-b007", "include_parallels": True,
                        "parallel_limit": 5,
                    },
                ))
                candidates = parallel.get("parallel_candidates") or []
                if not candidates or any(
                    row.get("review_status") != "unverified_candidate"
                    or row.get("citation_safe") is not False
                    for row in candidates
                ):
                    raise AssertionError("parallel candidates were presented as verified")
                smoke["parallel_safety"] = "pass"

                ultra_expansion = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "المريد", "match_mode": "auto", "limit": 6,
                        "expand_top": 2, "expand_chars": 500,
                        "mode": "ultra_compact", "context_chars": 60,
                    },
                ))
                ultra_rows = decode_search_response(ultra_expansion)["results"]
                if sum("expanded_passage" in row for row in ultra_rows) != 2:
                    raise AssertionError(
                        "ultra_compact silently dropped requested expansions"
                    )
                if not ultra_rows or any(
                    row.get("block_type") not in {"body", "toc"} for row in ultra_rows
                ):
                    raise AssertionError(
                        "ultra_compact did not expose block_type under blk"
                    )
                smoke["ultra_compact_expansion"] = "pass"

                ultra_toc = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "مرتبة الإنسان الكامل", "book_ids": ["b12"],
                        "include_toc": True,
                        "match_mode": "exact", "ranking": "relevance",
                        "limit": 10, "mode": "ultra_compact",
                        "context_chars": 60,
                    },
                ))
                toc_by_seq = {
                    row["seq"]: row for row in decode_search_response(ultra_toc)["results"]
                }
                if not (
                    toc_by_seq.get(255, {}).get("block_type") == "body"
                    and toc_by_seq.get(271, {}).get("block_type") == "toc"
                ):
                    raise AssertionError(
                        "ultra_compact blk failed the live body/TOC control"
                    )
                smoke["ultra_compact_block_type"] = "pass"

                complete_paragraph = _structured(await session.call_tool(
                    "get_passage", {
                        "match_id": match_id, "context_mode": "paragraph",
                        "max_chars": 12000,
                    },
                ))
                if complete_paragraph.get("context_scope") != "complete_paragraph":
                    raise AssertionError("complete paragraph retrieval was not honored")
                smoke["get_passage"] = "pass"

                _structured(await session.call_tool(
                    "get_page", {"book_id": "b14", "seq": 1, "mode": "ultra_compact"},
                ))
                smoke["get_page"] = "pass"

            return {
                "MCP-000": "pass",
                "MCP-001": "pass",
                "endpoint": endpoint,
                "tool_contract": TOOL_CONTRACT_ID,
                "expected_tools": sorted(REQUIRED_TOOLS),
                "discovered_tools": names,
                "smoke": smoke,
                "server_name": getattr(init.serverInfo, "name", None),
                "server_version": getattr(init.serverInfo, "version", None),
                "health": {
                    "server_version": health["server_version"],
                    "tool_contract_version": health["tool_contract_version"],
                    "corpus_status": health["corpus_contract"]["status"],
                    "diwan": health["corpus_contract"]["diwan"],
                    "research_indexes": health["corpus_contract"]["research_indexes"],
                },
            }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "endpoint", nargs="?",
        default=os.environ.get("BURHANIYA_MCP_URL", "https://burhaniya-library-backend.onrender.com/mcp/"),
    )
    parser.add_argument("--discovery-only", action="store_true")
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args.endpoint, args.discovery_only))
    except Exception as exc:
        print(json.dumps({"MCP-000": "fail", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
