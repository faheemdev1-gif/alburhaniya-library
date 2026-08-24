#!/usr/bin/env python3
"""Add or rebuild the audited token and Dīwān-parallel candidate indexes."""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from research_indexes import build_research_indexes


ROOT = Path(__file__).resolve().parent.parent


def migrate(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        stats = build_research_indexes(conn)
        conn.commit()
        return stats
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db", default=os.environ.get("LIBRARY_DB_PATH", str(ROOT / "library.db")),
    )
    args = parser.parse_args()
    print(migrate(Path(args.db)))


if __name__ == "__main__":
    main()
