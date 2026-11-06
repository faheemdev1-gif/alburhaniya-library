"""Isolate optional parallel test workers from shared runtime cache files."""
import os
from pathlib import Path
import tempfile


def pytest_configure(config):
    if not hasattr(config, 'workerinput'):
        return
    state = Path(tempfile.mkdtemp(prefix='burhaniya-tests-' + config.workerinput['workerid'] + '-'))
    os.environ['RESULT_CACHE_PATH'] = str(state / 'results.sqlite3')
    os.environ['TRAFFIC_METRICS_PATH'] = str(state / 'traffic.sqlite3')
    os.environ['MONITOR_SUMMARY_PATH'] = str(state / 'monitor-history.json')
