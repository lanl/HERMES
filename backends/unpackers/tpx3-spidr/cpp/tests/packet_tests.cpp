#include "test_helpers.h"

#include <array>
#include <cstdint>

#include "unpacker.h"

namespace {

using hermes_tpx3_spidr::SpidrControlType;
using hermes_tpx3_spidr::TdcChannel;
using hermes_tpx3_spidr::TdcEdge;
using hermes_tpx3_spidr::Tpx3ControlType;
using hermes_tpx3_spidr::UnpackResult;

std::uint64_t makeIntegratedTot(const std::uint16_t pixel_address,
                                const std::uint16_t integrated_tot,
                                const std::uint16_t event_count,
                                const std::uint8_t hit_count,
                                const std::uint16_t spidr_time) {
    return (0xAULL << 60U) |
           (static_cast<std::uint64_t>(pixel_address) << 44U) |
           (static_cast<std::uint64_t>(integrated_tot & 0x3FFFU) << 30U) |
           (static_cast<std::uint64_t>(event_count & 0x03FFU) << 20U) |
           (static_cast<std::uint64_t>(hit_count & 0x0FU) << 16U) |
           spidr_time;
}

std::uint64_t makePixel(const std::uint16_t pixel_address,
                        const std::uint16_t toa,
                        const std::uint16_t tot,
                        const std::uint8_t ftoa,
                        const std::uint16_t spidr_time) {
    return (0xBULL << 60U) |
           (static_cast<std::uint64_t>(pixel_address) << 44U) |
           (static_cast<std::uint64_t>(toa & 0x3FFFU) << 30U) |
           (static_cast<std::uint64_t>(tot & 0x03FFU) << 20U) |
           (static_cast<std::uint64_t>(ftoa & 0x0FU) << 16U) |
           spidr_time;
}

std::uint64_t makeTdc(const std::uint8_t edge_code,
                      const std::uint16_t trigger_counter,
                      const std::uint64_t timestamp,
                      const std::uint8_t fine,
                      const std::uint8_t reserved) {
    return (0x6ULL << 60U) |
           (static_cast<std::uint64_t>(edge_code & 0x0FU) << 56U) |
           (static_cast<std::uint64_t>(trigger_counter & 0x0FFFU) << 44U) |
           ((timestamp & 0x7FFFFFFFFULL) << 9U) |
           (static_cast<std::uint64_t>(fine & 0x0FU) << 5U) |
           (reserved & 0x1FU);
}

void testIntegratedTot(TestContext& test) {
    UnpackResult result;
    const auto word = makeIntegratedTot(0xABCDU, 0x2345U, 0x02AAU,
                                        0x0DU, 0x9876U);
    hermes_tpx3_spidr::unpackPacket(word, 3U, 4U, 5U, result);

    test.expectEqual(result.integrated_tot_pixels.size(), std::size_t{1},
                     "integrated-ToT packet count");
    test.expectEqual(result.summary.packets_read, std::uint64_t{1},
                     "integrated total packet count");
    test.expectEqual(result.summary.integrated_tot_count, std::uint64_t{1},
                     "integrated summary count");
    const auto& packet = result.integrated_tot_pixels.front();
    test.expectEqual(packet.position.raw_word, word, "integrated raw word");
    test.expectEqual(packet.position.chip_index, std::uint8_t{3},
                     "integrated chip index");
    test.expectEqual(packet.position.chunk_index, std::size_t{4},
                     "integrated chunk index");
    test.expectEqual(packet.position.packet_index, std::size_t{5},
                     "integrated packet index");
    test.expectEqual(packet.pixel_address, std::uint16_t{0xABCD},
                     "integrated pixel address");
    test.expectEqual(packet.integrated_tot_raw, std::uint16_t{0x2345},
                     "integrated ToT");
    test.expectEqual(packet.event_count, std::uint16_t{0x02AA},
                     "integrated event count");
    test.expectEqual(packet.hit_count, std::uint8_t{0x0D},
                     "integrated hit count");
    test.expectEqual(packet.spidr_time_raw, std::uint16_t{0x9876},
                     "integrated SPIDR time");
}

void testPixels(TestContext& test) {
    UnpackResult result;
    constexpr std::uint16_t address = 0x1234U;
    const auto word = makePixel(address, 0x2345U, 0x02AAU, 0x0BU, 0x4567U);
    hermes_tpx3_spidr::unpackPacket(word, 2U, 7U, 9U, result);

    const auto& hit = result.pixel_hits.front();
    const auto double_column = (address & 0xFE00U) >> 8U;
    const auto super_pixel = (address & 0x01F8U) >> 1U;
    const auto pixel_index = address & 0x0007U;
    const auto coarse = (static_cast<std::uint64_t>(0x4567U) << 14U) +
                        0x2345U;
    test.expectEqual(hit.pixel_address, address, "pixel address");
    test.expectEqual(hit.local_x,
                     static_cast<std::uint16_t>(double_column +
                                                (pixel_index >> 2U)),
                     "pixel local x");
    test.expectEqual(hit.local_y,
                     static_cast<std::uint16_t>(super_pixel +
                                                (pixel_index & 0x3U)),
                     "pixel local y");
    test.expectEqual(hit.toa_raw, std::uint16_t{0x2345}, "pixel ToA");
    test.expectEqual(hit.ftoa_raw, std::uint8_t{0x0B}, "pixel FToA");
    test.expectEqual(hit.tot_raw, std::uint16_t{0x02AA}, "pixel ToT");
    test.expectEqual(hit.spidr_time_raw, std::uint16_t{0x4567},
                     "pixel SPIDR time");
    test.expectEqual(hit.coarse_time_25ns, coarse, "pixel coarse time");
    test.expectEqual(hit.fine_time_1p5625ns,
                     static_cast<std::int64_t>(coarse << 4U) - 0x0B,
                     "pixel fine-time subtraction");
    test.expectEqual(result.summary.pixel_hit_count, std::uint64_t{1},
                     "pixel summary count");

    UnpackResult boundaries;
    hermes_tpx3_spidr::unpackPacket(
        makePixel(0U, 0U, 0U, 15U, 0U), 0U, 0U, 0U, boundaries);
    hermes_tpx3_spidr::unpackPacket(
        makePixel(0xFFFFU, 0x3FFFU, 0x03FFU, 0U, 0xFFFFU),
        0U, 0U, 1U, boundaries);
    test.expectEqual(boundaries.pixel_hits[0].fine_time_1p5625ns,
                     std::int64_t{-15}, "signed zero-boundary pixel time");
    test.expectEqual(boundaries.pixel_hits[1].coarse_time_25ns,
                     std::uint64_t{0x3FFFFFFF}, "pixel rollover boundary");
    test.expectEqual(boundaries.pixel_hits[1].fine_time_1p5625ns,
                     std::int64_t{0x3FFFFFFF0},
                     "maximum pixel fine time");
}

void testTdc(TestContext& test) {
    UnpackResult result;
    const std::array<std::uint8_t, 4> codes{0x0FU, 0x0AU, 0x0EU, 0x0BU};
    for (std::size_t index = 0; index < codes.size(); ++index) {
        hermes_tpx3_spidr::unpackPacket(
            makeTdc(codes[index], 0x0ABCU, 0x123456789ULL, 12U, 0x1BU),
            1U, 2U, index, result);
    }

    test.expectEqual(result.summary.tdc_hit_count, std::uint64_t{4},
                     "TDC total count");
    test.expectEqual(result.summary.tdc1_rising_count, std::uint64_t{1},
                     "TDC1 rising count");
    test.expectEqual(result.summary.tdc1_falling_count, std::uint64_t{1},
                     "TDC1 falling count");
    test.expectEqual(result.summary.tdc2_rising_count, std::uint64_t{1},
                     "TDC2 rising count");
    test.expectEqual(result.summary.tdc2_falling_count, std::uint64_t{1},
                     "TDC2 falling count");
    const auto& first = result.tdc_hits.front();
    test.expect(first.channel == TdcChannel::tdc1, "TDC1 channel");
    test.expect(first.edge == TdcEdge::rising, "TDC rising edge");
    test.expectEqual(first.trigger_counter, std::uint16_t{0x0ABC},
                     "TDC trigger counter");
    test.expectEqual(first.tdc_timestamp_raw, std::uint64_t{0x123456789},
                     "TDC 35-bit timestamp");
    test.expectEqual(first.tdc_fine_raw, std::uint8_t{12}, "TDC fine value");
    test.expectEqual(first.reserved, std::uint8_t{0x1B}, "TDC reserved bits");
    test.expectEqual(first.time_canonical_ticks,
                     std::uint64_t{0x123456789} * 1536U + 11U * 128U,
                     "exact TDC canonical time");

    UnpackResult fine_values;
    hermes_tpx3_spidr::unpackPacket(
        makeTdc(0x0FU, 0U, 10U, 0U, 0U), 0U, 0U, 0U, fine_values);
    hermes_tpx3_spidr::unpackPacket(
        makeTdc(0x0FU, 0U, 10U, 1U, 0U), 0U, 0U, 1U, fine_values);
    hermes_tpx3_spidr::unpackPacket(
        makeTdc(0x0FU, 0U, 10U, 12U, 0U), 0U, 0U, 2U, fine_values);
    hermes_tpx3_spidr::unpackPacket(
        makeTdc(0x01U, 0U, 10U, 13U, 0U), 0U, 0U, 3U, fine_values);
    test.expect(!fine_values.tdc_hits[0].fine_value_valid,
                "TDC fine zero invalid");
    test.expect(fine_values.tdc_hits[1].fine_value_valid,
                "TDC fine one valid");
    test.expectEqual(fine_values.tdc_hits[1].time_canonical_ticks,
                     std::uint64_t{10U * 1536U},
                     "TDC fine one has zero offset");
    test.expectEqual(fine_values.tdc_hits[2].time_canonical_ticks,
                     std::uint64_t{10U * 1536U + 11U * 128U},
                     "TDC fine twelve offset");
    test.expectEqual(fine_values.summary.invalid_tdc_fine_value_count,
                     std::uint64_t{2}, "invalid TDC fine count");
    test.expectEqual(fine_values.summary.unknown_tdc_edge_count,
                     std::uint64_t{1}, "unknown TDC edge count");
    test.expectEqual(fine_values.summary.errors.size(), std::size_t{2},
                     "invalid TDC error count");
    test.expectEqual(fine_values.summary.warnings.size(), std::size_t{1},
                     "unknown TDC warning count");
}

void testControlsAndUnknown(TestContext& test) {
    UnpackResult result;
    const auto packet_count = (0x50ULL << 56U) | (0xABULL << 48U) |
                              0x0000123456789ABCULL;
    const auto shutter_open = (0x5FULL << 56U) | (0x155ULL << 46U) |
                              (0x23456789ULL << 12U) | 0x0ABCU;
    const auto shutter_close = (0x5AULL << 56U) | (0x12345ULL << 12U);
    const auto heartbeat = (0x5CULL << 56U) | (0x23456ULL << 12U);
    const auto unknown_spidr = (0x51ULL << 56U) | 0x1234ULL;
    const auto sequential_end = (0x71A0ULL << 48U) | 0x123456789ABCULL;
    const auto data_driven_end = (0x71B0ULL << 48U) | 0xABCDEF012345ULL;
    const auto unknown_tpx3 = (0x7199ULL << 48U) | 0x111122223333ULL;
    const auto unknown_packet = 0x8123456789ABCDEFULL;

    const std::array<std::uint64_t, 9> words{
        packet_count, shutter_open, shutter_close, heartbeat, unknown_spidr,
        sequential_end, data_driven_end, unknown_tpx3, unknown_packet};
    for (std::size_t index = 0; index < words.size(); ++index) {
        hermes_tpx3_spidr::unpackPacket(words[index], 6U, 7U, index, result);
    }

    test.expectEqual(result.summary.spidr_control_count, std::uint64_t{5},
                     "SPIDR control count");
    test.expectEqual(result.summary.packets_read, std::uint64_t{9},
                     "control test total packet count");
    test.expectEqual(result.summary.packet_count_control_count,
                     std::uint64_t{1}, "packet-count control count");
    test.expectEqual(result.summary.shutter_open_count, std::uint64_t{1},
                     "shutter-open count");
    test.expectEqual(result.summary.shutter_close_count, std::uint64_t{1},
                     "shutter-close count");
    test.expectEqual(result.summary.heartbeat_count, std::uint64_t{1},
                     "heartbeat count");
    test.expectEqual(result.summary.unknown_spidr_control_count,
                     std::uint64_t{1}, "unknown SPIDR count");
    test.expectEqual(result.spidr_controls[0].packet_count,
                     std::uint64_t{0x123456789ABC}, "packet-count value");
    test.expectEqual(result.spidr_controls[0].reserved_high,
                     std::uint16_t{0xAB}, "packet-count reserved byte");
    test.expect(result.spidr_controls[1].type ==
                    SpidrControlType::shutter_open,
                "shutter-open type");
    test.expectEqual(result.spidr_controls[1].timestamp_raw,
                     std::uint64_t{0x23456789}, "shutter timestamp");
    test.expectEqual(result.spidr_controls[1].reserved_high,
                     std::uint16_t{0x155}, "shutter high reserved bits");
    test.expectEqual(result.spidr_controls[1].reserved_low,
                     std::uint16_t{0xABC}, "shutter low reserved bits");

    test.expectEqual(result.summary.tpx3_control_count, std::uint64_t{3},
                     "TPX3 control count");
    test.expectEqual(result.summary.end_of_sequential_readout_count,
                     std::uint64_t{1}, "sequential-end count");
    test.expectEqual(result.summary.end_of_data_driven_readout_count,
                     std::uint64_t{1}, "data-driven-end count");
    test.expectEqual(result.summary.unknown_tpx3_control_count,
                     std::uint64_t{1}, "unknown TPX3 count");
    test.expect(result.tpx3_controls[0].type ==
                    Tpx3ControlType::end_of_sequential_readout,
                "sequential-end type");
    test.expectEqual(result.tpx3_controls[2].control_value_raw,
                     std::uint16_t{0x7199}, "unknown TPX3 control value");
    test.expectEqual(result.tpx3_controls[2].payload_raw,
                     std::uint64_t{0x111122223333},
                     "unknown TPX3 payload");

    test.expectEqual(result.unknown_packets.size(), std::size_t{1},
                     "unknown packet vector count");
    test.expectEqual(result.unknown_packets[0].position.raw_word,
                     unknown_packet, "unknown raw word");
    test.expectEqual(result.unknown_packets[0].most_significant_byte,
                     std::uint8_t{0x81}, "unknown most-significant byte");
    test.expectEqual(result.unknown_packets[0].position.chip_index,
                     std::uint8_t{6}, "unknown chip index");
    test.expectEqual(result.unknown_packets[0].position.chunk_index,
                     std::size_t{7}, "unknown chunk index");
    test.expectEqual(result.unknown_packets[0].position.packet_index,
                     std::size_t{8}, "unknown packet index");
    test.expectEqual(result.summary.warnings.size(), std::size_t{3},
                     "control and unknown warning count");
}

}  // namespace

int main() {
    TestContext test;
    testIntegratedTot(test);
    testPixels(test);
    testTdc(test);
    testControlsAndUnknown(test);
    return test.finish();
}
