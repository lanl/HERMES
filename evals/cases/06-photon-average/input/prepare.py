"""Create the ignored synthetic pixel input before this eval runs."""

from pathlib import Path

from photon_timing_inputs import prepare_pixels

prepare_pixels(Path("data/06-photon-average/timing"))
