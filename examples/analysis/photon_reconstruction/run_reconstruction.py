from __future__ import annotations

from pathlib import Path

from hermes.analysis.hermes.run import run_hermes_analysis
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    HermesTpx3AnalysisState,
    PhotonReconstructorProgram,
    Tpx3PhotonClusteringSettings,
    Tpx3PhotonReconstructionConfiguration,
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
CLUSTERER_EXECUTABLE = (
    REPOSITORY_ROOT / "build/backends/photon-clusterer/hermes-photon-clusterer"
)
CALIBRATION_FILE = REPOSITORY_ROOT / "calibrations/tpx3/time-walk_example.json"
EXAMPLE_DIRECTORY = (
    REPOSITORY_ROOT / "data/examples/analysis/photon_reconstruction"
)
ANALYSIS_DIRECTORY = EXAMPLE_DIRECTORY / "analysis"
HERMES_STATE_FILE = EXAMPLE_DIRECTORY / "hermes-record.yaml"

# Cluster-selection settings for photon reconstruction. The time-walk
# calibration file supplies the leading-edge correction; photon_pixels are
# written so the per-photon source pixels can be inspected.
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
        "timewalk_calibration_file": CALIBRATION_FILE,
        "save_photon_pixels": True,
    }
)


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
    if not CLUSTERER_EXECUTABLE.is_file():
        raise FileNotFoundError(
            "C++ photon clusterer not found. Run "
            "`pixi run build-cpp-photon-clusterer` first: "
            f"{CLUSTERER_EXECUTABLE}"
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
        photon_reconstruction=Tpx3PhotonReconstructionConfiguration(
            program=PhotonReconstructorProgram(
                name="photon-clusterer-cpp",
                executable_path=CLUSTERER_EXECUTABLE,
                version="0.1.0",
            ),
            pixel_data_directory=ANALYSIS_DIRECTORY / "pixelHits",
            photon_output_directory=ANALYSIS_DIRECTORY / "photons",
            settings=CLUSTERING_SETTINGS,
        ),
    )
    state_manager = StateManager(
        HermesRecord(
            measurement_info=MeasurementInfo(
                measurement_id="example-tpx3-photon-reconstruction",
                run_number=1,
            ),
            environment=RuntimeEnvironment(working_dir=EXAMPLE_DIRECTORY),
            acquisition=None,
            analysis=analysis,
        ),
        config=StateServiceConfig(allow_trusted_workflow_bypass=True),
    )

    run_hermes_analysis(state_manager)
    save_hermes_record_to_yaml(state_manager.get_state(), HERMES_STATE_FILE)

    reconstruction = state_manager.get_state().analysis.results.reconstruction
    print("\nReconstruction result:")
    print(f"  Status:            {reconstruction.status}")
    print(f"  Photons:           {reconstruction.photon_count:,}")
    print(f"  Rejected clusters: {reconstruction.rejected_count:,}")
    if reconstruction.started_at is not None and (
        reconstruction.finished_at is not None
    ):
        wall_seconds = (
            reconstruction.finished_at - reconstruction.started_at
        ).total_seconds()
        print(f"  Wall time:         {wall_seconds:.3f} s")

    # Per-reason rejection counts and throughput come from each stem's summary.
    logs_dir = ANALYSIS_DIRECTORY / "logs"
    print("\nPer-file reconstruction summaries:")
    for summary_file in sorted(
        logs_dir.glob("*-reconstruction-summary.json")
    ):
        _print_summary(summary_file)

    photon_files = sorted((ANALYSIS_DIRECTORY / "photons").glob("*.parquet"))
    print(f"\nPhoton output directory: {ANALYSIS_DIRECTORY / 'photons'}")
    print(f"  {len(photon_files)} photon Parquet file(s)")
    print(f"HERMES state file:       {HERMES_STATE_FILE}")

    if reconstruction.photon_count == 0:
        print(
            "\nNo photons were reconstructed. The bundled data/list_tests "
            "files contain no photon-like phosphor blobs, so every cluster is "
            "rejected or none form. Point RAW_TPX3_DIRECTORY at TPX3 files "
            "with phosphor clusters to reconstruct real photons."
        )


def _print_summary(summary_file: Path) -> None:
    import json

    summary = json.loads(summary_file.read_text())
    reconstruction = summary["reconstruction"]
    times = summary["processing_times_seconds"]
    throughput = times["throughput"]
    print(f"  {summary_file.name}")
    print(f"    pixel rows read:      {reconstruction['pixel_rows_read']:,}")
    print(f"    components formed:    {reconstruction['components_formed']:,}")
    print(f"    photons:              {reconstruction['photon_count']:,}")
    print(
        f"    rejected components:  "
        f"{reconstruction['rejected_component_count']:,}"
    )
    for reason, count in reconstruction["rejection_counts"].items():
        if count:
            print(f"      {reason}: {count:,}")
    print(f"    total time:           {times['total']:.3f} s")
    print(
        f"    throughput:           "
        f"{throughput['pixels_per_second']:,.0f} pixels/s, "
        f"{throughput['photons_per_second']:,.0f} photons/s"
    )


if __name__ == "__main__":
    main()
