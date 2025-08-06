** TPX3 raw file format **
Taken from SERVAL manual V3.2
Raw binary TPX3 files recorded by SPIDR readout boards have the following header/buffer structures. 
The .tpx3 raw data files contain the original data as sent by the readout board. 
It consists of chunks with an 8-byte chunk header prepended. 
The chunk content consists of 8-byte words (little endian); 
The type of which is determined by the most significant nibble (i.e., the high nibble of the last byte):

Chunk header packet format:
    63 - 48 bit     Chunk size (bytes)
    47 - 40 bit     Reserved
    39 - 32 bit     Chip index
    31 – 0 bit      “TPX3”

Pixel data packets (0xa, 0xb) format:
    For Integrated ToT mode: 0xa
    63 - 60 bit     0xa
    59 - 44 bit     PixAddr
    43 - 30 bit     Integrated ToT (25ns)
    29 - 20 bit     EventCount 
    19 – 16 bit     HitCount
    15 – 0 bit      SPIDR time (0.4096ms)

    For Time of Arrival Mode: Oxb
    63 - 60 bit     0xb
    59 - 44 bit     PixAddr
    43 - 30 bit     ToA (25ns)
    29 - 20 bit     ToT (25ns)
    19 – 16 bit     FToA (-1.5625ns)
    15 – 0 bit      SPIDR time (0.4096ms)

    Notes: 
        Max ToA time 0.409575 milliseconds 
        Max ToT time is 0.025575 milliseconds
        Max FToA time is -23.4375 ns
        Max SPIDR time is 26.8435456 seconds

TDC data packets (0x6) format:
    63 - 60 bit     0x6
    59 – 56 bit     0xf = TDC1 Rise, 0xa = TDC1 Fall, 0xe = TDC2 Rise, 0xb = TDC2 Fall
    55 - 44 bit     Trigger count
    43 - 9 bit      Timestamp (3.125ns)
    8 - 5 bit       Fine timestamp Takes value 1-12 [value 1 = 0ps, 2 = 260.41666ps, 3 = 520.83332ps, … 12 = 2.86458ns]
    4 – 0 bit       Reserved

Global time data packets (0x4)
    For Global "time-low" packet 
    63 - 56 bit     0x44 = Time Low
    55 – 48 bit     Reserved
    47– 16 bit      TimeStampLow (25ns)
    15 – 0 bit      SPIDR time (0.4096ms)

    Note:
        I think you can set the fequency for spitting out global timestamps 
        in the detector_config_json_data with Serval.
        Timing info:
            - TimeStampLow max value: 107.374182 seconds
            - Max SPIDR time is 26.8435456 seconds

    For Global "time-high" packet 
    63 - 56 bit     0x45 = Time High
    55 – 32 bit     Reserved
    31 – 16 bit     TimeStampHigh (107.374182s)
    15 – 0 bit      SPIDR time (0.4096ms)

    Notes: 
        - TimeStampHigh max value: 7036767.01737
        - Max SPIDR time is 26.8435456 seconds


SPIDR control packets (0x5) format:
    For Packet ID 
    63 - 56 bit     0x50 = Packet ID
    55 – 48 bit     Reserved
    47 – 0 bit      Packet count

    For shutter/heartbeat packet
    64 – 60 bit     0x5
    59 – 56 bit     0xf = open shutter, 0xa = close shutter, 0xc = heartbeat
    55 – 46 bit     Reserved
    45 – 12 bit     Timestamp (25ns)
    11 – 0 bit      Reserved

TPX3 control packets (0x7) format:
    63 - 56 bit     0x71
    55 – 48 bit     0xa0 = End of sequential readout, 0xb0 = End of data driven readout
    51 – 0 bit      Reserved



HERMES Unpacker Format. Found in signalData Structure: 
    For Packet ID
    0–31     bufferNumber
    32–39    signalType
    40–47    xPixel
    48–55    yPixel
    56–63    (padding)
    64–127   ToaFinal
    128–143  TotFinal
    144–159  (padding)
    160–191  groupID