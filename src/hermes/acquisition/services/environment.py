from __future__ import annotations

import re
import socket
import time
from pathlib import Path
from typing import Iterable, List, Optional, Pattern, Tuple

from pydantic import BaseModel, ConfigDict, Field

from hermes.acquisition.logger import logger
from hermes.acquisition.models.environment import (
    AcquisitionEnvironment,
    NetworkEndpoint,
    RunDirectoryLayout,
    ServalDeployment,
    ServalInstallationStatus,
)
from hermes.acquisition.services.base import ServiceHealthStatus

from hermes.acquisition.services.serval import ServalHTTPService

_SERVAL_VERSION_DIR_PATTERN = re.compile(r"\d+\.\d+\.\d+")

class EnvironmentStatus(BaseModel):
    """Structured report produced by :class:`EnvironmentService`."""

    environment_name: str = Field(..., description="Identifier of the acquisition environment.")
    endpoints: List[NetworkEndpoint] = Field(
        default_factory=list,
        description="Probed network endpoints with updated reachability metadata.",
    )
    run_layout: Optional[RunDirectoryLayout] = Field(
        default=None,
        description="Run directory layout prepared for the upcoming acquisition.",
    )
    serval_health: Optional[ServiceHealthStatus] = Field(
        default=None,
        description="Optional Serval health snapshot if a Serval service was probed.",
    )
    serval_installations: List[ServalInstallationStatus] = Field(
        default_factory=list,
        description="Discovered Serval installations and their available versions.",
    )

    model_config = ConfigDict(extra="forbid")


class EnvironmentService:
    """Side-effecting helpers for preparing HERMES acquisition environments."""

    def ensure_run_layout(
        self,
        environment: AcquisitionEnvironment,
        run_number: int,
        *,
        create_missing: bool = True,
    ) -> RunDirectoryLayout:
        """Compute and optionally materialize the directory layout for a run."""

        layout = environment.workspace.make_run_layout(run_number)
        if create_missing:
            self._ensure_directories(layout.required_directories)
        logger.debug("Prepared run layout at %s", layout.run_dir.path)
        return layout

    def probe_network(
        self,
        environment: AcquisitionEnvironment,
        *,
        timeout: float = 1.0,
    ) -> List[NetworkEndpoint]:
        """Probe camera and auxiliary endpoints defined in the environment."""

        probed: List[NetworkEndpoint] = []
        for endpoint in environment.all_endpoints:
            reachable, latency_ms, detail = self._probe_endpoint(endpoint.host, endpoint.port, timeout)
            if detail:
                logger.debug(
                    "Endpoint probe detail for %s:%s — %s",
                    endpoint.host,
                    endpoint.port or "-",
                    detail,
                )
            probed.append(
                endpoint.model_copy(
                    update={
                        "reachable": reachable,
                        "latency_ms": latency_ms,
                    }
                )
            )
        return probed

    def collect_status(
        self,
        environment: AcquisitionEnvironment,
        *,
        run_number: Optional[int] = None,
        timeout: float = 1.0,
    serval_service: Optional[ServalHTTPService] = None,
    ) -> EnvironmentStatus:
        """Gather a consolidated status report for an environment."""

        run_layout = None
        if run_number is not None:
            run_layout = self.ensure_run_layout(environment, run_number)

        endpoints = self.probe_network(environment, timeout=timeout)

        serval_health = None
        if serval_service is not None:
            serval_health = serval_service.health_check()

        installation_status = self._gather_serval_installation_status(environment)

        return EnvironmentStatus(
            environment_name=environment.name,
            endpoints=endpoints,
            run_layout=run_layout,
            serval_health=serval_health,
            serval_installations=installation_status,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_directories(self, directories: Iterable[Path]) -> None:
        for path in directories:
            path.mkdir(parents=True, exist_ok=True)
            logger.debug("Ensured directory exists: %s", path)

    def _probe_endpoint(
        self,
        host: str,
        port: Optional[int],
        timeout: float,
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Probe a single endpoint, returning reachability, latency, and optional detail."""

        if port is not None:
            return self._probe_via_socket(host, port, timeout)
        return self._probe_via_resolution(host)

    def _probe_via_socket(
        self,
        host: str,
        port: int,
        timeout: float,
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                latency_ms = (time.perf_counter() - start) * 1000.0
                return True, latency_ms, None
        except (OSError, socket.timeout) as exc:
            return False, None, str(exc)

    def _probe_via_resolution(self, host: str) -> Tuple[bool, Optional[float], Optional[str]]:
        start = time.perf_counter()
        try:
            socket.gethostbyname(host)
        except socket.gaierror as exc:
            return False, None, str(exc)
        latency_ms = (time.perf_counter() - start) * 1000.0
        return True, latency_ms, None

    def _gather_serval_installation_status(self, environment: AcquisitionEnvironment) -> List[ServalInstallationStatus]:
        deployment = environment.serval
        search_paths: List[Path] = []

        explicit_path = deployment.install_dir.path
        search_paths.append(explicit_path)

        default_path = Path("/opt/serval")
        if explicit_path != default_path:
            search_paths.append(default_path)

        pattern = self._compile_serval_pattern(deployment)

        statuses: List[ServalInstallationStatus] = []
        seen: set[Path] = set()
        for path in search_paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            statuses.append(self._inspect_serval_directory(resolved, deployment, pattern))

        return statuses

    def _inspect_serval_directory(
        self,
        directory: Path,
        deployment: ServalDeployment,
        pattern: Pattern[str],
    ) -> ServalInstallationStatus:
        exists = directory.exists()
        versions: set[str] = set()
        default_available = False

        if exists:
            search_roots: List[Path] = [directory]
            try:
                search_roots.extend(path for path in directory.iterdir() if path.is_dir())
            except (PermissionError, OSError):  # pragma: no cover - defensive guard
                pass

            for root in search_roots:
                for glob_pattern in deployment.executable_glob_patterns:
                    for jar_path in root.glob(glob_pattern):
                        match = pattern.search(jar_path.name)
                        if match:
                            version = match.group("version")
                            versions.add(version)
                            if version == deployment.default_version:
                                default_available = True

            for root in search_roots[1:]:
                if _SERVAL_VERSION_DIR_PATTERN.fullmatch(root.name):
                    versions.add(root.name)
                    if root.name == deployment.default_version and not default_available:
                        expected_names = deployment.executable_names_for(root.name)
                        if any((root / name).exists() for name in expected_names):
                            default_available = True

        sorted_versions = sorted(versions, key=_version_sort_key)

        return ServalInstallationStatus(
            path=directory,
            exists=exists,
            available_versions=sorted_versions,
            default_version=deployment.default_version,
            default_available=default_available,
        )

    def _compile_serval_pattern(self, deployment: ServalDeployment) -> Pattern[str]:
        prefixes = "|".join(re.escape(prefix) for prefix in deployment.executable_prefixes)
        if not prefixes:
            prefixes = "serv"
        pattern = rf"(?:{prefixes})-(?P<version>\d+\.\d+\.\d+)\.jar"
        return re.compile(pattern, re.IGNORECASE)


def _version_sort_key(version: str) -> Tuple[int, ...]:
    """Convert a semantic version string into a tuple for sorting."""

    parts = [int(part) for part in version.split(".") if part.isdigit()]
    return tuple(parts)


__all__ = ["EnvironmentService", "EnvironmentStatus", "ServalInstallationStatus"]
