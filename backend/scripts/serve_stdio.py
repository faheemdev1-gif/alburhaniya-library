#!/usr/bin/env python3
"""MCP stdio entry point for fresh-client/offline integration checks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.mcp_server import mcp
if __name__=='__main__':
    mcp.run(transport='stdio')
