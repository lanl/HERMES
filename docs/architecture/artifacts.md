# Artifacts

Artifacts are files produced or consumed by acquisition and analysis. The
Pydantic record should reference artifacts; it should not embed their full
contents.

Common artifact kinds:

- `raw_tpx3`
- `image`
- `decoded_events`
- `unpack_summary`
- `analysis_table`
- `plot`
- `report`
- `config_snapshot`
- `log`

Each artifact should eventually record:

- stable artifact id
- path
- kind
- format
- creation time
- source artifact ids
- producing tool or workflow
- optional hash
- optional byte size

Large data products should be stored outside the Pydantic record and outside
version control.
