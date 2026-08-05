#include "summary_writer.h"

#include <filesystem>
#include <fstream>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace hermes_event_reconstructor {

using json = nlohmann::ordered_json;

std::string generateEventReconstructionSummaryJson(
    const EventReconstructionSummaryContent& content) {
    const double photons_per_second =
        content.total_seconds > 0.0
            ? static_cast<double>(content.photons_read) / content.total_seconds
            : 0.0;
    const double events_per_second =
        content.total_seconds > 0.0
            ? static_cast<double>(content.event_count) / content.total_seconds
            : 0.0;

    json j;
    j["schema_version"] = 1;

    j["reconstruction"] = {
        {"photons_read", content.photons_read},
        {"components_formed", content.components_formed},
        {"event_count", content.event_count},
        {"quality_flag_counts",
         {
             {"single_photon", content.single_photon_count},
             {"duration_exceeded", content.duration_exceeded_count},
         }},
        {"min_photon_count_below", content.min_photon_count_below},
        {"warnings", content.warnings},
        {"errors", content.errors},
    };

    // The settings object is produced by the clustering program (which owns its
    // own settings struct) and rendered verbatim, so this module stays neutral
    // about any algorithm's parameter fields. An empty string is treated as an
    // empty object.
    json settings = content.clustering_settings_json.empty()
                        ? json::object()
                        : json::parse(content.clustering_settings_json);
    j["clustering"] = {
        {"algorithm", content.clustering_algorithm},
        {"settings", settings},
    };

    j["event_timing"] = {
        {"estimator", "earliest_photon"},
    };

    json parquet = {
        {"input_photon_events_files", content.input_photon_events_files},
        {"event_candidates",
         {
             {"row_count", content.event_candidates_row_count},
             {"files", content.event_candidates_files},
         }},
    };
    // event_photons is reported only when that output was written.
    if (!content.event_photons_files.empty()) {
        parquet["event_photons"] = {
            {"row_count", content.event_photons_row_count},
            {"files", content.event_photons_files},
        };
    }
    j["parquet"] = parquet;

    j["processing_times_seconds"] = {
        {"photon_reading", content.photon_reading_seconds},
        {"clustering", content.clustering_seconds},
        {"parquet_writing", content.parquet_writing_seconds},
        {"total", content.total_seconds},
        {"throughput",
         {
             {"photons_per_second", photons_per_second},
             {"events_per_second", events_per_second},
         }},
    };

    return j.dump(2);
}

void writeEventReconstructionSummaryJson(
    const std::string& output_path,
    const EventReconstructionSummaryContent& content,
    bool overwrite) {
    if (!overwrite && std::filesystem::exists(output_path)) {
        throw std::runtime_error(
            "Refusing to overwrite existing event-reconstruction summary file: " +
            output_path);
    }
    std::ofstream out(output_path);
    if (!out) {
        throw std::runtime_error(
            "Failed to open event-reconstruction summary file for writing: " +
            output_path);
    }
    out << generateEventReconstructionSummaryJson(content);
    if (!out) {
        throw std::runtime_error(
            "Failed to write event-reconstruction summary file: " + output_path);
    }
}

}  // namespace hermes_event_reconstructor
