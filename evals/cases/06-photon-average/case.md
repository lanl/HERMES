# Default photon timing: uncorrected average

Both timing settings are omitted from `input/config.yaml`. The workflow must
choose `average` with correction off. `input/prepare.py` writes ten synthetic
pixel hits using `evals/photon_timing_inputs.py`; no detector files are committed.

The source hits form three accepted clusters under the 20-tick time gate:

| Photon | Raw hit times | Raw ToTs | Expected photon time |
| --- | --- | --- | --- |
| 0 | 100, 106, 110, 110 | 10, 30, 20, 30 | 106.5 |
| 1 | 200, 202, 204, 206 | 30, 10, 1023, 20 | 203 |
| 2 | B+1, B+2 | 10, 30 | B+2 = 9007199254740994 |

Here B = 2^53. The exact last mean is B+1.5; the nearest float64 value is B+2.
Rounding each raw timestamp before averaging would incorrectly produce B on
platforms where `long double` has the same precision as `double`.

Photon 0 repeats coordinate (1,1); all four hits count in its mean and position.
Photon 1 starts at (10,0) and (12,0); the hit at (11,0) joins them, and its ToT
1023 marks saturation. That photon keeps both quality bits (3), position (11,0),
and summed ToT 1083. Photon 0 has position (0.75,0.5) and summed ToT 90; photon
2 has position (20.5,20) and summed ToT 40.

`expected/parquet_rows.json` checks every photon column, every original pixel
column, and every pixel-to-photon assignment. All expected times are exactly
representable as float64 and are compared exactly. The summary and workflow
log must record the default timing and three successful photons.
