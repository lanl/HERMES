from __future__ import annotations

from pathlib import Path

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3SpidrUnpackerProgram,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.shared_types import StateServiceConfig
from hermes.state_service.state_io import save_hermes_record_to_yaml
from hermes.state_service.state_manager import StateManager

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RAW_TPX3_DIRECTORY = REPOSITORY_ROOT / "data/list_tests"
UNPACKER_EXECUTABLE = (
    REPOSITORY_ROOT / "build/backends/tpx3-spidr/hermes-tpx3-spidr"
)
EXAMPLE_DIRECTORY = (
    REPOSITORY_ROOT / "data/examples/analysis/unpacker_multiple_files"
)
ANALYSIS_DIRECTORY = EXAMPLE_DIRECTORY / "analysis"
HERMES_STATE_FILE = EXAMPLE_DIRECTORY / "hermes-record.yaml"


def main() -> None:
    raw_tpx3_files = sorted(RAW_TPX3_DIRECTORY.glob("*.tpx3"))

    if not raw_tpx3_files:
        raise FileNotFoundError(
            f"No TPX3 files found in directory: {RAW_TPX3_DIRECTORY}"
        )

    if not UNPACKER_EXECUTABLE.is_file():
        raise FileNotFoundError(
            "C++ unpacker not found. Run `pixi run build-cpp-unpacker` first: "
            f"{UNPACKER_EXECUTABLE}"
        )

    print(f"Found {len(raw_tpx3_files)} TPX3 files:")
    for tpx3_file in raw_tpx3_files:
        print(f"  - {tpx3_file.name}")

    analysis = HermesTpx3AnalysisState(
        unpacker_program=Tpx3SpidrUnpackerProgram(
            name="tpx3-spidr-cpp",
            executable_path=UNPACKER_EXECUTABLE,
            version="0.1.0",
        ),
        analysis_directory=ANALYSIS_DIRECTORY,
        tpx3_files=[FileReference(path=f) for f in raw_tpx3_files],
        resource_limit_percent=90,
    )
    state_manager = StateManager(
        HermesRecord(
            measurement_info=MeasurementInfo(
                measurement_id="example-tpx3-unpacking-multiple-files",
                run_number=1,
            ),
            environment=RuntimeEnvironment(working_dir=EXAMPLE_DIRECTORY),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    unpacked_files = run_hermes_analysis(state_manager)
    save_hermes_record_to_yaml(state_manager.get_state(), HERMES_STATE_FILE)

    print(f"\nUnpacked: {len(unpacked_files)} files")
    print(f"Skipped: {len(raw_tpx3_files) - len(unpacked_files)} files")
    print(f"Analysis directory: {ANALYSIS_DIRECTORY}")
    print(f"HERMES state file: {HERMES_STATE_FILE}")


if __name__ == "__main__":
    main()
