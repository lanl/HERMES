#include "summary_writer.h"

#include <filesystem>
#include <fstream>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace hermes_photon_clusterer {

using json = nlohmann::ordered_json;

namespace {

// The complete clustering settings, in the same key order the photon-file
// metadata uses. The calibration path is null when no file was configured.
json settingsJson(const ClusteringSettings& s) {
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
    j["timewalk_calibration_file"] =
        s.timewalk_calibration_file.empty()
            ? json(nullptr)
            : json(s.timewalk_calibration_file);
    j["save_photon_pixels"] = s.save_photon_pixels;
    return j;
}

// The photon_timing block: the estimator, the correction model name, the
// calibration path, the fitted parameters, and the high-ToT anchor. When no
// correction was loaded the model is "none" with empty parameters and null
// calibration path and anchor.
json photonTimingJson(const ReconstructionSummaryContent& content) {
    json timing;
    timing["estimator"] = content.photon_time_estimator;
    if (!content.has_correction) {
        timing["correction_model"] = "none";
        timing["calibration_file"] = nullptr;
        timing["parameters"] = json::object();
        timing["high_tot_anchor"] = nullptr;
        return timing;
    }

    const bool inverse =
        content.correction.model == TimewalkCorrection::Model::kInverse;
    timing["correction_model"] = inverse ? "inverse" : "linear";
    timing["calibration_file"] =
        content.settings.timewalk_calibration_file.empty()
            ? json(nullptr)
            : json(content.settings.timewalk_calibration_file);
    json parameters;
    if (inverse) {
        parameters["a"] = content.correction.a;
        parameters["b"] = content.correction.b;
    } else {
        parameters["m"] = content.correction.m;
    }
    timing["parameters"] = parameters;
    timing["high_tot_anchor"] = content.correction.high_tot_anchor;
    return timing;
}

json fileListJson(const std::string& file) {
    json files = json::array();
    if (!file.empty()) {
        files.push_back(file);
    }
    return files;
}

}  // namespace

std::string generateReconstructionSummaryJson(
    const ReconstructionSummaryContent& content) {
    const double pixels_per_second =
        content.total_seconds > 0.0
            ? static_cast<double>(content.pixels_read) / content.total_seconds
            : 0.0;
    const double photons_per_second =
        content.total_seconds > 0.0
            ? static_cast<double>(content.total_photons) / content.total_seconds
            : 0.0;

    json j;

    j["measurement_info"] = {
        {"measurement_id", content.measurement_id},
        {"run", content.run},
    };

    j["reconstruction"] = {
        {"pixels_read", content.pixels_read},
        {"clusters_formed", content.clusters_formed},
        {"rejected_clusters", content.rejected_clusters},
        {"rejection_reasons",
         {
             {"below_min_cluster_size",
              content.rejection_reasons.below_min_cluster_size},
             {"above_max_cluster_size",
              content.rejection_reasons.above_max_cluster_size},
             {"below_min_cluster_tot",
              content.rejection_reasons.below_min_cluster_tot},
             {"above_max_cluster_tot",
              content.rejection_reasons.above_max_cluster_tot},
             {"above_max_aspect_ratio",
              content.rejection_reasons.above_max_aspect_ratio},
             {"below_min_filled_fraction",
              content.rejection_reasons.below_min_filled_fraction},
         }},
        {"quality_flag_counts",
         {
             {"saturated_pixel", content.saturated_pixel_count},
             {"bridged_components", content.bridged_components_count},
         }},
        {"warnings", content.warnings},
        {"errors", content.errors},
        {"total_photons", content.total_photons},
    };

    j["clustering"] = {
        {"algorithm", content.clustering_algorithm},
        {"settings", settingsJson(content.settings)},
    };

    j["photon_timing"] = photonTimingJson(content);

    j["parquet_files"] = {
        {"input_pixel_data_file", fileListJson(content.input_pixel_data_file)},
        {"photons",
         {
             {"row_count", content.photons_row_count},
             {"files", fileListJson(content.photons_file)},
         }},
        {"pixel_clusters",
         {
             {"requested", content.pixel_clusters_requested},
             {"row_count", content.pixel_clusters_row_count},
             {"files", fileListJson(content.pixel_clusters_file)},
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
