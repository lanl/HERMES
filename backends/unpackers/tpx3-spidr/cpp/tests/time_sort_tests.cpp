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

}  // namespace

int main() {
    TestContext test;
    testBuildChipAnchorIndexSingleChip(test);
    testBuildChipAnchorIndexMultipleChips(test);
    testBuildChipAnchorIndexNoAnchors(test);
    testBuildChipAnchorIndexSorting(test);
    testSortByTimestampAndOrder(test);
    testCounterModuli(test);
    return test.finish();
}
