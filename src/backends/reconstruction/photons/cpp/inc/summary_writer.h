#ifndef HERMES_PHOTON_CLUSTERER_SUMMARY_WRITER_H
#define HERMES_PHOTON_CLUSTERER_SUMMARY_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

#include "cluster_filter.h"
#include "settings.h"
#include "timewalk.h"

namespace hermes_photon_clusterer {

// All content needed to render one input file's reconstruction summary. It names
// the measurement and run it belongs to, the reconstruction counts, the exact
// clustering settings the run used, the photon-timing correction, the input and
// output Parquet paths, and the timing breakdown.
struct ReconstructionSummaryContent {
    // run identity, copied from the command line
    std::string measurement_id;
    std::string run;

    // reconstruction counts
    std::uint64_t pixels_read = 0;
    std::uint64_t clusters_formed = 0;
    std::uint64_t rejected_clusters = 0;
    RejectionCounts rejection_reasons;
    std::uint64_t saturated_pixel_count = 0;
    std::uint64_t bridged_components_count = 0;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;
    std::uint64_t total_photons = 0;

    // clustering algorithm and the complete settings the run used
    std::string clustering_algorithm;
    ClusteringSettings settings;

    // photon timing: the estimator, and the time-walk correction when one was
    // loaded. When has_correction is false the correction fields are ignored and
    // the correction model is reported as "none".
    std::string photon_time_estimator;
    bool has_correction = false;
    TimewalkCorrection correction;

    // input and output Parquet paths, exactly as passed to or written by the
    // binary so a reader can open them from the working directory. Output paths
    // are empty when no file was written.
    std::string input_pixel_data_file;
    std::string photons_file;
    std::uint64_t photons_row_count = 0;
    bool pixel_clusters_requested = false;
    std::string pixel_clusters_file;
    std::uint64_t pixel_clusters_row_count = 0;

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
