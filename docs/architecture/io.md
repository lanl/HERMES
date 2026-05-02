# I/O

`src/hermes/io/` owns reading and writing HERMES records and common path
handling.

Expected responsibilities:

- save and load run records
- validate schema versions
- resolve artifact paths relative to a run directory
- avoid mixing temporary files, generated files, and version-controlled files

Directory creation belongs in workflow or I/O code, not in Pydantic validators.
