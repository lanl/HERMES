# Analysis

`src/hermes/analysis/` owns the Python code that runs analysis steps. The Rust
unpacker, not Python, reads the binary packets in raw TPX3 files.

Expected responsibilities:

- call the Rust unpacker for raw `.tpx3` files
- load pixel-hit, TDC-hit, timestamp, or control-packet Parquet files
- group pixel hits into photon events when photon clustering is requested
- write specific output files, such as photon-event Parquet files, images, or plots
- update the analysis section of the central record through `hermes.state_service`

Analysis workflows should accept explicitly named inputs, such as raw TPX3 files
or directories containing TPX3 Parquet files, together with Pydantic
configuration models. They should return explicitly named paths, such as the TPX3
Parquet output directory, summary JSON file, image file, or plot file. Any saved
state updates must be applied through `hermes.state_service`; analysis code
should not mutate the record directly.

Analysis workflows must not require acquisition state to be present. For
analysis-only use, raw TPX3 files, image files, or directories containing TPX3
Parquet files should be recorded directly in the analysis section of the
`HermesRecord`.
