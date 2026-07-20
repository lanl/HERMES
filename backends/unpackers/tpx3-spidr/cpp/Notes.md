# TPX3 SPIDR raw packet reference

This file records the raw fields that the HERMES TPX3 SPIDR unpacker must
preserve. It is based primarily on:

- `.agent/resources/20231023_ASIServer_TPX3_manual_V3.3.pdf`;
- `.agent/resources/TPX3CAM_manual_V2.3.pdf`;
- `.agent/examples/TPX3_read_and_convert.cpp`.

PymePix, tpx3HitParser, and mcpevent2hist/Sophiread are useful independent
implementations, but none of them preserves every packet family. The vendor
manuals define the raw file contract.

## General rules

- A `.tpx3` file is a sequence of chunks.
- Every chunk starts with one 8-byte header.
- The chunk content contains 8-byte words in little-endian byte order.
- Bit ranges below are inclusive and numbered from the least-significant bit.
- The most-significant nibble normally identifies the packet family.
- Raw integer fields are the source of truth. Derived times must not replace
  them.
- The raw 64-bit word, chip index, chunk index, and packet index should be
  retained for packet families whose meaning is incomplete or uncertain.

## Chunk header

| Bits | Field | Notes |
| --- | --- | --- |
| 63-48 | `chunk_size_bytes` | Number of content bytes following the header. It must be divisible by 8. |
| 47-40 | `mode_or_reserved` | Called reserved by SERVAL V3.3 and mode by the older TPX3Cam manual. Preserve it without assuming a meaning. |
| 39-32 | `chip_index` | Identifies the Timepix3 chip that produced the chunk. |
| 31-0 | signature | Little-endian bytes `TPX3`, integer value `0x33585054`. |

The number of content packets is `chunk_size_bytes / 8`. A decoder must reject
or report a truncated chunk rather than reading beyond the input buffer.

## Pixel packets

### Integrated-ToT packet (`0xA`)

| Bits | Field | Type |
| --- | --- | --- |
| 63-60 | packet type `0xA` | `uint8` |
| 59-44 | `pixel_address` | `uint16` |
| 43-30 | `integrated_tot_raw` | `uint16`, 25 ns ticks |
| 29-20 | `event_count` | `uint16` |
| 19-16 | `hit_count` | `uint8` |
| 15-0 | `spidr_time_raw` | `uint16`, 409.6 us ticks |

Integrated-ToT packets must not be silently discarded, even when the first
workflow normally records data-driven `0xB` packets.

### ToA/ToT pixel-hit packet (`0xB`)

| Bits | Field | Type |
| --- | --- | --- |
| 63-60 | packet type `0xB` | `uint8` |
| 59-44 | `pixel_address` | `uint16` |
| 43-30 | `toa_raw` | `uint16`, 25 ns ticks |
| 29-20 | `tot_raw` | `uint16`, 25 ns ticks |
| 19-16 | `ftoa_raw` | `uint8`, negative 1.5625 ns correction |
| 15-0 | `spidr_time_raw` | `uint16`, 409.6 us ticks |

The pixel address is decoded as:

```text
double_column = (pixel_address & 0xFE00) >> 8
super_pixel   = (pixel_address & 0x01F8) >> 1
pixel_index   =  pixel_address & 0x0007
x             = double_column + (pixel_index >> 2)
y             = super_pixel + (pixel_index & 0x3)
```

These are local chip coordinates. Detector-wide coordinates require the
`chip_index` and detector-layout information and should not replace the local
coordinates in the unpacker output.

The exact fine pixel time in units of 1.5625 ns is:

```text
pixel_time_1p5625ns =
    (((spidr_time_raw << 14) + toa_raw) << 4) - ftoa_raw
```

Do not use `(toa_raw << 4) | (~ftoa_raw & 0xF)`. That expression adds 15 fine
ticks and shifts every pixel timestamp by 23.4375 ns.

The 16-bit SPIDR timer advances in 409.6 us steps. Its rollover period is:

```text
65536 * 409.6 us = 26.8435456 s
```

The largest encoded value occurs one tick before that rollover.

## TDC packet (`0x6`)

| Bits | Field | Type |
| --- | --- | --- |
| 63-60 | packet type `0x6` | `uint8` |
| 59-56 | `edge_code` | `uint8` |
| 55-44 | `trigger_counter` | `uint16` |
| 43-9 | `tdc_timestamp_raw` | `uint64`, 3.125 ns ticks |
| 8-5 | `tdc_fine_raw` | `uint8`, values 1-12 |
| 4-0 | reserved | `uint8` |

