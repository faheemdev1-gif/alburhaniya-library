"""Exercise the actual hosting entry point, including failure and shutdown."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "scripts/start_server.py"


@pytest.mark.parametrize("port", ["", "invalid", "0", "65536"])
def test_invalid_port_fails_clearly(port, tmp_path):
    result = subprocess.run(
        [sys.executable, str(LAUNCHER)], cwd=tmp_path,
        env={**os.environ, "PORT": port}, capture_output=True, text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Invalid PORT" in result.stderr


def test_missing_index_exits_instead_of_hiding_failure(tmp_path):
    missing = tmp_path / "missing.db"
    result = subprocess.run(
        [sys.executable, str(LAUNCHER)], cwd=tmp_path,
        env={**os.environ, "PORT": "18181", "LIBRARY_DB_PATH": str(missing),
             "ENABLE_LEGACY_MEILISEARCH": "false"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode != 0
    assert "library.db not found" in result.stderr
    assert not missing.exists()


def test_assigned_port_foreground_health_and_shutdown(tmp_path):
    with socket.socket() as sock:
        sock.bind(("0.0.0.0", 0))
        port = sock.getsockname()[1]
    with (tmp_path / "server.log").open("w+") as log:
        server = subprocess.Popen(
            [sys.executable, str(LAUNCHER)], cwd=tmp_path,
            env={**os.environ, "PORT": str(port), "LIBRARY_DB_PATH": "library.db",
                 "ENABLE_LEGACY_MEILISEARCH": "false"},
            stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 20
            with httpx.Client(trust_env=False, timeout=1) as client:
                while time.monotonic() < deadline:
                    assert server.poll() is None, "Server exited before readiness"
                    try:
                        response = client.get(f"http://127.0.0.1:{port}/health")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("Assigned port never became healthy")
                payload = response.json()
                assert payload["server_version"] == "2.10.5"
                assert payload["corpus_contract"]["status"] == "ok"
                # A successful request must not end the persistent process.
                assert client.get(f"http://127.0.0.1:{port}/health").status_code == 200
                assert server.poll() is None
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
                pytest.fail("Server did not handle SIGTERM")
        log.seek(0)
        output = log.read()
        assert f"0.0.0.0:{port}" in output
        assert "Library startup complete" in output
        assert "Application shutdown complete" in output
        assert "CancelledError" not in output
