#ifndef HERMES_PHOTON_CLUSTERER_SENSOR_LAYOUT_H
#define HERMES_PHOTON_CLUSTERER_SENSOR_LAYOUT_H

#include <string>

namespace hermes_photon_clusterer {

// A point in the shared sensor coordinate frame.
struct SensorPoint {
    double x = 0.0;
    double y = 0.0;
};

// Maps one chip's local (x, y) into the shared sensor frame. "single_chip"
// leaves the 256x256 chip space unchanged. "quad" tiles the four chips 2x2 with
// a four-pixel dead gap into a 516x516 sensor, using the same per-chip
// offset/flip as the reference TPX3 decoder:
//   chip 0 -> (x + 260, y)
//   chip 1 -> (515 - x, 515 - y)
//   chip 2 -> (255 - x, 515 - y)
//   chip 3 -> (x, y)
// The map is affine, so transforming a cluster centroid equals transforming its
// source pixels and then averaging; clustering therefore stays chip-local.
// Throws std::runtime_error for an unknown layout or a quad chip index outside
// 0-3.
SensorPoint sensorTransform(const std::string& layout, int chip_index, double x,
                            double y);

}  // namespace hermes_photon_clusterer

#endif
