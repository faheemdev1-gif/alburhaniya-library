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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.mcp_contract import (
    REQUIRED_TOOLS,
    TOOL_CONTRACT_ID,
    validate_tool_names,
)


SEARCH_REQUIRED_PROPERTIES = {
    "query", "queries", "operator", "book_scope", "book_ids",
    "include_counts", "qasida_number", "expand_top", "expand_chars",
    "min_score", "match_mode", "mode", "context_chars", "ranking",
}
MATCH_MODES = {"auto", "exact", "terms", "hybrid", "lexeme"}
RESPONSE_MODES = {"compact", "ultra_compact"}


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
    async with streamable_http_client(endpoint) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
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
                smoke["list_books"] = "pass"

                _structured(await session.call_tool("get_book", {"book_id": "b14"}))
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
