#!/usr/bin/env python3
"""Apply the v5 Dīwān source/structure correction to a prebuilt library.db."""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app" / "core"))
sys.path.insert(0, str(ROOT / "scripts"))

from arabic_utils import normalize_arabic  # noqa: E402
from build_index import _BAYT_NUMBER, validate_diwan_structure  # noqa: E402


_SOURCE_HEADING = re.compile(r"الْ?قَ?صِ?يدَ?ة\s+([^:<\n]{1,80})\s*:")
_NUMERIC_HEADING = re.compile(
    r"(الْ?قَ?صِ?يدَ?ة\s+)(?:رقم\s*)?[0-9٠-٩۰-۹]{1,3}(\s*:)"
)


def _source_ordinals(source_path: Path) -> list[str]:
    text = source_path.read_bytes().decode("windows-1256")
    values = [match.group(1).strip() for match in _SOURCE_HEADING.finditer(text)]
    values = [value for value in values if not re.search(r"قوافي|لها\s+ثلاث", value)]
    if len(values) != 95 or any(re.search(r"[0-9٠-٩۰-۹]", value) for value in values):
        raise RuntimeError(
            f"expected 95 written source ordinals, received {len(values)}"
        )
    return values


def migrate(db_path: Path, source_path: Path) -> dict[str, int]:
    ordinals = _source_ordinals(source_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    replaced = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        pages = conn.execute(
            "SELECT id, qasida_number, text FROM pages "
            "WHERE book_id='b14' ORDER BY seq"
        ).fetchall()
        for page in pages:
            qasida_number = page["qasida_number"]
            if not qasida_number or not _NUMERIC_HEADING.search(page["text"]):
                continue
            ordinal = ordinals[int(qasida_number) - 1]
            text, count = _NUMERIC_HEADING.subn(
                lambda match: f"{match.group(1)}{ordinal}{match.group(2)}",
                page["text"],
                count=1,
            )
            if count:
                conn.execute(
                    "UPDATE pages SET text=?, norm_text=? WHERE id=?",
                    (text, normalize_arabic(text, aggressive=True), page["id"]),
                )
                replaced += 1
        if replaced not in {0, 95}:
            raise RuntimeError(f"expected to restore 95 headings, restored {replaced}")

        conn.execute("DELETE FROM bayts WHERE book_id='b14'")
        for page in conn.execute(
            "SELECT id, qasida_number, text FROM pages "
            "WHERE book_id='b14' AND qasida_number IS NOT NULL ORDER BY seq"
        ):
            markers = list(_BAYT_NUMBER.finditer(page["text"]))
            for index, marker in enumerate(markers):
                number = int(marker.group(1))
                start = marker.start()
                end = markers[index + 1].start() if index + 1 < len(markers) else len(page["text"])
                bayt_text = page["text"][start:end].strip()
                stable_id = f"b14-q{int(page['qasida_number']):03d}-b{number:03d}"
                conn.execute(
                    "INSERT OR REPLACE INTO bayts "
                    "(stable_id, page_id, book_id, qasida_number, bayt_number, "
                    "start_char, end_char, text, norm_text) "
                    "VALUES (?, ?, 'b14', ?, ?, ?, ?, ?, ?)",
                    (
                        stable_id, page["id"], page["qasida_number"], number,
                        start, end, bayt_text,
                        normalize_arabic(bayt_text, aggressive=True),
                    ),
                )

        # pages_fts is an external-content FTS5 table; rebuild guarantees that
        # ordinal restoration and normalized text stay synchronized.
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        validate_diwan_structure(conn)
        total = conn.execute(
            "SELECT COUNT(*) FROM bayts WHERE book_id='b14'"
        ).fetchone()[0]
        conn.commit()
        return {"headings_restored": replaced, "qasidas": 95, "bayts": int(total)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("LIBRARY_DB_PATH", str(ROOT / "library.db")))
    parser.add_argument("--source", default=str(ROOT / "data" / "raw_htm" / "book_14.htm"))
    args = parser.parse_args()
    print(migrate(Path(args.db), Path(args.source)))


if __name__ == "__main__":
    main()
