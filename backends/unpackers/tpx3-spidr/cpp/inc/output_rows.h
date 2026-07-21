#ifndef HERMES_TPX3_SPIDR_OUTPUT_ROWS_H
#define HERMES_TPX3_SPIDR_OUTPUT_ROWS_H

#include <cstddef>
#include <cstdint>

namespace hermes_tpx3_spidr {

struct PixelOutputRow {
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
    std::uint64_t source_packet_order = 0;
    std::uint16_t local_x = 0;
    std::uint16_t local_y = 0;
    std::uint16_t tot_raw = 0;
    std::uint64_t timestamp_canonical = 0;
};

struct TdcOutputRow {
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
    std::uint64_t source_packet_order = 0;
    std::uint8_t trigger_type = 0;
    std::uint64_t timestamp_canonical = 0;
};

struct GlobalOutputRow {
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
    std::uint64_t source_packet_order = 0;
    std::uint64_t timestamp_canonical = 0;
};

struct ControlOutputRow {
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
    std::uint64_t source_packet_order = 0;
    std::uint8_t source = 0;
    std::uint16_t control_type = 0;
    std::uint8_t packet_id = 0;
    bool packet_id_present = false;
    std::uint8_t subtype = 0;
    bool subtype_present = false;
    std::uint64_t packet_count = 0;
    bool packet_count_present = false;
    std::uint16_t reserved_high = 0;
    bool reserved_high_present = false;
    std::uint16_t reserved_low = 0;
    bool reserved_low_present = false;
    std::uint16_t control_value_raw = 0;
    bool control_value_raw_present = false;
    std::uint64_t control_payload_raw = 0;
    bool control_payload_raw_present = false;
    std::uint64_t timestamp_canonical = 0;
    bool timestamp_canonical_present = false;
};

struct UnknownOutputRow {
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
    std::uint64_t source_packet_order = 0;
    std::uint64_t raw_word = 0;
    std::uint8_t most_significant_byte = 0;
};

}  // namespace hermes_tpx3_spidr

#endif
