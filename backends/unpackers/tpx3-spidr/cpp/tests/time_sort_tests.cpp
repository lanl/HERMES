#include "test_helpers.h"
#include "time_sort.h"

#include <cstdint>

using namespace hermes_tpx3_spidr;

namespace {

void testBuildChipAnchorIndexSingleChip(TestContext& test) {
    std::vector<GlobalTimestamp> global_timestamps;

    GlobalTimestamp g1;
    g1.high_packet.chip_index = 0;
    g1.high_packet.chunk_index = 0;
    g1.high_packet.packet_index = 10;
    g1.global_time_raw = 0x100000000000;
    global_timestamps.push_back(g1);

    GlobalTimestamp g2;
    g2.high_packet.chip_index = 0;
    g2.high_packet.chunk_index = 0;
    g2.high_packet.packet_index = 20;
    g2.global_time_raw = 0x200000000000;
    global_timestamps.push_back(g2);

    GlobalTimestamp g3;
    g3.high_packet.chip_index = 0;
    g3.high_packet.chunk_index = 1;
    g3.high_packet.packet_index = 5;
    g3.global_time_raw = 0x300000000000;
    global_timestamps.push_back(g3);

    AnchorIndexDiagnostics diagnostics;
    const auto index = buildChipAnchorIndex(global_timestamps, 0, diagnostics);

    test.expectEqual(index.anchors.size(), std::size_t{3},
                     "chip 0 has 3 anchors");
    test.expectEqual(diagnostics.total_anchors, std::uint64_t{3},
                     "diagnostics total anchors");

    test.expectEqual(index.anchors[0].global_time_48bit,
                     std::uint64_t{0x100000000000}, "first anchor time");
    test.expectEqual(index.anchors[0].chunk_index, std::size_t{0},
                     "first anchor chunk");
    test.expectEqual(index.anchors[0].packet_index, std::size_t{10},
                     "first anchor packet");

    test.expectEqual(index.anchors[1].global_time_48bit,
                     std::uint64_t{0x200000000000}, "second anchor time");
    test.expectEqual(index.anchors[1].packet_index, std::size_t{20},
                     "second anchor packet");

    test.expectEqual(index.anchors[2].global_time_48bit,
                     std::uint64_t{0x300000000000}, "third anchor time");
    test.expectEqual(index.anchors[2].chunk_index, std::size_t{1},
                     "third anchor chunk");
}

void testBuildChipAnchorIndexMultipleChips(TestContext& test) {
    std::vector<GlobalTimestamp> global_timestamps;

    GlobalTimestamp g1;
    g1.high_packet.chip_index = 0;
    g1.high_packet.chunk_index = 0;
    g1.high_packet.packet_index = 10;
    g1.global_time_raw = 0x100000000000;
    global_timestamps.push_back(g1);

    GlobalTimestamp g2;
    g2.high_packet.chip_index = 1;
    g2.high_packet.chunk_index = 0;
    g2.high_packet.packet_index = 15;
    g2.global_time_raw = 0x150000000000;
    global_timestamps.push_back(g2);

    GlobalTimestamp g3;
    g3.high_packet.chip_index = 0;
    g3.high_packet.chunk_index = 0;
    g3.high_packet.packet_index = 20;
    g3.global_time_raw = 0x200000000000;
    global_timestamps.push_back(g3);

    AnchorIndexDiagnostics diag0;
    const auto index0 = buildChipAnchorIndex(global_timestamps, 0, diag0);

    test.expectEqual(index0.anchors.size(), std::size_t{2},
                     "chip 0 has 2 anchors");
    test.expectEqual(diag0.total_anchors, std::uint64_t{2},
                     "chip 0 diagnostics");

    AnchorIndexDiagnostics diag1;
    const auto index1 = buildChipAnchorIndex(global_timestamps, 1, diag1);

    test.expectEqual(index1.anchors.size(), std::size_t{1},
                     "chip 1 has 1 anchor");
    test.expectEqual(diag1.total_anchors, std::uint64_t{1},
                     "chip 1 diagnostics");
}

void testBuildChipAnchorIndexNoAnchors(TestContext& test) {
    std::vector<GlobalTimestamp> global_timestamps;

    AnchorIndexDiagnostics diagnostics;
    const auto index = buildChipAnchorIndex(global_timestamps, 0, diagnostics);

    test.expectEqual(index.anchors.size(), std::size_t{0}, "no anchors");
    test.expectEqual(diagnostics.total_anchors, std::uint64_t{0},
                     "diagnostics zero");
}

void testBuildChipAnchorIndexSorting(TestContext& test) {
    std::vector<GlobalTimestamp> global_timestamps;

    GlobalTimestamp g1;
    g1.high_packet.chip_index = 0;
    g1.high_packet.chunk_index = 1;
    g1.high_packet.packet_index = 5;
    g1.global_time_raw = 0x300000000000;
    global_timestamps.push_back(g1);

    GlobalTimestamp g2;
    g2.high_packet.chip_index = 0;
    g2.high_packet.chunk_index = 0;
    g2.high_packet.packet_index = 20;
    g2.global_time_raw = 0x200000000000;
    global_timestamps.push_back(g2);

    GlobalTimestamp g3;
    g3.high_packet.chip_index = 0;
    g3.high_packet.chunk_index = 0;
    g3.high_packet.packet_index = 10;
    g3.global_time_raw = 0x100000000000;
    global_timestamps.push_back(g3);

    AnchorIndexDiagnostics diagnostics;
    const auto index = buildChipAnchorIndex(global_timestamps, 0, diagnostics);

    test.expectEqual(index.anchors[0].chunk_index, std::size_t{0},
                     "sorted: chunk 0 first");
    test.expectEqual(index.anchors[0].packet_index, std::size_t{10},
                     "sorted: packet 10 before 20");

    test.expectEqual(index.anchors[1].chunk_index, std::size_t{0},
                     "sorted: still chunk 0");
    test.expectEqual(index.anchors[1].packet_index, std::size_t{20},
                     "sorted: packet 20");

    test.expectEqual(index.anchors[2].chunk_index, std::size_t{1},
                     "sorted: chunk 1 last");
}

void testSortByTimestampAndOrder(TestContext& test) {
    std::vector<PixelOutputRow> pixels;

    PixelOutputRow p1;
    p1.timestamp_canonical = 500;
    p1.source_packet_order = 3;
    p1.packet_index = 3;
    pixels.push_back(p1);

    PixelOutputRow p2;
    p2.timestamp_canonical = 100;
    p2.source_packet_order = 1;
    p2.packet_index = 1;
    pixels.push_back(p2);

    PixelOutputRow p3;
    p3.timestamp_canonical = 300;
    p3.source_packet_order = 4;
    p3.packet_index = 4;
    pixels.push_back(p3);

    PixelOutputRow p4;
    p4.timestamp_canonical = 300;
    p4.source_packet_order = 2;
    p4.packet_index = 2;
    pixels.push_back(p4);

    sortByTimestampAndOrder(pixels);

    test.expectEqual(pixels[0].timestamp_canonical, std::uint64_t{100},
                     "sorted by time first");
    test.expectEqual(pixels[0].packet_index, std::size_t{1},
                     "lowest timestamp first");

    test.expectEqual(pixels[1].timestamp_canonical, std::uint64_t{300},
                     "equal timestamps grouped");
    test.expectEqual(pixels[1].source_packet_order, std::uint64_t{2},
                     "equal time: lower order first");
    test.expectEqual(pixels[1].packet_index, std::size_t{2},
                     "packet index preserved");

    test.expectEqual(pixels[2].timestamp_canonical, std::uint64_t{300},
                     "equal timestamps grouped");
    test.expectEqual(pixels[2].source_packet_order, std::uint64_t{4},
                     "equal time: higher order second");
    test.expectEqual(pixels[2].packet_index, std::size_t{4},
                     "packet index preserved");

    test.expectEqual(pixels[3].timestamp_canonical, std::uint64_t{500},
                     "highest timestamp last");
}

void testCounterModuli(TestContext& test) {
    test.expectEqual(PIXEL_COUNTER_MODULUS, std::uint64_t{1ULL << 30U},
                     "pixel modulus 2^30");
    test.expectEqual(TDC_COUNTER_MODULUS, std::uint64_t{1ULL << 35U},
                     "TDC modulus 2^35");
    test.expectEqual(GLOBAL_COUNTER_MODULUS, std::uint64_t{1ULL << 48U},
                     "global modulus 2^48");
    test.expectEqual(CONTROL_COUNTER_MODULUS, std::uint64_t{1ULL << 34U},
                     "control modulus 2^34");
}

void testFindBestEpochNoAnchors(TestContext& test) {
    ChipAnchorIndex empty_index;
    EpochAssignmentDiagnostics diagnostics;

    const auto epoch = findBestEpoch(0x10000000, PIXEL_COUNTER_MODULUS,
                                     empty_index, 0, diagnostics);

    test.expectEqual(epoch, std::uint64_t{0}, "no anchors returns epoch 0");
    test.expect(diagnostics.used_fallback, "fallback flag set");
    test.expectEqual(diagnostics.unresolved_timestamps, std::uint64_t{1},
                     "unresolved count incremented");
}

void testFindBestEpochSingleAnchor(TestContext& test) {
    ChipAnchorIndex index;
    GlobalAnchor anchor;
    anchor.global_time_48bit = 0x100000000000;
    anchor.source_packet_order = 100;
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;

    const auto raw = 0x10000000;
    const auto epoch = findBestEpoch(raw, PIXEL_COUNTER_MODULUS,
                                     index, 50, diagnostics);

    test.expect(epoch >= 0, "returns valid epoch");
    test.expect(!diagnostics.used_fallback, "no fallback with anchors");
}

void testFindBestEpochMultipleEpochs(TestContext& test) {
    ChipAnchorIndex index;

    GlobalAnchor anchor;
    anchor.global_time_48bit = 0x100000000;
    anchor.source_packet_order = 500;
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;

    const auto raw_small = 0x01000000;
    const auto epoch_small = findBestEpoch(raw_small, PIXEL_COUNTER_MODULUS,
                                           index, 100, diagnostics);

    const auto raw_large = 0x3F000000;
    const auto epoch_large = findBestEpoch(raw_large, PIXEL_COUNTER_MODULUS,
                                           index, 200, diagnostics);

    test.expect(epoch_small >= 0 && epoch_large >= 0,
                "both epochs are valid");

    const auto unwrapped_small = raw_small + epoch_small * PIXEL_COUNTER_MODULUS;
    const auto unwrapped_large = raw_large + epoch_large * PIXEL_COUNTER_MODULUS;

    test.expect(unwrapped_small > 0 && unwrapped_large > 0,
                "unwrapped values are positive");
}

void testAssignEpochsToPixels(TestContext& test) {
    std::vector<PixelHit> pixels;

    PixelHit pixel1;
    pixel1.position.chip_index = 0;
    pixel1.coarse_time_25ns = 0x10000000;
    pixels.push_back(pixel1);

    PixelHit pixel2;
    pixel2.position.chip_index = 0;
    pixel2.coarse_time_25ns = 0x20000000;
    pixels.push_back(pixel2);

    PixelHit pixel3;
    pixel3.position.chip_index = 1;
    pixel3.coarse_time_25ns = 0x15000000;
    pixels.push_back(pixel3);

    ChipAnchorIndex index;
    GlobalAnchor anchor;
    anchor.global_time_48bit = 0x100000000;
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;
    assignEpochsToPixels(pixels, index, 0, diagnostics);

    test.expectEqual(diagnostics.pixels_assigned, std::uint64_t{2},
                     "assigned 2 pixels for chip 0");
    test.expect(pixels[0].coarse_time_25ns >= 0x10000000,
                "pixel 1 timestamp unwrapped");
    test.expect(pixels[1].coarse_time_25ns >= 0x20000000,
                "pixel 2 timestamp unwrapped");
    test.expectEqual(pixels[2].coarse_time_25ns, std::uint64_t{0x15000000},
                     "chip 1 pixel unchanged");
}

void testAssignEpochsToTdcs(TestContext& test) {
    std::vector<TdcHit> tdcs;

    TdcHit tdc1;
    tdc1.position.chip_index = 0;
    tdc1.tdc_timestamp_raw = 0x100000000;
    tdcs.push_back(tdc1);

    TdcHit tdc2;
    tdc2.position.chip_index = 0;
    tdc2.tdc_timestamp_raw = 0x200000000;
    tdcs.push_back(tdc2);

    ChipAnchorIndex index;
    GlobalAnchor anchor;
    anchor.global_time_48bit = 0x100000000;
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;
    assignEpochsToTdcs(tdcs, index, 0, diagnostics);

    test.expectEqual(diagnostics.tdcs_assigned, std::uint64_t{2},
                     "assigned 2 TDCs");
    test.expect(tdcs[0].tdc_timestamp_raw >= 0x100000000,
                "TDC 1 timestamp unwrapped");
    test.expect(tdcs[1].tdc_timestamp_raw >= 0x200000000,
                "TDC 2 timestamp unwrapped");
}

void testAssignEpochsToControls(TestContext& test) {
    std::vector<SpidrControl> controls;

    SpidrControl control1;
    control1.position.chip_index = 0;
    control1.type = SpidrControlType::shutter_open;
    control1.timestamp_raw = 0x100000000;
    controls.push_back(control1);

    SpidrControl control2;
    control2.position.chip_index = 0;
    control2.type = SpidrControlType::packet_count;
    control2.timestamp_raw = 0x200000000;
    controls.push_back(control2);

    ChipAnchorIndex index;
    GlobalAnchor anchor;
    anchor.global_time_48bit = 0x100000000;
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;
    assignEpochsToControls(controls, index, 0, diagnostics);

    test.expectEqual(diagnostics.controls_assigned, std::uint64_t{1},
                     "assigned 1 control (packet_count skipped)");
    test.expect(controls[0].timestamp_raw >= 0x100000000,
                "control 1 timestamp unwrapped");
    test.expectEqual(controls[1].timestamp_raw, std::uint64_t{0x200000000},
                     "packet_count control unchanged");
}

}  // namespace

int main() {
    TestContext test;
    testBuildChipAnchorIndexSingleChip(test);
    testBuildChipAnchorIndexMultipleChips(test);
    testBuildChipAnchorIndexNoAnchors(test);
    testBuildChipAnchorIndexSorting(test);
    testSortByTimestampAndOrder(test);
    testCounterModuli(test);
    testFindBestEpochNoAnchors(test);
    testFindBestEpochSingleAnchor(test);
    testFindBestEpochMultipleEpochs(test);
    testAssignEpochsToPixels(test);
    testAssignEpochsToTdcs(test);
    testAssignEpochsToControls(test);
    return test.finish();
}
