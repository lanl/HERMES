#ifndef HERMES_EVENT_RECONSTRUCTOR_SUMMARY_WRITER_H
#define HERMES_EVENT_RECONSTRUCTOR_SUMMARY_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

namespace hermes_event_reconstructor {

// All content needed to render one input file's event-reconstruction summary.
// The summary is informational (counts, timing, and file lists); the clustering
// algorithm name and its settings are copied in for provenance, matching the
// event-file metadata.
//
// This module is algorithm-neutral: it does not know any algorithm's settings
// struct. Each clustering program serializes its own (possibly differently
// shaped) settings to a JSON object string and passes it in as
// clustering_settings_json; the writer renders that object verbatim under
// clustering.settings. That is what lets connected-components, DBSCAN, or any
// other algorithm share this writer despite different parameter fields.
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

    // clustering provenance: the algorithm name and its complete settings as a
    // JSON object string. The writer renders the parsed object verbatim under
    // clustering.settings, so any algorithm's fields (and any derived diagnostic
    // values it chooses to include) appear without this module knowing them.
    std::string clustering_algorithm;
    std::string clustering_settings_json;

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
