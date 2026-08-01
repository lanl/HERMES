#include "test_helpers.h"
#include "timestamp_calculator.h"

#include <cstdint>
#include <limits>

using namespace hermes_tpx3_spidr;

namespace {

void testPixelTimestampCalculation(TestContext& test) {
    PixelHit pixel;
    pixel.spidr_time_raw = 0x1234;
    pixel.toa_raw = 0x2ABC;
    pixel.ftoa_raw = 0x5;
    pixel.coarse_time_25ns = (static_cast<std::uint64_t>(0x1234) << 14U) | 0x2ABC;
    pixel.fine_time_1p5625ns = static_cast<std::int64_t>(pixel.coarse_time_25ns << 4U) - 0x5;

    const auto timestamp = calculatePixelTimestamp(pixel);
    const auto expected = static_cast<std::uint64_t>(pixel.fine_time_1p5625ns) * 768U;
    test.expectEqual(timestamp, expected, "pixel timestamp calculation");

    PixelHit zero_pixel;
    zero_pixel.coarse_time_25ns = 0;
    zero_pixel.fine_time_1p5625ns = 0;
    test.expectEqual(calculatePixelTimestamp(zero_pixel), std::uint64_t{0},
                     "zero pixel timestamp");

    PixelHit max_ftoa_pixel;
    max_ftoa_pixel.coarse_time_25ns = 100;
    max_ftoa_pixel.ftoa_raw = 15;
    max_ftoa_pixel.fine_time_1p5625ns = static_cast<std::int64_t>(100 << 4U) - 15;
    const auto max_ftoa_timestamp = calculatePixelTimestamp(max_ftoa_pixel);
    const auto max_ftoa_expected =
        static_cast<std::uint64_t>(max_ftoa_pixel.fine_time_1p5625ns) * 768U;
    test.expectEqual(max_ftoa_timestamp, max_ftoa_expected,
                     "pixel with max ftoa");
}

void testTdcTimestampCalculation(TestContext& test) {
    TdcHit valid_tdc;
    valid_tdc.tdc_timestamp_raw = 0x123456789;
    valid_tdc.tdc_fine_raw = 12;
    valid_tdc.fine_value_valid = true;

    const auto timestamp = calculateTdcTimestamp(valid_tdc);
    test.expect(timestamp.has_value(), "valid TDC returns timestamp");
    const auto expected = 0x123456789ULL * 1536U + 11U * 128U;
    test.expectEqual(*timestamp, expected, "TDC timestamp with fine=12");

    TdcHit fine_one_tdc;
    fine_one_tdc.tdc_timestamp_raw = 100;
    fine_one_tdc.tdc_fine_raw = 1;
    fine_one_tdc.fine_value_valid = true;
    const auto fine_one_timestamp = calculateTdcTimestamp(fine_one_tdc);
    test.expectEqual(*fine_one_timestamp, 100ULL * 1536U,
                     "TDC fine=1 adds zero offset");

    TdcHit invalid_tdc;
    invalid_tdc.tdc_timestamp_raw = 100;
    invalid_tdc.tdc_fine_raw = 0;
    invalid_tdc.fine_value_valid = false;
    const auto invalid_timestamp = calculateTdcTimestamp(invalid_tdc);
    test.expect(!invalid_timestamp.has_value(),
                "invalid TDC fine returns nullopt");
}

void testTdcTriggerTypeMapping(TestContext& test) {
    TdcHit tdc;

    tdc.channel = TdcChannel::tdc1;
    tdc.edge = TdcEdge::rising;
    test.expectEqual(getTdcTriggerType(tdc), std::uint8_t{0},
                     "TDC1 rising = 0");

    tdc.channel = TdcChannel::tdc1;
    tdc.edge = TdcEdge::falling;
    test.expectEqual(getTdcTriggerType(tdc), std::uint8_t{1},
                     "TDC1 falling = 1");

    tdc.channel = TdcChannel::tdc2;
    tdc.edge = TdcEdge::rising;
    test.expectEqual(getTdcTriggerType(tdc), std::uint8_t{2},
                     "TDC2 rising = 2");

    tdc.channel = TdcChannel::tdc2;
    tdc.edge = TdcEdge::falling;
    test.expectEqual(getTdcTriggerType(tdc), std::uint8_t{3},
                     "TDC2 falling = 3");

    tdc.channel = TdcChannel::unknown;
    tdc.edge = TdcEdge::unknown;
    test.expectEqual(getTdcTriggerType(tdc), std::uint8_t{255},
                     "unknown TDC returns 255");
}

void testGlobalTimestampCalculation(TestContext& test) {
    GlobalTimestamp global;
    global.global_time_high_raw = 0x1234;
    global.global_time_low_raw = 0x56789ABC;
    global.global_time_raw =
        (static_cast<std::uint64_t>(0x1234) << 32U) | 0x56789ABC;

    const auto timestamp = calculateGlobalTimestamp(global);
    const auto expected = global.global_time_raw * 12288U;
    test.expectEqual(timestamp, expected, "global timestamp calculation");

    GlobalTimestamp zero_global;
    zero_global.global_time_raw = 0;
    test.expectEqual(calculateGlobalTimestamp(zero_global), std::uint64_t{0},
                     "zero global timestamp");
}

void testControlTimestampCalculation(TestContext& test) {
    SpidrControl packet_count_control;
    packet_count_control.type = SpidrControlType::packet_count;
    packet_count_control.timestamp_raw = 12345;
    const auto packet_count_timestamp =
        calculateControlTimestamp(packet_count_control);
    test.expect(!packet_count_timestamp.has_value(),
                "packet_count control has no timestamp");

    SpidrControl shutter_control;
    shutter_control.type = SpidrControlType::shutter_open;
    shutter_control.timestamp_raw = 0x23456789;
    const auto shutter_timestamp = calculateControlTimestamp(shutter_control);
    test.expect(shutter_timestamp.has_value(), "shutter control has timestamp");
    test.expectEqual(*shutter_timestamp, 0x23456789ULL * 12288U,
                     "shutter timestamp calculation");
}

void testPixelOutputRowConversion(TestContext& test) {
    PixelHit pixel;
    pixel.position.chunk_index = 10;
    pixel.position.packet_index = 20;
    pixel.local_x = 100;
    pixel.local_y = 200;
    pixel.tot_raw = 50;
    pixel.fine_time_1p5625ns = 1000;

    const auto row = convertPixelToOutputRow(pixel);
    test.expect(row.has_value(), "pixel converts to output row");
    test.expectEqual(row->chunk_index, std::size_t{10}, "pixel chunk_index");
    test.expectEqual(row->packet_index, std::size_t{20}, "pixel packet_index");
    test.expectEqual(row->local_x, std::uint16_t{100}, "pixel local_x");
    test.expectEqual(row->local_y, std::uint16_t{200}, "pixel local_y");
    test.expectEqual(row->tot_raw, std::uint16_t{50}, "pixel tot_raw");
    test.expectEqual(row->timestamp_canonical, 1000ULL * 768U,
                     "pixel timestamp_canonical");
}

void testTdcOutputRowConversion(TestContext& test) {
    TdcHit valid_tdc;
    valid_tdc.position.chunk_index = 5;
    valid_tdc.position.packet_index = 15;
    valid_tdc.channel = TdcChannel::tdc1;
    valid_tdc.edge = TdcEdge::falling;
    valid_tdc.tdc_timestamp_raw = 500;
    valid_tdc.tdc_fine_raw = 6;
    valid_tdc.fine_value_valid = true;

    const auto row = convertTdcToOutputRow(valid_tdc);
    test.expect(row.has_value(), "valid TDC converts to output row");
    test.expectEqual(row->chunk_index, std::size_t{5}, "TDC chunk_index");
    test.expectEqual(row->packet_index, std::size_t{15}, "TDC packet_index");
    test.expectEqual(row->trigger_type, std::uint8_t{1}, "TDC1 falling type");
    test.expectEqual(row->timestamp_canonical, 500ULL * 1536U + 5U * 128U,
                     "TDC timestamp_canonical");

    TdcHit invalid_tdc;
    invalid_tdc.fine_value_valid = false;
    const auto invalid_row = convertTdcToOutputRow(invalid_tdc);
    test.expect(!invalid_row.has_value(),
                "invalid TDC does not convert to output row");
}

void testGlobalOutputRowConversion(TestContext& test) {
    GlobalTimestamp global;
    global.high_packet.chunk_index = 7;
    global.high_packet.packet_index = 8;
    global.global_time_raw = 0x123456789ABC;

    const auto row = convertGlobalToOutputRow(global);
    test.expectEqual(row.chunk_index, std::size_t{7},
                     "global uses high packet chunk_index");
    test.expectEqual(row.packet_index, std::size_t{8},
                     "global uses high packet packet_index");
    test.expectEqual(row.timestamp_canonical, 0x123456789ABCULL * 12288U,
                     "global timestamp_canonical");
}

void testControlOutputRowConversion(TestContext& test) {
    SpidrControl spidr;
    spidr.position.chunk_index = 3;
    spidr.position.packet_index = 4;
    spidr.type = SpidrControlType::shutter_open;
    spidr.packet_id = 0x5F;
    spidr.subtype = 0x0F;
    spidr.timestamp_raw = 1000;
    spidr.reserved_high = 0x100;
    spidr.reserved_low = 0x200;

    const auto spidr_row = convertSpidrControlToOutputRow(spidr);
    test.expectEqual(spidr_row.source, std::uint8_t{0}, "SPIDR source=0");
    test.expectEqual(spidr_row.chunk_index, std::size_t{3},
                     "SPIDR chunk_index");
    test.expectEqual(spidr_row.packet_id, std::uint8_t{0x5F},
                     "SPIDR packet_id");
    test.expect(spidr_row.packet_id_present, "SPIDR packet_id_present");
    test.expect(spidr_row.timestamp_canonical_present,
                "SPIDR shutter has timestamp");
    test.expectEqual(spidr_row.timestamp_canonical, 1000ULL * 12288U,
                     "SPIDR timestamp value");

    Tpx3Control tpx3;
    tpx3.position.chunk_index = 6;
    tpx3.position.packet_index = 7;
    tpx3.type = Tpx3ControlType::end_of_sequential_readout;
    tpx3.control_value_raw = 0x71A0;
    tpx3.payload_raw = 0x123456789ABC;

    const auto tpx3_row = convertTpx3ControlToOutputRow(tpx3);
    test.expectEqual(tpx3_row.source, std::uint8_t{1}, "TPX3 source=1");
    test.expectEqual(tpx3_row.chunk_index, std::size_t{6}, "TPX3 chunk_index");
    test.expectEqual(tpx3_row.control_value_raw, std::uint16_t{0x71A0},
                     "TPX3 control_value_raw");
    test.expect(tpx3_row.control_value_raw_present,
                "TPX3 control_value_raw_present");
    test.expect(!tpx3_row.timestamp_canonical_present,
                "TPX3 controls have no timestamp");
}

void testUnknownOutputRowConversion(TestContext& test) {
    UnknownPacket unknown;
    unknown.position.chunk_index = 9;
    unknown.position.packet_index = 10;
    unknown.position.raw_word = 0x8123456789ABCDEF;
    unknown.most_significant_byte = 0x81;

    const auto row = convertUnknownToOutputRow(unknown);
    test.expectEqual(row.chunk_index, std::size_t{9}, "unknown chunk_index");
    test.expectEqual(row.packet_index, std::size_t{10},
                     "unknown packet_index");
    test.expectEqual(row.raw_word, 0x8123456789ABCDEFULL, "unknown raw_word");
    test.expectEqual(row.most_significant_byte, std::uint8_t{0x81},
                     "unknown most_significant_byte");
}

}  // namespace

int main() {
    TestContext test;
    testPixelTimestampCalculation(test);
    testTdcTimestampCalculation(test);
    testTdcTriggerTypeMapping(test);
    testGlobalTimestampCalculation(test);
    testControlTimestampCalculation(test);
    testPixelOutputRowConversion(test);
    testTdcOutputRowConversion(test);
    testGlobalOutputRowConversion(test);
    testControlOutputRowConversion(test);
    testUnknownOutputRowConversion(test);
    return test.finish();
}
