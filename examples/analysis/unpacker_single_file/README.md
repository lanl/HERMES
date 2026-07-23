# TPX3 SPIDR unpacker example

This example runs the state-managed HERMES C++ unpacker on
`tests/data/Example_1kHz_5frames.tpx3`.

Build the C++ executable:

```bash
pixi run build-cpp-unpacker
```

Run the example:

```bash
pixi run python examples/analysis/unpacker/run_unpacker.py
```

The example writes persistent development output outside the tracked source
tree:

```text
data/examples/analysis/unpacker/
├── hermes-record.yaml
└── analysis/
    ├── pixelHits/
    ├── tdcTriggers/
    ├── globalTimestamps/
    ├── controlPackets/
    ├── unknownPackets/
    └── logs/
        └── Example_1kHz_5frames-unpacker-summary.json
```

Running the example again validates the existing summary and Parquet files,
skips unpacking, and refreshes the final HERMES YAML file.
