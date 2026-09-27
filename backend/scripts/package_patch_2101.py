#!/usr/bin/env python3
"""Package the 2.10.1 source patch while proving raw corpus bytes are intact."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "__pycache__", ".pytest_cache"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def included(path):
    parts = path.relative_to(ROOT).parts
    return (path.is_file() and not any(p in EXCLUDED or p.startswith("._") for p in parts)
            and path.name not in {"library.db", ".env"}
            and not path.name.startswith(("library.db-", ".library.db."))
            and path.suffix not in {".zip", ".pyc", ".log"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    original = Path(args.original)
    output = Path(args.output)
    changed = []
    with zipfile.ZipFile(original) as source:
        for item in source.infolist():
            if item.is_dir():
                continue
            rel = Path(*Path(item.filename).parts[1:])
            local = ROOT / rel
            if not local.is_file():
                raise RuntimeError(f"Original file missing: {rel}")
            if sha(local.read_bytes()) != sha(source.read(item)):
                if rel.parts[:2] in {("data", "raw_htm"), ("data", "raw_utf8")} or rel == Path("data/mapping.json"):
                    raise RuntimeError(f"Raw corpus changed: {rel}")
                changed.append(str(rel))
    files = sorted((p for p in ROOT.rglob("*") if included(p)), key=lambda p: str(p))
    manifest = {
        "server_version": "2.10.1",
        "tool_contract_version": "12.0",
        "original_sha256": sha(original.read_bytes()),
        "raw_corpus_bytes_unchanged": True,
        "changed_original_files": changed,
        "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size,
                   "sha256": sha(p.read_bytes())} for p in files],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = "Al_Burhaniya_Connector_2.10.1/"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, prefix + path.relative_to(ROOT).as_posix())
        archive.writestr(prefix + "RELEASE_MANIFEST_2101.json",
                         json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive integrity failed")
    print(json.dumps({"output": str(output), "bytes": output.stat().st_size,
                      "sha256": sha(output.read_bytes()), "files": len(files) + 1,
                      "changed_original_files": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
