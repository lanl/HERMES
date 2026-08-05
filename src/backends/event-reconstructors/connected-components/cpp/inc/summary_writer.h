#ifndef HERMES_EVENT_RECONSTRUCTOR_SUMMARY_WRITER_H
#define HERMES_EVENT_RECONSTRUCTOR_SUMMARY_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

#include "settings.h"

namespace hermes_event_reconstructor {

// All content needed to render one input file's event-reconstruction summary.
// The summary is informational (counts, timing, and file lists); the settings
// are copied in for provenance, matching the event-file metadata.
struct EventReconstructionSummaryContent {
    // reconstruction counts
    std::uint64_t photons_read = 0;
    std::uint64_t components_formed = 0;
    std::uint64_t event_count = 0;
    std::uint64_t single_photon_count = 0;      // events flagged single_photon
    std::uint64_t duration_exceeded_count = 0;  // events flagged duration_exceeded
    std::uint64_t min_photon_count_below = 0;   // events below min_photon_count
    std::vector<std::string> warnings;
    std::vector<std::string> errors;

    // clustering provenance: the settings used and the cell width derived from
    // spatial_cells_per_axis (recorded for diagnostics).
    ReconParams settings;
    int derived_cell_width = 0;

    // parquet file lists and row counts
    std::vector<std::string> input_photon_events_files;
    std::uint64_t event_candidates_row_count = 0;
    std::vector<std::string> event_candidates_files;
    // event_photons is present only when save_event_photons was set.
    std::uint64_t event_photons_row_count = 0;
    std::vector<std::string> event_photons_files;

    // processing times (seconds)
    double photon_reading_seconds = 0.0;
    double clustering_seconds = 0.0;
    double parquet_writing_seconds = 0.0;
    double total_seconds = 0.0;
};

// Renders the summary as a pretty-printed JSON string matching the structure in
// docs/architecture/event_reconstruction.md. Throughput is derived from the
// counts and total time (zero when total time is zero).
std::string generateEventReconstructionSummaryJson(
    const EventReconstructionSummaryContent& content);

// Writes the summary JSON to output_path. When overwrite is false, refuses to
// replace an existing file; when true, replaces it. Throws std::runtime_error on
// a refused existing file or a write failure.
void writeEventReconstructionSummaryJson(
    const std::string& output_path,
    const EventReconstructionSummaryContent& content,
    bool overwrite);

}  // namespace hermes_event_reconstructor

#endif
