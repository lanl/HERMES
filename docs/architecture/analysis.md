# Analysis

`src/hermes/analysis/` owns analysis orchestration. It should not duplicate the
Rust packet decoder.

Expected responsibilities:

- call the Rust unpacker for raw `.tpx3` files
- load decoded event products or image products
- run modality-specific analysis workflows
- write derived artifacts
- update the analysis section of the central record through `hermes.state_service`

Analysis workflows should accept artifact references and Pydantic plans, then
return structured analysis results and new artifacts. Any durable state updates
must be applied through `hermes.state_service`; analysis code should not mutate
the record directly.
