"""
Legacy JSON registry used by the old Meilisearch-based ingestion pipeline
(app/services/ingestion.py). Only relevant if ENABLE_LEGACY_MEILISEARCH=true.
The default SQLite-FTS5 deployment does not use this.
"""
import json
from pathlib import Path


def _registry_path() -> Path:
    p = Path("/app/processed/registry.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_registry() -> dict[str, dict]:
    p = _registry_path()
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_registry(reg: dict):
    _registry_path().write_text(json.dumps(reg, ensure_ascii=False, indent=2))
