#include "settings.h"

#include <fstream>
#include <set>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace hermes_photon_clusterer {

namespace {

using json = nlohmann::json;

// Reads an unsigned integer field, rejecting non-integers and negative values.
template <typename T>
void overrideUnsigned(const json& document, const char* key, T& target) {
    if (!document.contains(key)) {
        return;
    }
    const auto& value = document.at(key);
    if (!value.is_number_unsigned() &&
        !(value.is_number_integer() && value.get<long long>() >= 0)) {
        throw std::runtime_error(std::string("settings field '") + key +
                                 "' must be a non-negative integer");
    }
    target = value.get<T>();
}

void overrideDouble(const json& document, const char* key, double& target) {
    if (!document.contains(key)) {
        return;
    }
    const auto& value = document.at(key);
    if (!value.is_number()) {
        throw std::runtime_error(std::string("settings field '") + key +
                                 "' must be a number");
    }
    target = value.get<double>();
}

void overrideString(const json& document, const char* key, std::string& target) {
    if (!document.contains(key)) {
        return;
    }
    const auto& value = document.at(key);
    if (value.is_null()) {
        target.clear();
        return;
    }
    if (!value.is_string()) {
        throw std::runtime_error(std::string("settings field '") + key +
                                 "' must be a string");
    }
    target = value.get<std::string>();
}

void overrideBool(const json& document, const char* key, bool& target) {
    if (!document.contains(key)) {
        return;
    }
    const auto& value = document.at(key);
    if (!value.is_boolean()) {
        throw std::runtime_error(std::string("settings field '") + key +
                                 "' must be a boolean");
    }
    target = value.get<bool>();
}

}  // namespace

void validateClusteringSettings(const ClusteringSettings& s) {
    if (s.max_time_spread_ticks == 0) {
        throw std::runtime_error("max_time_spread_ticks must be greater than 0");
    }
    if (s.min_cluster_size == 0 || s.max_cluster_size == 0) {
        throw std::runtime_error("cluster size bounds must be greater than 0");
    }
    if (s.min_cluster_size > s.max_cluster_size) {
        throw std::runtime_error(
            "min_cluster_size must be less than or equal to max_cluster_size");
    }
    if (s.min_pixel_tot_raw > 1023) {
        throw std::runtime_error("min_pixel_tot_raw must be between 0 and 1023");
    }
    if (s.min_cluster_tot_raw > s.max_cluster_tot_raw) {
        throw std::runtime_error(
            "min_cluster_tot_raw must be less than or equal to "
            "max_cluster_tot_raw");
    }
    if (s.max_aspect_ratio < 1.0) {
        throw std::runtime_error("max_aspect_ratio must be at least 1");
    }
    if (s.min_filled_fraction <= 0.0 || s.min_filled_fraction > 1.0) {
        throw std::runtime_error(
            "min_filled_fraction must be greater than 0 and at most 1");
    }
    if (s.adjacency != 4 && s.adjacency != 8) {
        throw std::runtime_error("adjacency must be 4 or 8");
    }
    if (s.position_averaging != "arithmetic") {
        throw std::runtime_error(
            "position_averaging='" + s.position_averaging +
            "' is reserved and not implemented");
    }
    if (s.photon_time_estimator != "leading_edge") {
        throw std::runtime_error(
            "photon_time_estimator='" + s.photon_time_estimator +
            "' is reserved and not implemented");
    }
}

ClusteringSettings loadClusteringSettings(const std::string& path) {
    std::ifstream input(path);
    if (!input.is_open()) {
        throw std::runtime_error("cannot open settings file: " + path);
    }

    json document;
    try {
        input >> document;
    } catch (const json::exception& error) {
        throw std::runtime_error("malformed settings JSON in " + path + ": " +
                                 error.what());
    }
    if (!document.is_object()) {
        throw std::runtime_error("settings file must be a JSON object: " + path);
    }

    // Reject unknown keys so a typo cannot silently keep a default.
    static const std::set<std::string> known_keys = {
        "max_time_spread_ticks", "min_cluster_size",
        "max_cluster_size",      "min_pixel_tot_raw",
        "min_cluster_tot_raw",   "max_cluster_tot_raw",
        "max_aspect_ratio",      "min_filled_fraction",
        "adjacency",             "position_averaging",
        "photon_time_estimator", "timewalk_calibration_file",
        "save_photon_pixels",
    };
    for (const auto& item : document.items()) {
        if (known_keys.find(item.key()) == known_keys.end()) {
            throw std::runtime_error("unknown settings field '" + item.key() +
                                     "' in " + path);
        }
    }

    ClusteringSettings settings;
    overrideUnsigned(document, "max_time_spread_ticks",
                     settings.max_time_spread_ticks);
    overrideUnsigned(document, "min_cluster_size", settings.min_cluster_size);
    overrideUnsigned(document, "max_cluster_size", settings.max_cluster_size);
    overrideUnsigned(document, "min_pixel_tot_raw", settings.min_pixel_tot_raw);
    overrideUnsigned(document, "min_cluster_tot_raw",
                     settings.min_cluster_tot_raw);
    overrideUnsigned(document, "max_cluster_tot_raw",
                     settings.max_cluster_tot_raw);
    overrideDouble(document, "max_aspect_ratio", settings.max_aspect_ratio);
    overrideDouble(document, "min_filled_fraction", settings.min_filled_fraction);
    overrideUnsigned(document, "adjacency", settings.adjacency);
    overrideString(document, "position_averaging", settings.position_averaging);
    overrideString(document, "photon_time_estimator",
                   settings.photon_time_estimator);
    overrideString(document, "timewalk_calibration_file",
                   settings.timewalk_calibration_file);
    overrideBool(document, "save_photon_pixels", settings.save_photon_pixels);

    validateClusteringSettings(settings);
    return settings;
}

}  // namespace hermes_photon_clusterer
