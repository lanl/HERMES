#include "time_sort.h"

#include <algorithm>

namespace hermes_tpx3_spidr {

ChipAnchorIndex buildChipAnchorIndex(
    const std::vector<GlobalTimestamp>& global_timestamps,
    const std::uint8_t chip_index,
    AnchorIndexDiagnostics& diagnostics) {
    ChipAnchorIndex index;

    for (const auto& global : global_timestamps) {
        if (global.high_packet.chip_index == chip_index) {
            GlobalAnchor anchor;
            anchor.global_time_48bit = global.global_time_raw;
            anchor.source_packet_order = 0;
            anchor.chunk_index = global.high_packet.chunk_index;
            anchor.packet_index = global.high_packet.packet_index;
            index.anchors.push_back(anchor);
            ++diagnostics.total_anchors;
        }
    }

    std::stable_sort(index.anchors.begin(), index.anchors.end(),
                     [](const GlobalAnchor& a, const GlobalAnchor& b) {
                         if (a.chunk_index != b.chunk_index) {
                             return a.chunk_index < b.chunk_index;
                         }
                         return a.packet_index < b.packet_index;
                     });

    return index;
}

void assignSourcePacketOrder(UnpackResult& result) {
    (void)result;
}

}  // namespace hermes_tpx3_spidr
