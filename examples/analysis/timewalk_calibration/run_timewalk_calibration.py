from __future__ import annotations

import sys
from pathlib import Path

import yaml

from hermes.analysis.hermes.timewalk_calibration import calibrate_timewalk
from hermes.state.models.analysis.hermes_tpx3_spidr import (
    Tpx3PhotonClusteringSettings,
)
from hermes.state_service.state_io import (
    load_hermes_record_from_yaml,
    save_hermes_record_to_yaml,
)
from hermes.workflows.workflow import Workflow

DEFAULT_INPUT_YAML_PATH = Path(__file__).with_name("timewalk_config.yaml")
CLUSTERING_SETTINGS_YAML_PATH = Path(__file__).with_name(
    "clustering_settings.yaml"
)


def main(input_yaml_path: Path = DEFAULT_INPUT_YAML_PATH) -> None:
    # Step 1: Load the initial HERMES record from the configuration YAML file
    initial_record = load_hermes_record_from_yaml(input_yaml_path)

    # Step 2: Choose paths for the completed record and calibration outputs
    working_directory = initial_record.environment.working_dir.resolved_path
    final_record_path = working_directory / "hermes-record_final.yaml"
    analysis = initial_record.analysis
    if analysis is None or getattr(analysis, "mode", None) != "hermes":
        raise SystemExit(
            "time-walk calibration requires a HERMES HermesRecord (analysis.mode: hermes)"
        )
    analysis_directory = analysis.analysis_directory
    calibration_file = analysis_directory / "logs/timewalk-calibration.json"
    correction_file = analysis_directory / "logs/timewalk-calibration-correction.json"

    # Step 3: Unpack the raw TPX3 files and save the completed HERMES record
    workflow = Workflow(initial_record)
    workflow.run_analysis()
    save_hermes_record_to_yaml(workflow.record, final_record_path)

    # Step 4: Load the cluster-selection settings for the calibration fit
    clustering_settings = Tpx3PhotonClusteringSettings.model_validate(
        yaml.safe_load(
            CLUSTERING_SETTINGS_YAML_PATH.read_text(encoding="utf-8")
        )
    )

    # Step 5: Fit and save the time-walk calibration from the unpacked pixel data
    pixel_files = sorted((analysis_directory / "pixelHits").glob("*.parquet"))
    calibration = calibrate_timewalk(
        pixel_files,
        clustering_settings,
        calibration_file,
        correction_file,
    )

    # Step 6: Display the calibration results and saved file locations
    print(f"Components considered: {calibration.components_considered:,}")
    print(f"Components used:       {calibration.components_used:,}")
    print(f"Pixel pairs:           {calibration.pixel_pairs:,}")
    print(f"High-ToT anchor:       {calibration.high_tot_anchor}")
    print(f"Selected model:        {calibration.selected_model}")
    print(f"Selected parameters:   {calibration.selected_parameters}")
    print(f"Selection reason:      {calibration.selection_reason}")
    print(f"Calibration file:      {calibration_file}")
    print(f"Comparison plot:       {calibration.comparison_plot}")
    print(f"Correction file:       {correction_file}")
    print(f"HERMES state file:     {final_record_path}")


if __name__ == "__main__":
    input_yaml_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT_YAML_PATH
    )
    main(input_yaml_path)
