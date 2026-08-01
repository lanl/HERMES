#ifndef HERMES_PHOTON_CLUSTERER_SUMMARY_WRITER_H
#define HERMES_PHOTON_CLUSTERER_SUMMARY_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

#include "cluster_filter.h"

namespace hermes_photon_clusterer {

// All content needed to render one input file's reconstruction summary. The
// summary is purely informational (counts and timing); settings provenance
// lives in the photon-file metadata, not here.
struct ReconstructionSummaryContent {
    // reconstruction counts
    std::uint64_t pixel_rows_read = 0;
    std::uint64_t pixel_rows_below_min_tot = 0;
    std::uint64_t components_formed = 0;
    std::uint64_t photon_count = 0;
    std::uint64_t rejected_component_count = 0;
    RejectionCounts rejection_counts;
    std::uint64_t saturated_pixel_count = 0;
    std::uint64_t bridged_components_count = 0;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;

    // processing times (seconds)
    double parquet_reading_seconds = 0.0;
    double clustering_and_filtering_seconds = 0.0;
    double parquet_writing_seconds = 0.0;
    double total_seconds = 0.0;
};

// Renders the summary as a pretty-printed JSON string matching
// Tpx3PhotonReconstructionSummary. Throughput is derived from the counts and
// total time (zero when total time is zero).
std::string generateReconstructionSummaryJson(
    const ReconstructionSummaryContent& content);

// Writes the summary JSON to output_path. When overwrite is false, refuses to
// replace an existing file; when true, replaces it. Throws std::runtime_error
// on a refused existing file or a write failure.
void writeReconstructionSummaryJson(
    const std::string& output_path,
    const ReconstructionSummaryContent& content,
    bool overwrite);

}  // namespace hermes_photon_clusterer

#endif
