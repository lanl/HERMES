# Brightest-hit photon timing

This case uses the same ten synthetic hits as
[case 06](../06-photon-average/case.md). It selects `brightest` with correction
off. The source hits, cluster memberships, positions, summed ToTs, and quality
flags must be identical to case 06.

| Photon | Selection | Expected photon time |
| --- | --- | --- |
| 0 | Two hits have the largest ToT, 30, at raw times 106 and 110. Select the earliest raw time. | 106 |
| 1 | The saturated hit has the largest ToT, 1023. | 204 |
| 2 | The ToT-30 hit is later than the ToT-10 hit. | 9007199254740994 |

These expectations select timestamps, not ToT values. They distinguish
brightest timing from both average and leading-edge timing on the small
clusters. `expected/parquet_rows.json` compares all rows exactly, and the
summary records `brightest` without calibration.
