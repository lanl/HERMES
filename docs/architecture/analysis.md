# Analysis

`src/hermes/analysis/` owns the Python code that runs analysis steps. It should
not duplicate the Rust packet decoder.

Expected responsibilities:

- call the Rust unpacker for raw `.tpx3` files
- load decoded event tables or image files
- run the selected analysis workflow
- write decoded tables, images, plots, and other named outputs
- update the analysis section of the central record through `hermes.state_service`

Analysis workflows should accept explicitly named inputs, such as raw TPX3 files
or decoded output directories, together with Pydantic configuration models. They
should return explicitly named results, such as a decoded output directory,
summary JSON file, image file, or plot file. Any saved state updates must be
applied through `hermes.state_service`; analysis code should not mutate the
record directly.

Analysis workflows must not require acquisition state to be present. For
analysis-only use, raw TPX3 files or other input files should be recorded directly
in the analysis section of the `HermesRecord`.
