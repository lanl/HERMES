#ifndef HERMES_PHOTON_CLUSTERER_SUMMARY_WRITER_H
#define HERMES_PHOTON_CLUSTERER_SUMMARY_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

#include "cluster_filter.h"

namespace hermes_photon_clusterer {

// The complete clustering settings, mirrored into the summary's
// clustering.settings block. Field names match Tpx3PhotonClusteringSettings.
struct SummaryClusteringSettings {
    std::uint64_t max_time_spread_ticks = 0;
    std::uint32_t min_cluster_size = 0;
    std::uint32_t max_cluster_size = 0;
    std::uint16_t min_pixel_tot_raw = 0;
    std::uint64_t min_cluster_tot_raw = 0;
    std::uint64_t max_cluster_tot_raw = 0;
    double max_aspect_ratio = 0.0;
    double min_filled_fraction = 0.0;
    int adjacency = 8;
    std::string position_averaging = "arithmetic";
    std::string photon_time_estimator = "leading_edge";
    // Empty string means no calibration file was supplied.
    std::string timewalk_calibration_file;
    bool save_photon_pixels = false;
};

// Timing block. correction_model is "none", "inverse", or "linear". When "none",
// calibration_file is empty, parameters is empty, and high_tot_anchor is unset.
struct SummaryPhotonTiming {
    std::string estimator = "leading_edge";
    std::string correction_model = "none";
    std::string calibration_file;
    std::vector<std::pair<std::string, double>> parameters;
    bool has_high_tot_anchor = false;
    double high_tot_anchor = 0.0;
};

// All content needed to render one raw stem's reconstruction summary.
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

    // clustering
    std::string algorithm = "connected_components";
    SummaryClusteringSettings settings;

    // photon timing
    SummaryPhotonTiming photon_timing;

    // parquet (paths relative to the analysis directory)
    std::vector<std::string> input_pixel_data_files;
    std::uint64_t photon_events_row_count = 0;
    std::vector<std::string> photon_events_files;
    bool photon_pixels_requested = false;
    std::uint64_t photon_pixels_row_count = 0;
    std::vector<std::string> photon_pixels_files;

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

// Writes the summary JSON to output_path, refusing to overwrite an existing
// file. Throws std::runtime_error on an existing file or a write failure.
void writeReconstructionSummaryJson(
    const std::string& output_path,
    const ReconstructionSummaryContent& content);

}  // namespace hermes_photon_clusterer

#endif
