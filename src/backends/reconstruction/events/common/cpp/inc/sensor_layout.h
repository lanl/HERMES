#ifndef HERMES_EVENT_RECONSTRUCTOR_SENSOR_LAYOUT_H
#define HERMES_EVENT_RECONSTRUCTOR_SENSOR_LAYOUT_H

#include <string>

namespace hermes_event_reconstructor {

// Returns the width in pixels of the shared sensor coordinate frame for a
// detector layout: 256 for "single_chip" (one 256x256 chip) and 516 for "quad"
// (a 2x2 tile of chips with a 4-pixel dead cross, so 0..515 on each axis).
// Throws std::runtime_error on any other layout. Photon reconstruction records
// the layout in each photon file's metadata; the event stage reads it back and
// sizes its clustering grid over this width.
int sensorWidth(const std::string& layout);

}  // namespace hermes_event_reconstructor

#endif
