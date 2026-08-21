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
                                     CANONICAL_TICKS_PER_25NS, empty_index, 0, 0,
                                     diagnostics);

    test.expectEqual(epoch, std::uint64_t{0}, "no anchors returns epoch 0");
    test.expect(diagnostics.used_fallback, "fallback flag set");
    test.expectEqual(diagnostics.unresolved_timestamps, std::uint64_t{1},
                     "unresolved count incremented");
}

void testFindBestEpochPixelScale(TestContext& test) {
    // Pixel coarse time and the global anchor both count 25 ns units, so they
    // scale to canonical ticks by the same factor. An anchor three pixel
    // rollovers past zero must pull a raw pixel time of 0 up to epoch 3.
    ChipAnchorIndex index;
    GlobalAnchor anchor;
    anchor.global_time_48bit = 3ULL * PIXEL_COUNTER_MODULUS;
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;

    const auto epoch = findBestEpoch(0, PIXEL_COUNTER_MODULUS,
                                     CANONICAL_TICKS_PER_25NS, index, 0, 0,
                                     diagnostics);

    test.expectEqual(epoch, std::uint64_t{3},
                     "pixel raw 0 unwraps to the 3rd rollover");
    test.expect(!diagnostics.used_fallback, "no fallback with anchors");
}

void testFindBestEpochTdcScale(TestContext& test) {
    // TDC raw counts 3.125 ns units while the global anchor counts 25 ns units,
    // so one TDC rollover (2^35 raw) equals 2^32 global units. An anchor three
    // TDC rollovers past zero (global time 3 * 2^32) must pull a raw TDC time of
    // 0 up to epoch 3. With the wrong scale factor the search lands elsewhere,
    // so this pins the TDC-to-canonical conversion.
    ChipAnchorIndex index;
    GlobalAnchor anchor;
    anchor.global_time_48bit = 3ULL * (1ULL << 32U);
    index.anchors.push_back(anchor);

    EpochAssignmentDiagnostics diagnostics;

    const auto epoch = findBestEpoch(0, TDC_COUNTER_MODULUS,
                                     CANONICAL_TICKS_PER_TDC_RAW, index, 0, 0,
                                     diagnostics);

    test.expectEqual(epoch, std::uint64_t{3},
                     "TDC raw 0 unwraps to the 3rd TDC rollover");
    test.expect(!diagnostics.used_fallback, "no fallback with anchors");
}

