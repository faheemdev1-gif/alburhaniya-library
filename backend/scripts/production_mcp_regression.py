#!/usr/bin/env python3
"""Post-deployment MCP-000/MCP-001 discovery and execution hard gate."""
from __future__ import annotations

import argparse
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

from app.mcp_contract import (
    REQUIRED_TOOLS,
    SERVER_VERSION,
    TOOL_CONTRACT_ID,
    TOOL_CONTRACT_VERSION,
    validate_tool_names,
)


SEARCH_REQUIRED_PROPERTIES = {
    "query", "queries", "operator", "book_scope", "book_ids",
    "include_counts", "qasida_number", "expand_top", "expand_chars",
    "min_score", "match_mode", "mode", "context_chars", "ranking",
}
MATCH_MODES = {"auto", "exact", "terms", "hybrid", "lexeme"}
RESPONSE_MODES = {"compact", "ultra_compact"}


async def _validate_live_health(endpoint: str) -> dict[str, Any]:
    parts = urlsplit(endpoint)
    health_url = urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
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
    if not (
        corpus.get("status") == "ok"
        and diwan.get("qasidas") == 95
        and diwan.get("bayts") == 2682
        and diwan.get("continuous_bayt_numbering") is True
        and research.get("status") == "ok"
        and research.get("parallel_semantics") == "unverified_candidates_only"
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
    if not {"match_id", "match_ids"}.issubset(passage_properties):
        raise AssertionError("get_passage must expose match_id and match_ids")


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
    async with streamable_http_client(endpoint) as (read_stream, write_stream, _):
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
                if catalogue.get("connector_contract") != {
                    "server_version": SERVER_VERSION,
                    "tool_contract_version": TOOL_CONTRACT_VERSION,
                    "tool_contract": TOOL_CONTRACT_ID,
                    "tool_count": 5,
                    "tools": sorted(REQUIRED_TOOLS),
                }:
                    raise AssertionError("list_books MCP contract evidence is stale")
                if catalogue.get("corpus_contract") != health["corpus_contract"]:
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
                smoke["get_book"] = "pass"

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
                edition_rows = explicit_edition.get("results") or []
                if not edition_rows or any(
                    row.get("canon") != "b37" or row.get("er") != "duplicate_excerpt"
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
                    and scoped_census.get("total_hits") == 0
                    and scoped_census.get("total_occurrences") == 0
                    and not scoped_census.get("suggestions")
                ):
                    raise AssertionError(
                        "qasida-scoped census leaked whole-book counts: "
                        f"{scoped_census}"
                    )
                smoke["qasida_scoped_counts"] = "pass"

                ultra_expansion = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "المريد", "match_mode": "auto", "limit": 6,
                        "expand_top": 2, "expand_chars": 500,
                        "mode": "ultra_compact", "context_chars": 60,
                    },
                ))
                ultra_rows = ultra_expansion.get("results") or []
                if sum("ep" in row for row in ultra_rows) != 2:
                    raise AssertionError(
                        "ultra_compact silently dropped requested expansions"
                    )
                if not ultra_rows or any(
                    row.get("blk") not in {"body", "toc"} for row in ultra_rows
                ):
                    raise AssertionError(
                        "ultra_compact did not expose block_type under blk"
                    )
                smoke["ultra_compact_expansion"] = "pass"

                ultra_toc = _structured(await session.call_tool(
                    "search_library",
                    {
                        "query": "مرتبة الإنسان الكامل", "book_ids": ["b12"],
                        "match_mode": "exact", "ranking": "relevance",
                        "limit": 10, "mode": "ultra_compact",
                        "context_chars": 60,
                    },
                ))
                toc_by_seq = {
                    row.get("s"): row for row in ultra_toc.get("results") or []
                }
                if not (
                    toc_by_seq.get(255, {}).get("blk") == "body"
                    and toc_by_seq.get(271, {}).get("blk") == "toc"
                ):
                    raise AssertionError(
                        "ultra_compact blk failed the live body/TOC control"
                    )
                smoke["ultra_compact_block_type"] = "pass"

                _structured(await session.call_tool(
                    "get_passage", {"match_id": match_id, "context_chars": 300},
                ))
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
