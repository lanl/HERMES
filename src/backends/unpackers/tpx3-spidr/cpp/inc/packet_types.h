#ifndef HERMES_TPX3_SPIDR_PACKET_TYPES_H
#define HERMES_TPX3_SPIDR_PACKET_TYPES_H

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace hermes_tpx3_spidr {

struct PacketPosition {
    std::uint64_t raw_word = 0;
    std::uint8_t chip_index = 0;
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
};

struct ChunkHeader {
    std::uint64_t raw_header = 0;
    std::uint16_t chunk_size_bytes = 0;
    std::uint8_t mode_or_reserved = 0;
    std::uint8_t chip_index = 0;
    std::size_t chunk_index = 0;
};

struct IntegratedTotPixel {
    PacketPosition position;
    std::uint16_t pixel_address = 0;
    std::uint16_t integrated_tot_raw = 0;
    std::uint16_t event_count = 0;
    std::uint8_t hit_count = 0;
    std::uint16_t spidr_time_raw = 0;
};

struct PixelHit {
    PacketPosition position;
    std::uint16_t pixel_address = 0;
    std::uint16_t local_x = 0;
    std::uint16_t local_y = 0;
    std::uint16_t toa_raw = 0;
    std::uint8_t ftoa_raw = 0;
    std::uint16_t tot_raw = 0;
    std::uint16_t spidr_time_raw = 0;
    std::uint64_t coarse_time_25ns = 0;
    std::int64_t fine_time_1p5625ns = 0;
};

enum class TdcChannel {
    tdc1,
    tdc2,
    unknown,
};

enum class TdcEdge {
    rising,
    falling,
    unknown,
};

struct TdcHit {
    PacketPosition position;
    std::uint8_t edge_code = 0;
    TdcChannel channel = TdcChannel::unknown;
    TdcEdge edge = TdcEdge::unknown;
    std::uint16_t trigger_counter = 0;
    std::uint64_t tdc_timestamp_raw = 0;
    std::uint8_t tdc_fine_raw = 0;
    std::uint8_t reserved = 0;
    bool fine_value_valid = false;
    std::uint64_t time_canonical_ticks = 0;
};

struct GlobalTimeLow {
    PacketPosition position;
    std::uint8_t reserved = 0;
    std::uint32_t global_time_low_raw = 0;
    std::uint16_t spidr_time_raw = 0;
};

struct GlobalTimeHigh {
    PacketPosition position;
    std::uint32_t reserved = 0;
    std::uint16_t global_time_high_raw = 0;
    std::uint16_t spidr_time_raw = 0;
};

struct GlobalTimestamp {
    PacketPosition low_packet;
    PacketPosition high_packet;
    std::uint16_t global_time_high_raw = 0;
    std::uint32_t global_time_low_raw = 0;
    std::uint64_t global_time_raw = 0;
};

enum class SpidrControlType {
    packet_count,
    shutter_open,
    shutter_close,
    heartbeat,
    unknown,
};

struct SpidrControl {
    PacketPosition position;
    SpidrControlType type = SpidrControlType::unknown;
    std::uint8_t packet_id = 0;
    std::uint8_t subtype = 0;
    std::uint64_t packet_count = 0;
    std::uint64_t timestamp_raw = 0;
    std::uint16_t reserved_high = 0;
    std::uint16_t reserved_low = 0;
};

enum class Tpx3ControlType {
    end_of_sequential_readout,
    end_of_data_driven_readout,
    request_time_low,
    request_time_high,
    other_chip_command,
    unknown,
};

struct Tpx3Control {
    PacketPosition position;
    Tpx3ControlType type = Tpx3ControlType::unknown;
    std::uint16_t control_value_raw = 0;
    std::uint64_t payload_raw = 0;
};

struct UnknownPacket {
    PacketPosition position;
    std::uint8_t most_significant_byte = 0;
};

struct UnpackSummary {
    std::uint64_t bytes_read = 0;
    std::uint64_t chunks_read = 0;
    std::uint64_t packets_read = 0;
    std::uint64_t integrated_tot_count = 0;
    std::uint64_t pixel_data_packet_count = 0;
    std::uint64_t tdc_timestamp_count = 0;
    std::uint64_t tdc1_rising_count = 0;
    std::uint64_t tdc1_falling_count = 0;
    std::uint64_t tdc2_rising_count = 0;
    std::uint64_t tdc2_falling_count = 0;
    std::uint64_t unknown_tdc_edge_count = 0;
    std::uint64_t global_time_low_count = 0;
    std::uint64_t global_time_high_count = 0;
    std::uint64_t heartbeat_packet_count = 0;
    std::uint64_t spidr_control_count = 0;
    std::uint64_t packet_count_control_count = 0;
    std::uint64_t shutter_open_count = 0;
    std::uint64_t shutter_close_count = 0;
    std::uint64_t heartbeat_count = 0;
    std::uint64_t unknown_spidr_control_count = 0;
    std::uint64_t tpx3_control_count = 0;
    std::uint64_t end_of_sequential_readout_count = 0;
    std::uint64_t end_of_data_driven_readout_count = 0;
    std::uint64_t request_time_low_count = 0;
    std::uint64_t request_time_high_count = 0;
    std::uint64_t other_chip_command_count = 0;
    std::uint64_t unknown_tpx3_control_count = 0;
    std::uint64_t malformed_chunk_count = 0;
    std::uint64_t truncated_chunk_count = 0;
    std::uint64_t invalid_tdc_fine_value_count = 0;
    std::uint64_t unrecognized_packet_count = 0;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;
};

struct UnpackResult {
    std::vector<ChunkHeader> chunk_headers;
    std::vector<IntegratedTotPixel> integrated_tot_pixels;
    std::vector<PixelHit> pixel_hits;
    std::vector<TdcHit> tdc_hits;
    std::vector<GlobalTimeLow> global_time_lows;
    std::vector<GlobalTimeHigh> global_time_highs;
    std::vector<GlobalTimestamp> global_timestamps;
    std::vector<SpidrControl> spidr_controls;
    std::vector<Tpx3Control> tpx3_controls;
    std::vector<UnknownPacket> unknown_packets;
    UnpackSummary summary;
};

}  // namespace hermes_tpx3_spidr

#endif
