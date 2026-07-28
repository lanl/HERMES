#include "summary_writer.h"

#include <filesystem>
#include <fstream>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace hermes_photon_clusterer {

using json = nlohmann::ordered_json;

namespace {

json settingsJson(const SummaryClusteringSettings& s) {
    json j;
    j["max_time_spread_ticks"] = s.max_time_spread_ticks;
    j["min_cluster_size"] = s.min_cluster_size;
    j["max_cluster_size"] = s.max_cluster_size;
    j["min_pixel_tot_raw"] = s.min_pixel_tot_raw;
    j["min_cluster_tot_raw"] = s.min_cluster_tot_raw;
    j["max_cluster_tot_raw"] = s.max_cluster_tot_raw;
    j["max_aspect_ratio"] = s.max_aspect_ratio;
    j["min_filled_fraction"] = s.min_filled_fraction;
    j["adjacency"] = s.adjacency;
    j["position_averaging"] = s.position_averaging;
    j["photon_time_estimator"] = s.photon_time_estimator;
    if (s.timewalk_calibration_file.empty()) {
        j["timewalk_calibration_file"] = nullptr;
    } else {
        j["timewalk_calibration_file"] = s.timewalk_calibration_file;
    }
    j["save_photon_pixels"] = s.save_photon_pixels;
    return j;
}

json timingJson(const SummaryPhotonTiming& t) {
    json j;
    j["estimator"] = t.estimator;
    j["correction_model"] = t.correction_model;
    j["calibration_file"] =
        t.calibration_file.empty() ? json(nullptr) : json(t.calibration_file);
    json parameters = json::object();
    for (const auto& [key, value] : t.parameters) {
        parameters[key] = value;
    }
    j["parameters"] = parameters;
    j["high_tot_anchor"] =
        t.has_high_tot_anchor ? json(t.high_tot_anchor) : json(nullptr);
    return j;
}

}  // namespace

std::string generateReconstructionSummaryJson(
    const ReconstructionSummaryContent& content) {
    const double pixels_per_second =
        content.total_seconds > 0.0
            ? static_cast<double>(content.pixel_rows_read) /
                  content.total_seconds
            : 0.0;
    const double photons_per_second =
        content.total_seconds > 0.0
            ? static_cast<double>(content.photon_count) / content.total_seconds
            : 0.0;

    json j;
    j["schema_version"] = 1;

    j["reconstruction"] = {
        {"pixel_rows_read", content.pixel_rows_read},
        {"pixel_rows_below_min_tot", content.pixel_rows_below_min_tot},
        {"components_formed", content.components_formed},
        {"photon_count", content.photon_count},
        {"rejected_component_count", content.rejected_component_count},
        {"rejection_counts",
         {
             {"below_min_cluster_size",
              content.rejection_counts.below_min_cluster_size},
             {"above_max_cluster_size",
              content.rejection_counts.above_max_cluster_size},
             {"below_min_cluster_tot",
              content.rejection_counts.below_min_cluster_tot},
             {"above_max_cluster_tot",
              content.rejection_counts.above_max_cluster_tot},
             {"above_max_aspect_ratio",
              content.rejection_counts.above_max_aspect_ratio},
             {"below_min_filled_fraction",
              content.rejection_counts.below_min_filled_fraction},
         }},
        {"quality_flag_counts",
         {
             {"saturated_pixel", content.saturated_pixel_count},
             {"bridged_components", content.bridged_components_count},
         }},
        {"warnings", content.warnings},
        {"errors", content.errors},
    };

    j["clustering"] = {
        {"algorithm", content.algorithm},
        {"settings", settingsJson(content.settings)},
    };

    j["photon_timing"] = timingJson(content.photon_timing);

    j["parquet"] = {
        {"input_pixel_data_files", content.input_pixel_data_files},
        {"photon_events",
         {
             {"row_count", content.photon_events_row_count},
             {"files", content.photon_events_files},
         }},
        {"photon_pixels",
         {
             {"requested", content.photon_pixels_requested},
             {"row_count", content.photon_pixels_row_count},
             {"files", content.photon_pixels_files},
         }},
    };

    j["processing_times_seconds"] = {
        {"parquet_reading", content.parquet_reading_seconds},
        {"clustering_and_filtering", content.clustering_and_filtering_seconds},
        {"parquet_writing", content.parquet_writing_seconds},
        {"total", content.total_seconds},
        {"throughput",
         {
             {"pixels_per_second", pixels_per_second},
             {"photons_per_second", photons_per_second},
         }},
    };

    return j.dump(2);
}

void writeReconstructionSummaryJson(
    const std::string& output_path,
    const ReconstructionSummaryContent& content) {
    if (std::filesystem::exists(output_path)) {
        throw std::runtime_error(
            "Refusing to overwrite existing reconstruction summary file: " +
            output_path);
    }
    std::ofstream out(output_path);
    if (!out) {
        throw std::runtime_error(
            "Failed to open reconstruction summary file for writing: " +
            output_path);
    }
    out << generateReconstructionSummaryJson(content);
    if (!out) {
        throw std::runtime_error(
            "Failed to write reconstruction summary file: " + output_path);
    }
}

}  // namespace hermes_photon_clusterer
