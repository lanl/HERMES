# Analysis

`src/hermes/analysis/` owns analysis orchestration. It should not duplicate the
Rust packet decoder.

Expected responsibilities:

- call the Rust unpacker for raw `.tpx3` files
- load decoded event products or image products
- run modality-specific analysis workflows
- write derived artifacts
- update the analysis section of the central record

Analysis workflows should accept artifact references and Pydantic plans, then
return updated state and new artifacts.
