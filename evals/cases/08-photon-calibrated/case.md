# Shared linear correction followed by average timing

This case uses the same ten synthetic hits as
[case 06](../06-photon-average/case.md). It enables the small synthetic curve
in `input/linear.json`: slope 1 and high-ToT anchor 30, in canonical ticks.
It is a test curve, not a fit to detector data.

The delay is `tot_raw - 30` and is subtracted from each raw hit time. Calculate
the arithmetic mean only after that correction, without changing clustering:

| Photon | Corrected hit times | Expected photon time |
| --- | --- | --- |
| 0 | 120, 106, 120, 110 | 456 / 4 = 114 |
| 1 | 200, 222, -789, 216 | -151 / 4 = -37.75 |
| 2 | B+21, B+2 | B+12 = 9007199254741004 |

Here B = 2^53. The last exact mean is B+11.5, which rounds to B+12 in float64.
Prematurely rounding the earliest raw timestamp loses a tick before the mean
and can instead produce B+10.

The saturated hit uses the curve at ToT 1023, giving a delay of 993 and a
corrected time of -789. It keeps its saturation flag. Corrected times can
change order, but the raw 20-tick gate still gives the same three clusters,
with the same positions, summed ToTs, and pixel-to-photon assignments.

`expected/parquet_rows.json` checks those values and the unchanged raw source
times exactly. The summary must record `average`, the linear model, slope 1,
anchor 30, and the calibration filename. The old known-good leading-edge
cases remain unchanged.
