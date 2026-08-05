#include "settings.h"

#include <cmath>
#include <fstream>
#include <set>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace hermes_event_reconstructor {

namespace {

using json = nlohmann::json;

// Fixed chip width in pixels. The spatial grid spans one 256 x 256 chip.
constexpr int kChipWidthPixels = 256;

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

void validateReconParams(const ReconParams& s) {
    if (!(s.spatial_link_radius_pixels > 0.0) ||
        !std::isfinite(s.spatial_link_radius_pixels)) {
        throw std::runtime_error(
            "spatial_link_radius_pixels must be a finite value greater than 0");
    }
    if (s.spatial_cells_per_axis == 0) {
        throw std::runtime_error("spatial_cells_per_axis must be at least 1");
    }
    if (s.spatial_cells_per_axis > static_cast<std::uint32_t>(kChipWidthPixels)) {
        throw std::runtime_error(
            "spatial_cells_per_axis must be at most the 256-pixel field of view");
    }
    // A cell narrower than the linking radius would let the fixed 3x3 search
    // miss genuine neighbors and silently change the clustering result, so
    // reject grids too fine for the chosen radius.
    const int cell_width = deriveCellWidth(s.spatial_cells_per_axis);
    if (static_cast<double>(cell_width) < s.spatial_link_radius_pixels) {
        throw std::runtime_error(
            "spatial_cells_per_axis is too large for spatial_link_radius_pixels: "
            "the derived cell width would be smaller than the linking radius");
    }
    if (!(s.max_time_difference_ticks > 0.0) ||
        !std::isfinite(s.max_time_difference_ticks)) {
        throw std::runtime_error(
            "max_time_difference_ticks must be a finite value greater than 0");
    }
    if (!(s.max_event_duration_ticks > 0.0) ||
        !std::isfinite(s.max_event_duration_ticks)) {
        throw std::runtime_error(
            "max_event_duration_ticks must be a finite value greater than 0");
    }
    if (s.min_photon_count == 0) {
        throw std::runtime_error("min_photon_count must be at least 1");
    }
}

int deriveCellWidth(std::uint32_t spatial_cells_per_axis) {
    if (spatial_cells_per_axis == 0) {
        return kChipWidthPixels;
    }
    // Round up so exactly spatial_cells_per_axis cells span the 256-pixel field
    // of view; the last cell along each axis may be narrower than the rest.
    const int n = static_cast<int>(spatial_cells_per_axis);
    return (kChipWidthPixels + n - 1) / n;
}

ReconParams loadReconParams(const std::string& path) {
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
        "spatial_link_radius_pixels",
        "spatial_cells_per_axis",
        "max_time_difference_ticks",
        "max_event_duration_ticks",
        "min_photon_count",
        "save_event_photons",
    };
    for (const auto& item : document.items()) {
        if (known_keys.find(item.key()) == known_keys.end()) {
            throw std::runtime_error("unknown settings field '" + item.key() +
                                     "' in " + path);
        }
    }

    ReconParams settings;
    overrideDouble(document, "spatial_link_radius_pixels",
                   settings.spatial_link_radius_pixels);
    overrideUnsigned(document, "spatial_cells_per_axis",
                     settings.spatial_cells_per_axis);
    overrideDouble(document, "max_time_difference_ticks",
                   settings.max_time_difference_ticks);
    overrideDouble(document, "max_event_duration_ticks",
                   settings.max_event_duration_ticks);
    overrideUnsigned(document, "min_photon_count", settings.min_photon_count);
    overrideBool(document, "save_event_photons", settings.save_event_photons);

    validateReconParams(settings);
    return settings;
}

}  // namespace hermes_event_reconstructor
