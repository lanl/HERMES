from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import requests
from requests import Response
from requests.exceptions import RequestException

from hermes.acquisition.logger import logger
from hermes.acquisition.models.environment import ServalDeployment
from hermes.acquisition.services.serval import ServalHTTPService

DEFAULT_STARTUP_TIMEOUT = 30.0
DEFAULT_STARTUP_POLL_INTERVAL = 0.5
DEFAULT_REQUEST_TIMEOUT = 2.0


class ServalFactoryError(RuntimeError):
	"""Raised when creating a Serval client fails."""


@dataclass
class ServalClientHandle:
	"""Lifecycle helper returned by :func:`create_serval_client`."""

	deployment: ServalDeployment
	client: ServalHTTPService
	process: Optional[subprocess.Popen[str]] = None
	_log_thread: Optional[threading.Thread] = None

	def close(self, *, stop_process: bool = True, timeout: float = 5.0) -> None:
		"""Dispose the HTTP client and optionally terminate the process."""

		self.client.close()
		if stop_process and self.process is not None:
			_terminate_process(self.process, timeout=timeout)
		self.process = None

	def __enter__(self) -> ServalClientHandle:
		return self

	def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
		self.close()


def create_serval_client(
	deployment: ServalDeployment,
	*,
	auto_start: bool = True,
	jar_path: Optional[Path] = None,
	java_executable: str = "java",
	extra_jvm_args: Sequence[str] = (),
	extra_serval_args: Sequence[str] = (),
	env: Optional[Mapping[str, str]] = None,
	capture_output: bool = True,
	startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
	poll_interval: float = DEFAULT_STARTUP_POLL_INTERVAL,
	request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> ServalClientHandle:
	"""Create a Serval HTTP client and optionally launch the process.

	Parameters
	----------
	deployment:
		Deployment metadata describing host, port, and installation paths.
	auto_start:
		When true, attempt to launch the Serval JVM before constructing the
		client. When false, the factory assumes Serval is already running and
		merely returns the HTTP client wrapper.
	jar_path:
		Explicit path to the Serval executable jar. When omitted the factory
		searches ``deployment.install_dir`` for the default version.
	java_executable:
		Java binary used to launch Serval when ``auto_start=True``.
	extra_jvm_args / extra_serval_args:
		Additional command line arguments appended to the launch command.
	env:
		Optional environment variables to provide to the subprocess.
	capture_output:
		When true, redirect Serval stdout/stderr to the acquisition logger.
	startup_timeout:
		Maximum seconds to wait for the HTTP endpoint to become responsive.
	poll_interval:
		Delay between readiness probes while waiting for startup.
	request_timeout:
		Timeout applied to individual HTTP readiness probes and the resulting
		``ServalHTTPService`` instance.

	Returns
	-------
	ServalClientHandle
		Tuple-like object that exposes the HTTP client and, when Serval was
		spawned by the factory, the underlying subprocess handle.
	"""

	process: Optional[subprocess.Popen[str]] = None
	log_thread: Optional[threading.Thread] = None

	if auto_start:
		resolved_jar = jar_path or _resolve_jar_path(deployment)
		logger.debug("Resolved Serval jar at %s", resolved_jar)
		command = _build_launch_command(
			java_executable=java_executable,
			jar_path=resolved_jar,
			extra_jvm_args=list(extra_jvm_args),
			extra_serval_args=list(extra_serval_args),
		)
		try:
			process, log_thread = _start_serval_process(
				command,
				cwd=resolved_jar.parent,
				capture_output=capture_output,
				env=env,
			)
		except FileNotFoundError as exc:
			raise ServalFactoryError(
				f"Java executable '{java_executable}' was not found."
				" Provide a valid path via the 'java_executable' parameter."
			) from exc
		logger.info("Started Serval process (pid=%s) with command: %s", process.pid, command)

		if not _wait_for_serval_ready(
			deployment,
			timeout=startup_timeout,
			poll_interval=poll_interval,
			request_timeout=request_timeout,
		):
			logger.error("Serval failed to become ready within %.1f seconds", startup_timeout)
			if process is not None:
				_terminate_process(process, timeout=5.0)
			raise ServalFactoryError("Serval process did not become ready")

	client = ServalHTTPService(deployment, timeout=max(request_timeout, 1.0))
	return ServalClientHandle(deployment=deployment, client=client, process=process, _log_thread=log_thread)


def _resolve_jar_path(deployment: ServalDeployment) -> Path:
	install_dir = deployment.install_dir.path
	preferred = [install_dir / name for name in deployment.default_executable_names]
	wildcard_candidates = sorted(install_dir.glob("*.jar"))

	for candidate in preferred + wildcard_candidates:
		if candidate.exists() and candidate.is_file():
			return candidate

	raise ServalFactoryError(
		f"No Serval executable jar found in {install_dir.as_posix()} (checked {deployment.default_executable_names})"
	)


def _build_launch_command(
	*,
	java_executable: str,
	jar_path: Path,
	extra_jvm_args: Sequence[str],
	extra_serval_args: Sequence[str],
) -> list[str]:
	command = [java_executable]
	command.extend(extra_jvm_args)
	command.extend(["-jar", jar_path.as_posix()])
	command.extend(extra_serval_args)
	return command


def _start_serval_process(
	command: Sequence[str],
	*,
	cwd: Path,
	capture_output: bool,
	env: Optional[Mapping[str, str]],
) -> tuple[subprocess.Popen[str], Optional[threading.Thread]]:
	stdout = subprocess.PIPE if capture_output else None
	stderr = subprocess.STDOUT if capture_output else None

	process = subprocess.Popen(
		command,
		cwd=cwd.as_posix(),
		stdout=stdout,
		stderr=stderr,
		text=True,
		env=dict(env) if env is not None else None,
	)

	log_thread: Optional[threading.Thread] = None
	if capture_output and process.stdout is not None:
		log_thread = threading.Thread(
			target=_pipe_to_logger,
			args=(process.stdout,),
			daemon=True,
		)
		log_thread.start()

	return process, log_thread


def _pipe_to_logger(stream) -> None:
	for line in iter(stream.readline, ""):
		text = line.rstrip()
		if text:
			logger.info("[SERVAL] %s", text)


def _wait_for_serval_ready(
	deployment: ServalDeployment,
	*,
	timeout: float,
	poll_interval: float,
	request_timeout: float,
) -> bool:
	url = f"http://{deployment.host}:{deployment.port}/"
	deadline = time.monotonic() + max(timeout, 0.0)

	while time.monotonic() < deadline:
		try:
			response: Response = requests.get(url, timeout=request_timeout)
			if response.ok:
				return True
		except RequestException:
			pass
		time.sleep(max(poll_interval, 0.1))

	return False


def _terminate_process(process: subprocess.Popen[str], *, timeout: float) -> None:
	if process.poll() is not None:
		return

	process.terminate()
	try:
		process.wait(timeout=timeout)
		return
	except subprocess.TimeoutExpired:
		logger.warning("Serval process did not terminate after %.1f seconds; killing", timeout)
		process.kill()
		process.wait()


__all__ = ["ServalClientHandle", "ServalFactoryError", "create_serval_client"]