Edge codes are:

| Code | Meaning |
| --- | --- |
| `0xF` | TDC1 rising edge |
| `0xA` | TDC1 falling edge |
| `0xE` | TDC2 rising edge |
| `0xB` | TDC2 falling edge |

Fine value 0 is a decoder error state. Value 1 represents zero fine offset;
values 2 through 12 advance in exact steps of `25 ns / 96`.

```text
tdc_time =
    tdc_timestamp_raw * 3.125 ns
    + (tdc_fine_raw - 1) * (25 ns / 96)
```

The decoder must preserve the edge code, trigger counter, timestamp, and fine
value independently. It must not count every `0x6` packet as a TDC1 event.

## Global-time packets (`0x4`)

### Time-low packet (`0x44`)

| Bits | Field | Type |
| --- | --- | --- |
| 63-56 | packet ID `0x44` | `uint8` |
| 55-48 | reserved | `uint8` |
| 47-16 | `global_time_low_raw` | `uint32`, 25 ns ticks |
| 15-0 | `spidr_time_raw` | `uint16`, 409.6 us ticks |

### Time-high packet (`0x45`)

| Bits | Field | Type |
| --- | --- | --- |
| 63-56 | packet ID `0x45` | `uint8` |
| 55-32 | reserved | 24 bits |
| 31-16 | `global_time_high_raw` | `uint16`, high bits of the 25 ns timer |
| 15-0 | `spidr_time_raw` | `uint16`, 409.6 us ticks |

When a matching low and high value are available, the 48-bit timer is:

```text
global_time_raw =
    (global_time_high_raw << 32) | global_time_low_raw
```

One global tick is 25 ns. The high field advances in exact steps of
`2^32 * 25 ns = 107.3741824 s`. The 48-bit timer rollover period is about
`7,036,874.4177664 s`, or 81.45 days.

The low packet, high packet, and paired 48-bit value should remain
distinguishable. Do not store either raw part only as floating-point seconds.

## SPIDR control packets (`0x5`)

### Packet-count packet (`0x50`)

| Bits | Field |
| --- | --- |
| 63-56 | packet ID `0x50` |
| 55-48 | reserved |
| 47-0 | `packet_count` |

### Shutter and heartbeat packets

| Bits | Field |
| --- | --- |
| 63-60 | packet type `0x5` |
| 59-56 | subtype: `0xF` open shutter, `0xA` close shutter, `0xC` heartbeat |
| 55-46 | reserved |
| 45-12 | `timestamp_raw`, 25 ns ticks |
| 11-0 | reserved |

The subtype, timestamp, reserved fields, and raw packet must be preserved. A
control packet must not be replaced with a zero-filled generic signal row.

## TPX3 control packets (`0x7`)

The SERVAL V3.3 table identifies `0x71` in bits 63-56 and lists `0xA0` and
`0xB0` as end-of-sequential-readout and end-of-data-driven-readout subtypes.
The table's stated reserved range overlaps the subtype, and other readers also
recognize additional `0x71xx` and `0x72xx` values.

Until every subtype is confirmed, preserve:

- the upper 16-bit control value;
- the lower 48 payload bits;
- the complete raw 64-bit word;
- chip and chunk provenance;
- an `unknown` classification for unrecognized values.

## Unknown packets

Unknown packets are part of the diagnostic record. Preserve their raw word,
most-significant byte, chip index, chunk index, and packet index, and add a
warning to the decode summary. Do not silently discard them.

## HERMES output representation

The unpacker should preserve and write the detector's native integer fields.
Each packet type should have its own clearly defined output columns so no raw
packet information is forced into unrelated generic fields or discarded.

Packet decoding should use integer masks, shifts, and arithmetic. Required
derived timestamps, such as the combined pixel or 48-bit global timestamp,
should also remain integers with their exact units recorded as metadata.

The first implementation should not write derived floating-point time columns.
Conversions to seconds or nanoseconds belong in later analysis and
visualization code and should be calculated only when needed.

The existing `signalData` memory dump should not be used as the output format.
It writes the program's internal C++ memory layout, which may include compiler
padding and machine-specific byte ordering, and it cannot retain all fields
from every packet type.
