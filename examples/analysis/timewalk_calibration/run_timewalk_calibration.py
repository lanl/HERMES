from __future__ import annotations

from pathlib import Path

from hermes.analysis.hermes.timewalk_calibration import calibrate_timewalk
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    Tpx3PhotonClusteringSettings,
    Tpx3SpidrUnpackerProgram,
)
from hermes.state.models.environment import RuntimeEnvironment
from hermes.state.models.measurement import MeasurementInfo
from hermes.state.models.shared_models import FileReference
from hermes.state.state import HermesRecord
from hermes.state_service.state_io import save_hermes_record_to_yaml
from hermes.workflows.workflow import Workflow

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RAW_TPX3_DIRECTORY = REPOSITORY_ROOT / "data/list_tests"
UNPACKER_EXECUTABLE = (
    REPOSITORY_ROOT / "build/backends/tpx3-spidr/hermes-tpx3-spidr"
)
EXAMPLE_DIRECTORY = (
    REPOSITORY_ROOT / "data/examples/analysis/timewalk_calibration"
)
ANALYSIS_DIRECTORY = EXAMPLE_DIRECTORY / "analysis"
HERMES_STATE_FILE = EXAMPLE_DIRECTORY / "hermes-record.yaml"
CALIBRATION_FILE = ANALYSIS_DIRECTORY / "logs/timewalk-calibration.json"
CORRECTION_FILE = ANALYSIS_DIRECTORY / "logs/timewalk-calibration-correction.json"

# Cluster-selection settings for the in-cluster relative time-walk fit.
CLUSTERING_SETTINGS = Tpx3PhotonClusteringSettings.model_validate(
    {
        "max_time_spread_ticks": 491_520,
        "min_cluster_size": 2,
        "max_cluster_size": 64,
        "min_pixel_tot_raw": 1,
        "min_cluster_tot_raw": 2,
        "max_cluster_tot_raw": 65_472,
        "max_aspect_ratio": 3.0,
        "min_filled_fraction": 0.5,
        "adjacency": 8,
    }
)


def main() -> None:
    # Step 1: Find the raw TPX3 files and validate the required unpacker
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

    # Step 2: Display the raw TPX3 files selected for analysis
    print(f"Found {len(raw_tpx3_files)} TPX3 files:")
    for tpx3_file in raw_tpx3_files:
        print(f"  - {tpx3_file.name}")

    # Step 3: Configure the unpacking analysis
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
    # Step 4: Create one HERMES record and workflow for the analysis
    workflow = Workflow(
        HermesRecord(
            measurement_info=MeasurementInfo(
                measurement_id="example-tpx3-timewalk-calibration",
                run_number=1,
            ),
            environment=RuntimeEnvironment(working_dir=EXAMPLE_DIRECTORY),
            acquisition=None,
            analysis=analysis,
        )
    )

    # Step 5: Unpack the raw files and save the completed HERMES record
    workflow.run_analysis()
    save_hermes_record_to_yaml(workflow.record, HERMES_STATE_FILE)

    # Step 6: Find the unpacked pixel-data Parquet files
    pixel_files = sorted((ANALYSIS_DIRECTORY / "pixelHits").glob("*.parquet"))
    if not pixel_files:
        raise FileNotFoundError(
            f"No pixel_data Parquet files found in: {ANALYSIS_DIRECTORY / 'pixelHits'}"
        )

    # Step 7: Fit and save the time-walk calibration
    print(f"\nCalibrating time-walk from {len(pixel_files)} pixel_data files...")
    try:
        calibration = calibrate_timewalk(
            pixel_files,
            CLUSTERING_SETTINGS,
            CALIBRATION_FILE,
            CORRECTION_FILE,
        )
    except ValueError as error:
        print(f"\nCalibration produced no usable clusters: {error}")
        print(
            "The bundled data/list_tests files contain no photon-like blobs, "
            "so there are no in-cluster pixel pairs to fit. Substitute your "
            "own photon pixel_data by pointing RAW_TPX3_DIRECTORY at a "
            "directory of TPX3 files that contain phosphor clusters."
        )
        return

    # Step 8: Display the calibration results and saved file locations
    print(f"\nComponents considered: {calibration.components_considered:,}")
    print(f"Components used:       {calibration.components_used:,}")
    print(f"Pixel pairs:           {calibration.pixel_pairs:,}")
    print(f"High-ToT anchor:       {calibration.high_tot_anchor}")
    print(f"Selected model:        {calibration.selected_model}")
    print(f"Selected parameters:   {calibration.selected_parameters}")
    print(f"Selection reason:      {calibration.selection_reason}")
    print(f"\nDetailed calibration:  {CALIBRATION_FILE}")
    print(f"Comparison plot:       {calibration.comparison_plot}")
    print(f"Correction file:       {CORRECTION_FILE}")
    print(f"HERMES state file:     {HERMES_STATE_FILE}")


if __name__ == "__main__":
    main()
