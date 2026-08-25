#include "sensor_layout.h"

#include <stdexcept>

namespace hermes_event_reconstructor {

int sensorWidth(const std::string& layout) {
    if (layout == "single_chip") {
        return 256;
    }
    if (layout == "quad") {
        return 516;
    }
    throw std::runtime_error("unknown detector layout '" + layout +
                             "': expected 'single_chip' or 'quad'");
}

}  // namespace hermes_event_reconstructor
