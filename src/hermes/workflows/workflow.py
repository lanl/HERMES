from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from hermes.runner.analysis.hermes.event_reconstruction import (
    derive_summary_path as derive_event_reconstruction_summary_path,
)
from hermes.runner.analysis.hermes.photon_reconstruction import (
    derive_summary_path as derive_reconstruction_summary_path,
)
from hermes.runner.analysis.hermes.unpacker import (
    derive_summary_path as derive_unpacker_summary_path,
)
from hermes.runner.analysis.run import run_analysis
from hermes.logging import configure_logging
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
from hermes.state.models.shared_models import FileReference, utc_now
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_io import save_hermes_record_to_yaml
from hermes.state_service.state_manager import StateManager

_WORKFLOW_LOGGER = logger.bind(domain="workflow")

# A finished analysis step records "completed"/"skipped"/"failed"; the workflow
# log reports a completed step as "success".
_STAGE_STATUS = {"completed": "success", "skipped": "skipped", "failed": "failed"}


def _relative(path: Path) -> str:
    """Write a path relative to the current directory when it sits underneath it.

    Input files named relative to the current directory and outputs resolved to
    absolute paths then read the same in the log: a path within the current
    directory becomes a relative string, and any path outside it is left as-is.
    """
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


class Workflow:
    """Run HERMES operations against one measurement record."""

    def __init__(self, record: HermesRecord) -> None:
        log_dir = record.environment.log_directory.resolved_path
        configure_logging(log_dir, level=record.environment.log_level)
        self._state_manager = StateManager(
            record,
            config=StateServiceConfig(allow_trusted_workflow_bypass=True),
        )
        _WORKFLOW_LOGGER.info(
            "Initialized HERMES workflow for measurement {measurement_id}, "
            "run {run}",
            event_type="workflow.initialized",
            measurement_id=record.measurement_info.measurement_id,
            run=record.measurement_info.run,
        )

    def run_analysis(self, *, overwrite: bool = False) -> list[FileReference]:
        return run_analysis(
            self._state_manager,
            overwrite=overwrite,
        )

    def run_acquisition(self) -> None:
        """Reserve the acquisition entry point until acquisition is implemented."""
        raise NotImplementedError("HERMES acquisition is not implemented")

    def run(self) -> HermesRecord:
        """Run the work the record configures and return the updated record.

        Analysis-only records run analysis, save the record, and write the
        workflow log. Acquisition-only records raise NotImplementedError.
        A record configuring both, or neither, raises ValueError.
        """
        record = self._state_manager.get_state()
        if record.acquisition is None and record.analysis is None:
            raise ValueError(
                "the record configures neither acquisition nor analysis to run"
            )
        if record.acquisition is not None and record.analysis is None:
            self.run_acquisition()
        if record.analysis is not None and record.acquisition is None:
            self.run_analysis()
        if record.acquisition is not None and record.analysis is not None:
            raise ValueError(
                "the record configures both acquisition and analysis to run, "
                "which is not supported"
            )
        self._save_record()
        self._write_workflow_log()
        return self.record

    def _run_directory(self) -> Path:
        """The run directory holds one run's outputs; fall back to working dir."""
        record = self._state_manager.get_state()
        return (
            record.environment.run_directory.resolved_path
            or record.environment.working_directory.resolved_path
        )

    def _save_record(self) -> None:
        """Write the final record to HERMES_record.yaml in the run directory."""
        record = self._state_manager.get_state()
        save_hermes_record_to_yaml(
            record, self._run_directory() / "HERMES_record.yaml"
        )

    def _write_workflow_log(self) -> None:
        """Write the run's workflow log to <log_directory>/HERMES-workflow.jsonl (or the run directory if unset).

        The log is one JSON object per line: the record file that started the
        run, the stages the run configured, one line per finished analysis step,
        and a closing line. Paths are written relative to the current directory
        so the log reads the same wherever the run directory sits. The file is
        rewritten from scratch on every run.
        """
        record = self._state_manager.get_state()
        record_path = self._run_directory() / "HERMES_record.yaml"
        stages = self._configured_stages()
        now = utc_now().isoformat()

        lines = [
            {
                "event": "HERMES_record_initialized",
                "record": _relative(record_path),
                "time": now,
            },
            {"event": "workflow_initialized", "stages": stages, "time": now},
        ]
        lines.extend(self._stage_completed_lines())
        lines.append(
            {"event": "workflow_completed", "stages": stages, "time": now}
        )

        log_dir = (
            record.environment.log_directory.resolved_path
            or self._run_directory()
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "HERMES-workflow.jsonl"
        log_file.write_text(
            "".join(json.dumps(line) + "\n" for line in lines)
        )

    def _configured_stages(self) -> list[str]:
        """The analysis steps the record asked this run to perform, in order."""
        analysis = self._state_manager.get_state().analysis
        if not isinstance(analysis, HermesTpx3AnalysisState):
            return []
        stages: list[str] = []
        if analysis.unpacking is not None:
            stages.append("unpacking")
        if analysis.photon_reconstruction is not None:
            stages.append("reconstruction")
        if analysis.event_reconstruction is not None:
            stages.append("event_reconstruction")
        return stages

    def _stage_completed_lines(self) -> list[dict]:
        """One log line per finished analysis step, in stage then file order."""
        analysis = self._state_manager.get_state().analysis
        if not isinstance(analysis, HermesTpx3AnalysisState):
            return []
        analysis_root = (
            self._state_manager.get_state()
            .environment.analysis_directory.resolved_path
        )
        now = utc_now().isoformat()
        lines: list[dict] = []

        if analysis.unpacking is not None:
            for result in analysis.unpacking.results:
                summary = derive_unpacker_summary_path(
                    analysis_root, result.input_file
                )
                lines.append(
                    self._stage_line(
                        "unpacking", result.input_file.path, result.status,
                        summary, now,
                    )
                )
        if analysis.photon_reconstruction is not None:
            for result in analysis.photon_reconstruction.results:
                summary = derive_reconstruction_summary_path(
                    analysis_root, result.input_file
                )
                lines.append(
                    self._stage_line(
                        "reconstruction",
                        result.input_file.path,
                        result.status,
                        summary,
                        now,
                    )
                )
        if analysis.event_reconstruction is not None:
            for result in analysis.event_reconstruction.results:
                summary = derive_event_reconstruction_summary_path(
                    analysis_root, result.raw_file_stem
                )
                lines.append(
                    self._stage_line(
                        "event_reconstruction", result.output_file,
                        result.status, summary, now,
                    )
                )
        return lines

    @staticmethod
    def _stage_line(
        stage: str, input_file: Path, status: str, summary: Path, now: str
    ) -> dict:
        return {
            "event": "stage_completed",
            "stage": stage,
            "file": _relative(input_file),
            "status": _STAGE_STATUS.get(status, status),
            "start": now,
            "stop": now,
            "summary": _relative(summary),
        }

    @property
    def record(self) -> HermesRecord:
        return self._state_manager.get_state()
