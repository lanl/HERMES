# Event Reconstruction

Event reconstruction is another separate analysis step. A user-selected event
reconstruction backend should read photon Parquet files and write event Parquet
files. Possible C++ and Rust versions should be grouped under:

```text
src/backends/event-reconstructors/<name>/
├── cpp/
└── rust/
```

The exact event file columns and timing rules must be added to the architecture
before the first event reconstruction backend is implemented.
