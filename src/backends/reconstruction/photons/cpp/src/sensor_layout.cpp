#include "sensor_layout.h"

#include <stdexcept>
#include <string>

namespace hermes_photon_clusterer {

SensorPoint sensorTransform(const std::string& layout, int chip_index, double x,
                            double y) {
    if (layout == "single_chip") {
        return {x, y};
    }
    if (layout == "quad") {
        switch (chip_index) {
            case 0:
                return {x + 260.0, y};
            case 1:
                return {515.0 - x, 515.0 - y};
            case 2:
                return {255.0 - x, 515.0 - y};
            case 3:
                return {x, y};
            default:
                throw std::runtime_error(
                    "quad detector_layout has no chip index " +
                    std::to_string(chip_index) + "; expected 0-3");
        }
    }
    throw std::runtime_error("unknown detector_layout: " + layout);
}

}  // namespace hermes_photon_clusterer
