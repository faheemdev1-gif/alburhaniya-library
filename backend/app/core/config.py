from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # ── Primary search engine (default) ─────────────────────────────────
    # SQLite FTS5, baked into the Docker image at build time by
    # scripts/build_index.py. No external service, no persistent disk.
    library_db_path: str = "library.db"

    # If set, search-result links point at your deployed static site
    # (e.g. https://your-library.vercel.app) instead of this backend's
    # own /read/... pages. Leave blank to use the backend's own pages.
    static_site_base_url: str = ""

    # ── Legacy engines (kept, disabled by default) ──────────────────────
    # Only used if enable_legacy_meilisearch / enable_semantic_search are
    # switched back on — requires running the Meilisearch/Qdrant services
    # from docker-compose.yml, which the lean single-container Render
    # deploy does not include.
    enable_legacy_meilisearch: bool = False
    meili_url: str = "http://localhost:7700"
    meili_master_key: str = "changeme_in_production"
    qdrant_url: str = "http://localhost:6333"
    books_dir: str = "./books"
    cors_origins: str = "*"

    # Search tuning (legacy chunk-based engine only)
    chunk_size: int = 400          # characters per indexed chunk
    chunk_overlap: int = 80        # overlap between consecutive chunks
    hybrid_keyword_weight: float = 0.4
    hybrid_semantic_weight: float = 0.6
    default_result_limit: int = 2000

    # Dormant legacy Qdrant switch. The production semantic path below is
    # local and does not require Qdrant or persistent disk.
    enable_semantic_search: bool = False

    # Local E5 semantic index. It activates only when both artifacts exist;
    # otherwise auto mode falls back to the existing lexical cascade.
    enable_local_semantic_search: bool = False
    semantic_embeddings_path: str = "semantic_embeddings.npy"
    semantic_manifest_path: str = "semantic_manifest.json"
    semantic_min_score: float = 0.0
    semantic_candidate_pool: int = 50
    hybrid_min_relevance: float = 0.55
    # Bound broad lexical candidate scoring.  The final local evidence check
    # is CPU-heavy; 250 retains the audited prayer results (candidate ranks 4
    # and 49) without rescoring 500 pages on every request.
    hybrid_candidate_pool: int = 250

    # Meilisearch caps how many total hits a single query can return
    # (default 1000). Raised so a common word can return every matching
    # page across the whole library, not just the first page of results.
    meili_max_total_hits: int = 100_000

    # Model — MiniLM is 4x faster than large models on CPU, good Arabic support
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()
