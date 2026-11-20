import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from app.services import monitoring
from scripts.monitor_connector import append_history


def test_outages_and_completed_calls_have_separate_denominators(tmp_path, monkeypatch):
    path = tmp_path / "samples.json"
    completed = {"timestamp": time.time(), "calls": 1, "successful": 1, "results": [{"ok": True, "ms": 12}]}
    path.write_text(json.dumps(completed))
    outage = {"timestamp": time.time(), "calls": 0, "successful": 0, "planned_calls": 2,
              "session_error": "ConnectError", "results": []}
    append_history(path, outage)
    monkeypatch.setattr(monitoring, "get_settings", lambda: SimpleNamespace(monitor_summary_path=str(path)))
    report = monitoring.monitoring_summary()
    assert report["success_rate_24h"] == 1
    assert report["scheduled_success_rate_24h"] == 1/3
    assert report["unattempted_calls_24h"] == 2
    assert report["session_errors_24h"] == 1


def test_overlapping_probes_preserve_all_observations(tmp_path):
    path = tmp_path / "samples.json"
    def write_probe(i):
        append_history(path, {"timestamp": time.time(), "probe": i})
    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(write_probe, range(30)))
    assert sorted(row["probe"] for row in json.loads(path.read_text())) == list(range(30))
