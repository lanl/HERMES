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
from hermes.runner.acquisition.serval.run import run_serval_acquisition
from hermes.runner.analysis.run import run_analysis
from hermes.logging import configure_logging
from hermes.state.models.acquisition.serval import ServalAcquisitionResult
from hermes.state.models.analysis.hermes_tpx3_spidr import HermesTpx3AnalysisState
from hermes.state.models.shared_models import FileReference, utc_now
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_io import save_hermes_record_to_yaml
from hermes.state_service.state_manager import StateManager

_WORKFLOW_LOGGER = logger.bind(domain="workflow")

# A finished analysis step records "completed"/"skipped"/"failed"; the workflow
# log reports a completed step, or a completed acquisition, as "success". Any
# other acquisition status ("configured", "stopped", ...) is written as-is.
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
        """Run the SERVAL acquisition the record configures."""
        run_serval_acquisition(self._state_manager)

    def run(self) -> HermesRecord:
        """Run the work the record configures and return the updated record.

        Analysis-only records run analysis; acquisition-only records run the
        SERVAL acquisition. A record configuring both records while it acquires:
        the acquisition unpacks each raw file as SERVAL finishes it, then a final
        analysis pass picks up anything the last frames left. That pass also
        runs after a failed acquisition, with a warning that the raw files may
        be incomplete. Either way the record is saved and the workflow log
        written, also when Ctrl-C or an error ends the run early; the error is
        then raised again. A record configuring neither raises ValueError.
        """
        record = self._state_manager.get_state()
        if record.acquisition is None and record.analysis is None:
            raise ValueError(
                "the record configures neither acquisition nor analysis to run"
            )
        error: BaseException | None = None
        try:
            if record.acquisition is not None:
                self.run_acquisition()
            if record.analysis is not None:
                acquisition = self.record.acquisition
                if acquisition is not None and acquisition.status == "failed":
                    result = acquisition.result or ServalAcquisitionResult()
                    _WORKFLOW_LOGGER.warning(
                        "The acquisition failed ({stop_reason}); analyzing the "
                        "raw files it wrote, which may be incomplete",
                        event_type="workflow.analysis_after_failed_acquisition",
                        stop_reason=result.stop_reason,
                        errors=result.errors,
                    )
                self.run_analysis()
        except BaseException as caught:
            error = caught
            if isinstance(caught, KeyboardInterrupt):
                _WORKFLOW_LOGGER.warning(
                    "Workflow stopped by Ctrl-C; saving the record",
                    event_type="workflow.stopped",
                )
            else:
                _WORKFLOW_LOGGER.error(
                    "Workflow failed: {error_type}: {error}; saving the record",
                    event_type="workflow.failed",
                    error_type=type(caught).__name__,
                    error=str(caught),
                )
            raise
        finally:
            self._save_record()
            self._write_workflow_log(error)
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

    def _write_workflow_log(self, error: BaseException | None = None) -> None:
        """Write the run's workflow log to <log_directory>/HERMES-workflow.jsonl (or the run directory if unset).

        The log is one JSON object per line: the record file that started the
        run, the stages the run configured, one line for the acquisition when
        one is configured, one line per finished analysis step, and a closing
        line. The closing line is `workflow_stopped` when Ctrl-C ended the run;
        `workflow_failed` when an error ended it (with the error) or any stage
        ended `failed` (listed in `failed_stages`); and `workflow_completed`
        otherwise. Paths are written relative to the current directory so the
        log reads the same wherever the run directory sits. The file is
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
        stage_lines = self._acquisition_lines() + self._stage_completed_lines()
        lines.extend(stage_lines)
        failed_stages = list(
            dict.fromkeys(
                line["stage"] for line in stage_lines if line["status"] == "failed"
            )
        )
        if isinstance(error, KeyboardInterrupt):
            lines.append(
                {"event": "workflow_stopped", "stages": stages, "time": now}
            )
        elif error is not None or failed_stages:
            failed_line = {
                "event": "workflow_failed",
                "stages": stages,
                "failed_stages": failed_stages,
            }
            if error is not None:
                failed_line["error"] = f"{type(error).__name__}: {error}"
            failed_line["time"] = now
            lines.append(failed_line)
        else:
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
        """The steps the record asked this run to perform, in order."""
        record = self._state_manager.get_state()
        stages: list[str] = []
        if record.acquisition is not None:
            stages.append("acquisition")
        analysis = record.analysis
        if not isinstance(analysis, HermesTpx3AnalysisState):
            return stages
        if analysis.unpacking is not None:
            stages.append("unpacking")
        if analysis.photon_reconstruction is not None:
            stages.append("reconstruction")
        if analysis.event_reconstruction is not None:
            stages.append("event_reconstruction")
        return stages

    def _acquisition_lines(self) -> list[dict]:
        """The acquisition's log line, when the record configures one.

        The line carries the acquisition status, why the measurement stopped,
        SERVAL's frame counts, and any errors, so the log shows a failed
        acquisition without opening the record. A status of `planned` means the
        acquisition ended before it recorded a status. Runs that take no
        measurement (connect-only or configure-only) leave the measurement
        fields empty, and their start and stop are the time the log is written.
        """
        acquisition = self._state_manager.get_state().acquisition
        if acquisition is None:
            return []
        result = acquisition.result or ServalAcquisitionResult()
        now = utc_now()
        return [
            {
                "event": "stage_completed",
                "stage": "acquisition",
                "status": _STAGE_STATUS.get(
                    acquisition.status, acquisition.status
                ),
                "stop_reason": result.stop_reason,
                "frames": result.frames,
                "dropped_frames": result.dropped_frames,
                "errors": result.errors,
                "start": (result.started_at or now).isoformat(),
                "stop": (result.completed_at or now).isoformat(),
            }
        ]

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
