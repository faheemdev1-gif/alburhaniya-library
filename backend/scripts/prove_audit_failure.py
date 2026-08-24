#!/usr/bin/env python3
"""Prove the independent corpus audit rejects a deliberately corrupted copy."""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from independent_corpus_audit import audit


def main() -> None:
    source = Path("library.db")
    if not source.is_file():
        raise SystemExit("library.db is missing; build the corpus first")

    with tempfile.TemporaryDirectory(prefix="burhaniya-negative-control-") as temp:
        broken = Path(temp) / "library-broken.db"
        shutil.copy2(source, broken)
        conn = sqlite3.connect(broken)
        try:
            conn.execute(
                "UPDATE bayts SET stable_id='deliberately-malformed-id' "
                "WHERE stable_id=(SELECT stable_id FROM bayts ORDER BY stable_id LIMIT 1)"
            )
            conn.commit()
        finally:
            conn.close()

        report = audit(broken)
        detected = (
            report.get("status") == "fail"
            and "deliberately-malformed-id" in report.get("malformed_stable_ids", [])
        )
        evidence = {
            "negative_control": "pass" if detected else "fail",
            "mutation": "one canonical bayt stable_id replaced",
            "audit_status": report.get("status"),
            "detected_malformed_ids": report.get("malformed_stable_ids", []),
            "audit_failures": report.get("failures", []),
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        if not detected:
            raise SystemExit("audit failed to reject the deliberately corrupted corpus")


if __name__ == "__main__":
    main()
