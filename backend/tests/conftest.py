"""Prepare search patterns and isolate parallel test workers' cache files."""

import os
import tempfile
from pathlib import Path


def pytest_configure(config):
    if not hasattr(config, "workerinput"):
        return

    worker_id = config.workerinput["workerid"]
    state = Path(tempfile.mkdtemp(prefix=f"burhaniya-tests-{worker_id}-"))
    os.environ["RESULT_CACHE_PATH"] = str(state / "results.sqlite3")
    os.environ["TRAFFIC_METRICS_PATH"] = str(state / "traffic.sqlite3")
    os.environ["MONITOR_SUMMARY_PATH"] = str(state / "monitor-history.json")


def pytest_sessionstart(session):
    from app.services.concept_links import prepare_patterns

    prepare_patterns()
