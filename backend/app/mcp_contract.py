"""Immutable public contract for the Al Burhania MCP surface."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


SERVER_VERSION = "2.3.2"
TOOL_CONTRACT_VERSION = "5.3"
TOOL_CONTRACT_ID = "alburhaniya-tools-v5"

REQUIRED_TOOLS = frozenset({
    "search_library",
    "get_passage",
    "get_page",
    "get_book",
    "list_books",
})

TOOL_META: dict[str, str | int] = {
    "server_version": SERVER_VERSION,
    "tool_contract_version": TOOL_CONTRACT_VERSION,
    "tool_contract": TOOL_CONTRACT_ID,
    "tool_count": len(REQUIRED_TOOLS),
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
        "server_version": SERVER_VERSION,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "tool_contract": TOOL_CONTRACT_ID,
        "tool_count": len(actual),
        "tools": list(actual),
    }
