# HERMES TPX3 Photon Reconstruction Example

This example unpacks raw TPX3 files and then reconstructs photons from the
resulting `pixel_data` with the connected-components + time-gate clusterer. It
applies the checked-in time-walk calibration to the leading edge, writes
`photon_events` and `photon_pixels` Parquet files, and a per-file
reconstruction-summary JSON.

## Input Files

The example unpacks all TPX3 files found in `data/list_tests/`:

- `Example_1kHz_5frames_0000.tpx3`
- `Example_1kHz_5frames_0001.tpx3`
- `Example_1kHz_5frames_0002.tpx3`
- `Example_1kHz_5frames_0003.tpx3`

> **Substitute your own data.** These bundled files are the unpacker test
> fixtures. They do **not** contain photon-like phosphor blobs, so the
> reconstruction forms no accepted photons — the example prints the counts and
> a note. To reconstruct real photons, edit `RAW_TPX3_DIRECTORY` in
> `run_reconstruction.py` to point at a directory of TPX3 files that contain
> phosphor clusters.

## Building the Backends

Before running the example, build both C++ backends:

```bash
pixi run build-cpp-unpacker
pixi run build-cpp-photon-clusterer
```

These create the executables at `build/backends/tpx3-spidr/hermes-tpx3-spidr`
and `build/backends/photon-clusterer/hermes-photon-clusterer`.

## Running the Example (fresh)

```bash
rm -rf data/examples/analysis/photon_reconstruction
pixi run python examples/analysis/photon_reconstruction/run_reconstruction.py
```

This will:

1. Unpack the TPX3 files in `data/list_tests/` through `run_hermes_analysis()`.
2. Reconstruct photons from the unpacked `pixel_data` with the
   connected-components + time-gate rule and the cluster-selection settings
   defined in the script.
3. Correct each cluster's leading edge with the checked-in time-walk
   calibration (`calibrations/tpx3/time-walk_example.json`).
4. Write `photon_events` and `photon_pixels` Parquet files and a per-file
   reconstruction-summary JSON.

## Running the Example Again (skip)

Running the example a second time without clearing the output directory finds
the valid reconstruction summaries and photon files, so reconstruction is
skipped:

```bash
pixi run python examples/analysis/photon_reconstruction/run_reconstruction.py
```

## Cluster-Selection Settings

The script uses an inclusive 1 microsecond time gate (491,520 canonical ticks),
8-connectivity, cluster sizes 2 through 64, per-pixel ToT at least 1, integrated
ToT from 2 through 65,472, aspect ratio at most 3, and filled fraction at least
0.5. `save_photon_pixels` is on so the per-photon source pixels are written.
Adjust these in `run_reconstruction.py` for your detector.

## Output Structure

```text
data/examples/analysis/photon_reconstruction/
├── hermes-record.yaml
└── analysis/
    ├── pixelHits/
    │   └── Example_1kHz_5frames_000X-chip-0-part-00000.parquet
    ├── photons/
    │   ├── Example_1kHz_5frames_000X-chip-0-photon-events-part-00000.parquet
    │   └── Example_1kHz_5frames_000X-chip-0-photon-pixels-part-00000.parquet
    └── logs/
        ├── Example_1kHz_5frames_000X-unpacker-summary.json
        └── Example_1kHz_5frames_000X-reconstruction-summary.json
```

The `photon_events` file carries the reconstructed photons (position, summed
ToT, leading-edge time, quality flags); `photon_pixels` carries one row per
source pixel referencing its photon. The reconstruction summary records the
clustering settings, per-reason rejection counts, quality-flag counts, output
file lists, and processing times with throughput.
