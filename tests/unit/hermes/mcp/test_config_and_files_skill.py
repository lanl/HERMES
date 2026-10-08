from __future__ import annotations

import subprocess
import sys

import pytest
import yaml

from hermes.mcp.setup import SKILLS_DIRECTORY
from hermes.state.state import HermesRecord

SKILL = SKILLS_DIRECTORY / "hermes-config-and-files"
SCRIPT = SKILL / "scripts" / "show_config_fields.py"


def _show(section: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), section],
        capture_output=True,
        text=True,
        check=False,
    )


def _frontmatter() -> dict:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, _ = text.split("---\n", 2)
    return yaml.safe_load(frontmatter)


@pytest.mark.parametrize(
    ("section", "fields"),
    [
        ("measurement_info", ["measurement_id", "run"]),
        ("environment", ["working_directory", "raw_data_directory", "log_level"]),
        ("acquisition", ["serval", "calibration_files", "run_timing", "Tdc"]),
        ("analysis", ["resource_limit_percent", "detector_layout"]),
        ("unpacking", ["tpx3_files", "delete_raw_after_unpack"]),
        (
            "photon_reconstruction",
            ["max_time_spread_ticks", "adjacency", "timewalk_calibration_file"],
        ),
        ("event_reconstruction", ["spatial_link_radius_pixels", "min_photon_count"]),
    ],
)
def test_shows_the_fields_of_each_section(section: str, fields: list[str]) -> None:
    result = _show(section)

    assert result.returncode == 0, result.stderr
    for field in fields:
        assert field in result.stdout
    # Fields HERMES fills in while it runs are left out.
    assert "results" not in result.stdout


def test_every_top_level_config_section_can_be_shown() -> None:
    for section in HermesRecord.model_fields:
        result = _show(section)
        assert result.returncode == 0, result.stderr


def test_a_field_shows_its_type_default_limits_and_meaning() -> None:
    result = _show("photon_reconstruction")

    assert "adjacency: 4 | 8 (default 8)" in result.stdout
    assert "min_pixel_tot_raw: int (required; >= 0; <= 1023)" in result.stdout
    assert "4: pixels join when they share a side." in result.stdout


def test_a_field_with_a_built_default_is_not_shown_as_unspecified() -> None:
    assert "additional_metadata: dict[str, JsonValue] (default {})" in (
        _show("measurement_info").stdout
    )
    assert "log_directory: path (optional)" in _show("environment").stdout
    assert "runtime_options: Tpx3UnpackingRuntimeOptions (optional)" in (
        _show("unpacking").stdout
    )


def test_an_unknown_section_lists_the_sections() -> None:
    result = _show("clustering")

    assert result.returncode != 0
    assert "photon_reconstruction" in result.stderr


def test_the_skill_files_are_in_the_package() -> None:
    assert (SKILL / "SKILL.md").is_file()
    assert (SKILL / "output_files.md").is_file()
    assert SCRIPT.is_file()


def test_the_skill_description_says_when_to_use_it() -> None:
    frontmatter = _frontmatter()

    assert frontmatter["name"] == SKILL.name
    description = frontmatter["description"]
    assert len(description) < 1536
    assert "Use when" in description
