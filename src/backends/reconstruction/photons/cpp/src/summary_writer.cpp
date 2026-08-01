#include "summary_writer.h"

#include <filesystem>
#include <fstream>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace hermes_photon_clusterer {

using json = nlohmann::ordered_json;

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
    const ReconstructionSummaryContent& content,
    bool overwrite) {
    if (!overwrite && std::filesystem::exists(output_path)) {
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