void testFindBestEpochNearestAnchor(TestContext& test) {
    // Two heartbeats sit at different points in the stream: the first near zero,
    // the second three pixel rollovers later. A row positioned after the second
    // heartbeat must unwrap toward that second anchor (epoch 3), not the first
    // (epoch 0). This pins the nearest-anchor selection that keeps timestamps
    // growing across a counter wrap.
    ChipAnchorIndex index;

    GlobalAnchor first_anchor;
    first_anchor.global_time_48bit = 0;
    first_anchor.chunk_index = 0;
    first_anchor.packet_index = 10;
    index.anchors.push_back(first_anchor);

    GlobalAnchor second_anchor;
    second_anchor.global_time_48bit = 3ULL * PIXEL_COUNTER_MODULUS;
    second_anchor.chunk_index = 0;
    second_anchor.packet_index = 100;
    index.anchors.push_back(second_anchor);

    EpochAssignmentDiagnostics diagnostics;

    const auto before = findBestEpoch(0, PIXEL_COUNTER_MODULUS,
                                      CANONICAL_TICKS_PER_25NS, index, 0, 20,
                                      diagnostics);
    test.expectEqual(before, std::uint64_t{0},
                     "row before the second heartbeat unwraps to the first");

    const auto after = findBestEpoch(0, PIXEL_COUNTER_MODULUS,
                                     CANONICAL_TICKS_PER_25NS, index, 0, 200,
                                     diagnostics);
    test.expectEqual(after, std::uint64_t{3},
                     "row after the second heartbeat unwraps to the second");
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

void testAssignEpochsToPixelsUsesChipSpecificAnchors(TestContext& test) {
    std::vector<PixelHit> pixels;

    PixelHit chip1_pixel;
    chip1_pixel.position.chip_index = 1;
    chip1_pixel.coarse_time_25ns = 0;
    pixels.push_back(chip1_pixel);

    ChipAnchorIndex chip0_index;
    GlobalAnchor chip0_anchor;
    chip0_anchor.global_time_48bit = 0;
    chip0_index.anchors.push_back(chip0_anchor);

    ChipAnchorIndex chip1_index;
    GlobalAnchor chip1_anchor;
    chip1_anchor.global_time_48bit = PIXEL_COUNTER_MODULUS;
    chip1_index.anchors.push_back(chip1_anchor);

    EpochAssignmentDiagnostics diagnostics;
    assignEpochsToPixels(pixels, chip0_index, 0, diagnostics);
    test.expectEqual(pixels[0].coarse_time_25ns, std::uint64_t{0},
                     "chip 0 pass leaves chip 1 pixel unchanged");

    assignEpochsToPixels(pixels, chip1_index, 1, diagnostics);
    test.expectEqual(pixels[0].coarse_time_25ns, PIXEL_COUNTER_MODULUS,
                     "chip 1 pixel uses chip 1 anchor");
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
    test.expectEqual(tdcs[0].tdc_timestamp_raw, std::uint64_t{0x900000000},
                     "TDC 1 unwrapped to nearest rollover");
    test.expectEqual(tdcs[1].tdc_timestamp_raw, std::uint64_t{0xA00000000},
                     "TDC 2 unwrapped to nearest rollover");
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
    test.expectEqual(controls[0].timestamp_raw, std::uint64_t{0x100000000},
                     "control 1 already aligned with anchor (epoch 0)");
    test.expectEqual(controls[1].timestamp_raw, std::uint64_t{0x200000000},
                     "packet_count control unchanged");
}

void testMemoryEstimation(TestContext& test) {
    OutputRows rows;

    PixelOutputRow pixel;
    rows.pixels.push_back(pixel);
    rows.pixels.push_back(pixel);

    TdcOutputRow tdc;
    rows.tdcs.push_back(tdc);

    GlobalOutputRow global;
    rows.globals.push_back(global);

    const auto estimate = estimateMemoryUsage(rows);

    test.expectEqual(estimate.pixel_rows, std::uint64_t{2}, "2 pixel rows");
    test.expectEqual(estimate.tdc_rows, std::uint64_t{1}, "1 TDC row");
    test.expectEqual(estimate.global_rows, std::uint64_t{1}, "1 global row");
    test.expect(estimate.estimated_bytes > 0, "nonzero memory estimate");
}

void testSortingPathSelection(TestContext& test) {
    MemoryEstimate small_estimate;
    small_estimate.estimated_bytes = 1024;

    MemoryEstimate large_estimate;
    large_estimate.estimated_bytes = 2ULL * 1024ULL * 1024ULL * 1024ULL;

    const auto small_path = selectSortingPath(small_estimate, 1024ULL * 1024ULL);
    const auto large_path = selectSortingPath(large_estimate, 1024ULL * 1024ULL);

    test.expect(small_path == SortingPath::in_memory,
                "small estimate uses in-memory path");
    test.expect(large_path == SortingPath::external_merge,
                "large estimate uses external merge path");
}

void testSortAllOutputRows(TestContext& test) {
    OutputRows rows;

    rows.pixels = {
        PixelOutputRow{0, 2, 2, 0, 0, 0, 20},
        PixelOutputRow{0, 3, 3, 0, 0, 0, 10},
        PixelOutputRow{0, 1, 1, 0, 0, 0, 20},
    };
    rows.tdcs = {
        TdcOutputRow{0, 2, 2, 0, 20},
        TdcOutputRow{0, 1, 1, 0, 10},
    };
    rows.globals = {
        GlobalOutputRow{0, 2, 2, 20},
        GlobalOutputRow{0, 1, 1, 10},
    };
    rows.unknowns = {
        UnknownOutputRow{0, 2, 2, 0, 0},
        UnknownOutputRow{0, 1, 1, 0, 0},
    };

    ControlOutputRow untimestamped;
    untimestamped.chunk_index = 0;
    untimestamped.packet_index = 1;
    ControlOutputRow timestamped;
    timestamped.chunk_index = 0;
    timestamped.packet_index = 2;
    timestamped.timestamp_canonical = 10;
    timestamped.timestamp_canonical_present = true;
    rows.controls = {untimestamped, timestamped};

    SortingDiagnostics diagnostics;
    sortAllOutputRows(rows, diagnostics);

    test.expect(diagnostics.path_used == SortingPath::in_memory,
                "output rows use in-memory path");
    test.expectEqual(diagnostics.temporary_runs_created, std::uint64_t{0},
                     "no temporary runs for in-memory");
    test.expectEqual(rows.pixels[0].timestamp_canonical, std::uint64_t{10},
                     "pixels sorted by timestamp");
    test.expectEqual(rows.pixels[1].source_packet_order, std::uint64_t{1},
                     "equal timestamps sorted by source order");
    test.expectEqual(rows.tdcs[0].timestamp_canonical, std::uint64_t{10},
                     "TDC rows sorted by timestamp");
    test.expectEqual(rows.globals[0].timestamp_canonical, std::uint64_t{10},
                     "global rows sorted by timestamp");
    test.expect(rows.controls[0].timestamp_canonical_present,
                "timestamped controls sort before controls without time");
    test.expectEqual(rows.unknowns[0].packet_index, std::size_t{1},
                     "unknown rows remain in source order");
}

void testSortBySourcePacketOrder(TestContext& test) {
    std::vector<UnknownOutputRow> unknowns;

    UnknownOutputRow u1;
    u1.source_packet_order = 300;
    unknowns.push_back(u1);

    UnknownOutputRow u2;
    u2.source_packet_order = 100;
    unknowns.push_back(u2);

    UnknownOutputRow u3;
    u3.source_packet_order = 200;
    unknowns.push_back(u3);

    sortBySourcePacketOrder(unknowns);

    test.expectEqual(unknowns[0].source_packet_order, std::uint64_t{100},
                     "first by order");
    test.expectEqual(unknowns[1].source_packet_order, std::uint64_t{200},
                     "second by order");
    test.expectEqual(unknowns[2].source_packet_order, std::uint64_t{300},
                     "third by order");
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
    testFindBestEpochPixelScale(test);
    testFindBestEpochTdcScale(test);
    testFindBestEpochNearestAnchor(test);
    testAssignEpochsToPixels(test);
    testAssignEpochsToPixelsUsesChipSpecificAnchors(test);
    testAssignEpochsToTdcs(test);
    testAssignEpochsToControls(test);
    testMemoryEstimation(test);
    testSortingPathSelection(test);
    testSortAllOutputRows(test);
    testSortBySourcePacketOrder(test);
    return test.finish();
}
