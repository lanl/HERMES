# Workflows

The full acquisition-to-analysis state flow is:

```text
Create acquisition plan
  -> initialize HERMES record
  -> connect to SERVAL
  -> snapshot detector and SERVAL state
  -> configure acquisition
  -> run acquisition
  -> record raw/image artifacts
  -> unpack raw data if needed
  -> record decoded artifacts and unpack summary
  -> run analysis workflow
  -> record analysis artifacts and summary metrics
  -> persist final HERMES record
```

Each major step should produce structured Loguru events and update the record
through `hermes.state_service` with enough information to debug or reproduce the
run. Acquisition-only and analysis-only workflows are valid subsets of this full
flow; the `HermesRecord` may have only acquisition state, only analysis state, or
both.

## First Concrete Workflow

The first workflow should be intentionally narrow:

1. Connect to SERVAL.
2. Snapshot detector information, detector configuration, detector layout, and
   detector health.
3. Configure a SERVAL destination that writes raw `.tpx3` data.
4. Start acquisition and wait for completion.
5. Save a HERMES record that references the raw artifact through
   `hermes.state_service`.
6. Run `hermes-tpx3-spidr` on the raw artifact.
7. Save decoded output and a summary JSON artifact.
8. Update the same HERMES record with analysis/unpack results through
   `hermes.state_service`.

This workflow is enough to validate the state model, artifact tracking, logging,
and Rust/Python boundary.
