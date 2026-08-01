#include "timestamp_calculator.h"

namespace hermes_tpx3_spidr {

std::uint64_t calculatePixelTimestamp(const PixelHit& pixel) {
    if (pixel.fine_time_1p5625ns <= 0) {
        return 0;
    }
    return static_cast<std::uint64_t>(pixel.fine_time_1p5625ns) * 768U;
}

std::optional<std::uint64_t> calculateTdcTimestamp(const TdcHit& tdc) {
    if (!tdc.fine_value_valid) {
        return std::nullopt;
    }
    const auto coarse_ticks = tdc.tdc_timestamp_raw * 1536U;
    const auto fine_ticks = static_cast<std::uint64_t>(tdc.tdc_fine_raw - 1U) * 128U;
    return coarse_ticks + fine_ticks;
}

std::uint8_t getTdcTriggerType(const TdcHit& tdc) {
    if (tdc.channel == TdcChannel::tdc1 && tdc.edge == TdcEdge::rising) {
        return 0;
    }
    if (tdc.channel == TdcChannel::tdc1 && tdc.edge == TdcEdge::falling) {
        return 1;
    }
    if (tdc.channel == TdcChannel::tdc2 && tdc.edge == TdcEdge::rising) {
        return 2;
    }
    if (tdc.channel == TdcChannel::tdc2 && tdc.edge == TdcEdge::falling) {
        return 3;
    }
    return 255;
}

std::uint64_t calculateGlobalTimestamp(const GlobalTimestamp& global) {
    return global.global_time_raw * 12288U;
}

std::optional<std::uint64_t> calculateControlTimestamp(
    const SpidrControl& control) {
    if (control.type == SpidrControlType::packet_count) {
        return std::nullopt;
    }
    return control.timestamp_raw * 12288U;
}

std::optional<PixelOutputRow> convertPixelToOutputRow(const PixelHit& pixel) {
    return PixelOutputRow{
        pixel.position.chunk_index,
        pixel.position.packet_index,
        0,
        pixel.local_x,
        pixel.local_y,
        pixel.tot_raw,
        calculatePixelTimestamp(pixel),
    };
}

std::optional<TdcOutputRow> convertTdcToOutputRow(const TdcHit& tdc) {
    const auto timestamp = calculateTdcTimestamp(tdc);
    if (!timestamp.has_value()) {
        return std::nullopt;
    }
    return TdcOutputRow{
        tdc.position.chunk_index,
        tdc.position.packet_index,
        0,
        getTdcTriggerType(tdc),
        *timestamp,
    };
}

GlobalOutputRow convertGlobalToOutputRow(const GlobalTimestamp& global) {
    return GlobalOutputRow{
        global.high_packet.chunk_index,
        global.high_packet.packet_index,
        0,
        calculateGlobalTimestamp(global),
    };
}

ControlOutputRow convertSpidrControlToOutputRow(const SpidrControl& control) {
    ControlOutputRow row;
    row.chunk_index = control.position.chunk_index;
    row.packet_index = control.position.packet_index;
    row.source_packet_order = 0;
    row.source = 0;
    row.control_type = static_cast<std::uint16_t>(control.type);
    row.packet_id = control.packet_id;
    row.packet_id_present = true;
    row.subtype = control.subtype;
    row.subtype_present = true;

    if (control.type == SpidrControlType::packet_count) {
        row.packet_count = control.packet_count;
        row.packet_count_present = true;
        row.reserved_high = control.reserved_high;
        row.reserved_high_present = true;
    } else {
        row.reserved_high = control.reserved_high;
        row.reserved_high_present = true;
        row.reserved_low = control.reserved_low;
        row.reserved_low_present = true;
        const auto timestamp = calculateControlTimestamp(control);
        if (timestamp.has_value()) {
            row.timestamp_canonical = *timestamp;
            row.timestamp_canonical_present = true;
        }
    }

    return row;
}

ControlOutputRow convertTpx3ControlToOutputRow(const Tpx3Control& control) {
    ControlOutputRow row;
    row.chunk_index = control.position.chunk_index;
    row.packet_index = control.position.packet_index;
    row.source_packet_order = 0;
    row.source = 1;
    row.control_type = static_cast<std::uint16_t>(control.type);
    row.control_value_raw = control.control_value_raw;
    row.control_value_raw_present = true;
    row.control_payload_raw = control.payload_raw;
    row.control_payload_raw_present = true;
    return row;
}

UnknownOutputRow convertUnknownToOutputRow(const UnknownPacket& unknown) {
    return UnknownOutputRow{
        unknown.position.chunk_index,
        unknown.position.packet_index,
        0,
        unknown.position.raw_word,
        unknown.most_significant_byte,
    };
}

}  // namespace hermes_tpx3_spidr
