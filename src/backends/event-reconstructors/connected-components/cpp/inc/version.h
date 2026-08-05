#ifndef HERMES_EVENT_RECONSTRUCTOR_VERSION_H
#define HERMES_EVENT_RECONSTRUCTOR_VERSION_H

namespace hermes_event_reconstructor {

// Program version reported by the executable. Bumped as the backend gains
// functionality across the reconstruction stages.
constexpr const char* kVersion = "0.1.0";

// Returns kVersion. Gives the static library a compiled symbol until later
// stages add real modules.
const char* libraryVersion();

}  // namespace hermes_event_reconstructor

#endif
