from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes.runner.acquisition.serval import server as server_module
from hermes.runner.acquisition.serval.client import ServalClientError
from hermes.runner.acquisition.serval.server import (
    ServalServerError,
    _build_launch_command,
    start_serval,
    stop_serval,
    wait_until_ready,
)
from hermes.state.models.acquisition.serval import ServalServer


JAR = "/opt/serval/serv.jar"


@pytest.mark.parametrize(
    ("server", "expected_flags"),
    [
        (
            ServalServer(
                url="http://localhost:8080",
                program_path=JAR,
                version="3.3.0",
                tcp_ip="192.168.100.1",
                tcp_port=50000,
            ),
            ["--tcpIp", "192.168.100.1", "--tcpPort", "50000"],
        ),
        (
            ServalServer(
                url="http://localhost:8080",
                program_path=JAR,
                version="3.3.0",
                tcp_ip="192.168.100.1",
            ),
            ["--tcpIp", "192.168.100.1"],
        ),
        (
            ServalServer(
                url="http://localhost:8080",
                program_path=JAR,
                version="3.3.0",
            ),
            [],
        ),
        (
            ServalServer(
                url="http://localhost:8080",
                program_path=JAR,
                tcp_ip="10.0.0.5",
            ),
            ["--tcpIp", "10.0.0.5"],
        ),
    ],
)
def test_build_launch_command_flags_follow_version(
    server: ServalServer,
    expected_flags: list[str],
) -> None:
    assert _build_launch_command(server) == ["java", "-jar", JAR, *expected_flags]


def test_start_serval_requires_program_path() -> None:
    server = ServalServer(url="http://localhost:8080")
    with pytest.raises(ServalServerError, match="program_path"):
        start_serval(server, Path("/tmp/does-not-matter"))


def test_start_serval_requires_existing_jar(tmp_path: Path) -> None:
    server = ServalServer(
        url="http://localhost:8080",
        program_path=str(tmp_path / "missing.jar"),
    )
    with pytest.raises(ServalServerError, match="not found"):
        start_serval(server, tmp_path / "logs")


def test_start_serval_launches_and_writes_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jar = tmp_path / "serv.jar"
    jar.write_bytes(b"")
    log_dir = tmp_path / "logs"
    server = ServalServer(url="http://localhost:8080", program_path=str(jar))

    recorded: dict[str, object] = {}

    class _FakePopen:
        def __init__(self, command, stdout, stderr):
            recorded["command"] = command
            recorded["has_stdout"] = stdout is not None
            recorded["stderr"] = stderr

    monkeypatch.setattr(server_module.subprocess, "Popen", _FakePopen)

    process = start_serval(server, log_dir)

    assert isinstance(process, _FakePopen)
    assert recorded["command"] == ["java", "-jar", str(jar)]
    assert recorded["stderr"] == subprocess.STDOUT
    assert (log_dir / "serval-server.log").exists()


class _FakeReadyClient:
    """Answers /dashboard after a set number of not-ready attempts."""

    def __init__(self, ready_after: int, version: str = "3.3.0") -> None:
        self.base_url = "http://serval.test"
        self._attempts = 0
        self._ready_after = ready_after
        self._version = version

    def get(self, path: str):
        assert path == "/dashboard"
        self._attempts += 1
        if self._attempts <= self._ready_after:
            raise ServalClientError("not up yet")

        class _Response:
            def __init__(self, version: str) -> None:
                self._version = version

            def json(self) -> dict:
                return {"Server": {"SoftwareVersion": self._version}}

        return _Response(self._version)


def test_wait_until_ready_returns_version_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_module.time, "sleep", lambda _seconds: None)
    client = _FakeReadyClient(ready_after=2)

    version = wait_until_ready(client, timeout_s=5.0)

    assert version == "3.3.0"


def test_wait_until_ready_raises_on_timeout() -> None:
    client = _FakeReadyClient(ready_after=1_000_000)
    with pytest.raises(ServalServerError, match="did not become ready"):
        wait_until_ready(client, timeout_s=0.0)


class _FakeProcess:
    def __init__(self, wait_timeouts: int = 0, returncode: int = 0) -> None:
        self._wait_timeouts = wait_timeouts
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self._wait_timeouts > 0:
            self._wait_timeouts -= 1
            raise subprocess.TimeoutExpired(cmd="serval", timeout=timeout)
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class _FakeShutdownClient:
    def __init__(self, *, shutdown_ok: bool = True) -> None:
        self.base_url = "http://serval.test"
        self._shutdown_ok = shutdown_ok
        self.calls: list[str] = []

    def get(self, path: str):
        self.calls.append(path)
        if not self._shutdown_ok:
            raise ServalClientError("connection dropped")
        return None


def test_stop_serval_requests_shutdown_and_returns_exit_code() -> None:
    client = _FakeShutdownClient()
    process = _FakeProcess(returncode=0)

    exit_code = stop_serval(client, process, timeout_s=1.0)

    assert client.calls == ["/server/shutdown"]
    assert exit_code == 0
    assert not process.terminated


def test_stop_serval_terminates_when_process_lingers() -> None:
    client = _FakeShutdownClient(shutdown_ok=False)
    process = _FakeProcess(wait_timeouts=1, returncode=143)

    exit_code = stop_serval(client, process, timeout_s=1.0)

    assert process.terminated
    assert not process.killed
    assert exit_code == 143
