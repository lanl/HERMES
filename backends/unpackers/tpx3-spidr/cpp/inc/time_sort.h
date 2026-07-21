#ifndef HERMES_TPX3_SPIDR_TIME_SORT_H
#define HERMES_TPX3_SPIDR_TIME_SORT_H

#include "output_rows.h"
#include "packet_types.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace hermes_tpx3_spidr {

constexpr std::uint64_t PIXEL_COUNTER_MODULUS = 1ULL << 30U;
constexpr std::uint64_t TDC_COUNTER_MODULUS = 1ULL << 35U;
constexpr std::uint64_t GLOBAL_COUNTER_MODULUS = 1ULL << 48U;
constexpr std::uint64_t CONTROL_COUNTER_MODULUS = 1ULL << 34U;

struct GlobalAnchor {
    std::uint64_t global_time_48bit = 0;
    std::uint64_t source_packet_order = 0;
    std::size_t chunk_index = 0;
    std::size_t packet_index = 0;
};

struct ChipAnchorIndex {
    std::vector<GlobalAnchor> anchors;
};

struct AnchorIndexDiagnostics {
    std::uint64_t total_anchors = 0;
    std::uint64_t unpaired_low_count = 0;
    std::uint64_t unpaired_high_count = 0;
    std::vector<std::string> warnings;
};

struct EpochAssignmentDiagnostics {
    std::uint64_t pixels_assigned = 0;
    std::uint64_t tdcs_assigned = 0;
    std::uint64_t controls_assigned = 0;
    std::uint64_t ambiguous_timestamps = 0;
    std::uint64_t unresolved_timestamps = 0;
    bool used_fallback = false;
    std::vector<std::string> warnings;
};

ChipAnchorIndex buildChipAnchorIndex(
    const std::vector<GlobalTimestamp>& global_timestamps,
    std::uint8_t chip_index,
    AnchorIndexDiagnostics& diagnostics);

void assignSourcePacketOrder(UnpackResult& result);

std::uint64_t findBestEpoch(std::uint64_t raw_counter,
                            std::uint64_t modulus,
                            const ChipAnchorIndex& anchors,
                            std::uint64_t source_packet_order,
                            EpochAssignmentDiagnostics& diagnostics);

void assignEpochsToPixels(std::vector<PixelHit>& pixels,
                          const ChipAnchorIndex& anchors,
                          std::uint8_t chip_index,
                          EpochAssignmentDiagnostics& diagnostics);

void assignEpochsToTdcs(std::vector<TdcHit>& tdcs,
                        const ChipAnchorIndex& anchors,
                        std::uint8_t chip_index,
                        EpochAssignmentDiagnostics& diagnostics);

void assignEpochsToControls(std::vector<SpidrControl>& controls,
                            const ChipAnchorIndex& anchors,
                            std::uint8_t chip_index,
                            EpochAssignmentDiagnostics& diagnostics);

template <typename Row>
void sortByTimestampAndOrder(std::vector<Row>& rows) {
    std::stable_sort(rows.begin(), rows.end(),
                     [](const Row& a, const Row& b) {
                         if (a.timestamp_canonical != b.timestamp_canonical) {
                             return a.timestamp_canonical < b.timestamp_canonical;
                         }
                         return a.source_packet_order < b.source_packet_order;
                     });
}

}  // namespace hermes_tpx3_spidr

#endif
