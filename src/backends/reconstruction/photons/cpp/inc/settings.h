#ifndef HERMES_PHOTON_CLUSTERER_SETTINGS_H
#define HERMES_PHOTON_CLUSTERER_SETTINGS_H

#include <cstdint>
#include <string>

namespace hermes_photon_clusterer {

// Complete clustering settings with built-in defaults. Every field has a value,
// so the binary runs with no settings file; an optional JSON file overrides only
// the fields it names. Field names and bounds mirror Tpx3PhotonClusteringSettings.
struct ClusteringSettings {
    std::uint64_t max_time_spread_ticks = 491520;
    std::uint32_t min_cluster_size = 2;
    std::uint32_t max_cluster_size = 64;
    std::uint16_t min_pixel_tot_raw = 1;
    std::uint64_t min_cluster_tot_raw = 2;
    std::uint64_t max_cluster_tot_raw = 65472;
    double max_aspect_ratio = 3.0;
    double min_filled_fraction = 0.5;
    int adjacency = 8;
    std::string position_averaging = "arithmetic";
    std::string photon_time_estimator = "leading_edge";
    // Empty means no time-walk calibration file (uncorrected leading edge).
    std::string timewalk_calibration_file;
    bool save_photon_pixels = false;
    // How this chip's photon x/y map into the shared sensor coordinate frame:
    // "single_chip" leaves the 256x256 chip space unchanged; "quad" tiles the
    // four chips 2x2 with a four-pixel dead gap into a 516x516 sensor. Clustering
    // is unaffected; only the written photon coordinates move.
    std::string detector_layout = "single_chip";
};

// Loads settings starting from the defaults and overriding any field present in
// the JSON file at path. Unknown keys, wrong value types, out-of-range values,
// reserved estimators, or ordering violations throw std::runtime_error. An empty
// path is not accepted here; the caller decides whether to load a file at all.
ClusteringSettings loadClusteringSettings(const std::string& path);

// Validates a settings struct, throwing std::runtime_error on any violation.
// Applied by loadClusteringSettings and reusable for the built-in defaults.
void validateClusteringSettings(const ClusteringSettings& settings);

}  // namespace hermes_photon_clusterer

#endif
