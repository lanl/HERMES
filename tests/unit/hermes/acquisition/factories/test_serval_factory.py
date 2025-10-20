from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from hermes.acquisition.factories import serval as factory
from hermes.acquisition.factories.serval import ServalClientHandle, ServalFactoryError
from hermes.acquisition.models.environment import ServalDeployment


class _DummyProcess:
    def __init__(self) -> None:
        self.pid = 1337
        self.stdout = None
        self._terminated = False
        self._killed = False

    def poll(self) -> Optional[int]:
        return 0 if self._terminated else None

    def terminate(self) -> None:
        self._terminated = True

    def wait(self, timeout: Optional[float] = None) -> int:  # noqa: ARG002 - timeout unused in dummy
        return 0

    def kill(self) -> None:
        self._killed = True


def _make_deployment(path: Path) -> ServalDeployment:
    return ServalDeployment(install_dir=str(path))


def test_create_client_without_autostart(tmp_path: Path) -> None:
    jar_path = tmp_path / "serv-2.1.6.jar"
    jar_path.write_text("jar")

    deployment = _make_deployment(tmp_path)

    handle = factory.create_serval_client(deployment, auto_start=False)
    assert isinstance(handle, ServalClientHandle)
    assert handle.process is None
    handle.close(stop_process=False)


def test_create_client_with_autostart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jar_path = tmp_path / "serv-2.1.6.jar"
    jar_path.write_text("jar")

    deployment = _make_deployment(tmp_path)

    dummy_process = _DummyProcess()
    captured = {}

    def fake_start(command, *, cwd, capture_output, env):  # noqa: ANN001 - duck typing for monkeypatch
        captured["command"] = list(command)
        captured["cwd"] = cwd
        captured["capture_output"] = capture_output
        captured["env"] = env
        return dummy_process, None

    monkeypatch.setattr(factory, "_start_serval_process", fake_start)
    monkeypatch.setattr(factory, "_wait_for_serval_ready", lambda *args, **kwargs: True)

    handle = factory.create_serval_client(
        deployment,
        jar_path=jar_path,
        extra_jvm_args=["-Xmx1G"],
        extra_serval_args=["--demo"],
        capture_output=False,
    )

    assert handle.process is dummy_process
    assert captured["command"][0] == "java"
    assert "-Xmx1G" in captured["command"]
    assert "--demo" in captured["command"]
    assert captured["cwd"] == jar_path.parent

    handle.close()
    assert dummy_process._terminated is True
    assert dummy_process._killed is False


def test_create_client_raises_when_no_jar_for_autostart(tmp_path: Path) -> None:
    deployment = _make_deployment(tmp_path)

    with pytest.raises(ServalFactoryError):
        factory.create_serval_client(deployment, auto_start=True)


def test_create_client_reports_missing_java(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    jar_path = tmp_path / "serv-2.1.6.jar"
    jar_path.write_text("jar")

    deployment = _make_deployment(tmp_path)

    def raise_file_not_found(*args, **kwargs):  # noqa: ANN001 - test helper
        raise FileNotFoundError()

    monkeypatch.setattr(factory, "_start_serval_process", raise_file_not_found)
    monkeypatch.setattr(factory, "_wait_for_serval_ready", lambda *args, **kwargs: True)

    with pytest.raises(ServalFactoryError) as excinfo:
        factory.create_serval_client(deployment, jar_path=jar_path)

    assert "Java executable" in str(excinfo.value)