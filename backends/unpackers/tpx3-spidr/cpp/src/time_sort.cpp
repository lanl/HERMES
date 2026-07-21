#include "time_sort.h"
#include "timestamp_calculator.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <vector>

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

std::uint64_t findBestEpoch(const std::uint64_t raw_counter,
                            const std::uint64_t modulus,
                            const ChipAnchorIndex& anchors,
                            const std::uint64_t source_packet_order,
                            EpochAssignmentDiagnostics& diagnostics) {
    if (anchors.anchors.empty()) {
        diagnostics.used_fallback = true;
        ++diagnostics.unresolved_timestamps;
        return 0;
    }

    const auto& anchor = anchors.anchors[0];
    const auto anchor_canonical = anchor.global_time_48bit * 12288U;

    std::uint64_t best_epoch = 0;
    std::uint64_t min_distance = std::numeric_limits<std::uint64_t>::max();

    for (std::uint64_t epoch = 0; epoch < 100; ++epoch) {
        const auto candidate_raw = raw_counter + epoch * modulus;
        const auto candidate_canonical = candidate_raw * 768U;

        std::uint64_t distance;
        if (candidate_canonical > anchor_canonical) {
            distance = candidate_canonical - anchor_canonical;
        } else {
            distance = anchor_canonical - candidate_canonical;
        }

        if (distance < min_distance) {
            min_distance = distance;
            best_epoch = epoch;
        }
    }

    (void)source_packet_order;
    return best_epoch;
}

void assignEpochsToPixels(std::vector<PixelHit>& pixels,
                          const ChipAnchorIndex& anchors,
                          const std::uint8_t chip_index,
                          EpochAssignmentDiagnostics& diagnostics) {
    for (auto& pixel : pixels) {
        if (pixel.position.chip_index != chip_index) {
            continue;
        }

        const auto epoch = findBestEpoch(
            pixel.coarse_time_25ns, PIXEL_COUNTER_MODULUS, anchors,
            0, diagnostics);

        const auto unwrapped_coarse =
            pixel.coarse_time_25ns + epoch * PIXEL_COUNTER_MODULUS;
        pixel.coarse_time_25ns = unwrapped_coarse;
        ++diagnostics.pixels_assigned;
    }
}

void assignEpochsToTdcs(std::vector<TdcHit>& tdcs,
                        const ChipAnchorIndex& anchors,
                        const std::uint8_t chip_index,
                        EpochAssignmentDiagnostics& diagnostics) {
    for (auto& tdc : tdcs) {
        if (tdc.position.chip_index != chip_index) {
            continue;
        }

        const auto epoch = findBestEpoch(
            tdc.tdc_timestamp_raw, TDC_COUNTER_MODULUS, anchors,
            0, diagnostics);

        const auto unwrapped_timestamp =
            tdc.tdc_timestamp_raw + epoch * TDC_COUNTER_MODULUS;
        tdc.tdc_timestamp_raw = unwrapped_timestamp;
        ++diagnostics.tdcs_assigned;
    }
}

void assignEpochsToControls(std::vector<SpidrControl>& controls,
                            const ChipAnchorIndex& anchors,
                            const std::uint8_t chip_index,
                            EpochAssignmentDiagnostics& diagnostics) {
    for (auto& control : controls) {
        if (control.position.chip_index != chip_index) {
            continue;
        }

        if (control.type == SpidrControlType::packet_count) {
            continue;
        }

        const auto epoch = findBestEpoch(
            control.timestamp_raw, CONTROL_COUNTER_MODULUS, anchors,
            0, diagnostics);

        const auto unwrapped_timestamp =
            control.timestamp_raw + epoch * CONTROL_COUNTER_MODULUS;
        control.timestamp_raw = unwrapped_timestamp;
        ++diagnostics.controls_assigned;
    }
}

}  // namespace hermes_tpx3_spidr
