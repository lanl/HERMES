#include "version.h"

// The version constant lives in the header as a constexpr. This translation
// unit gives the static library a compiled object until later stages add real
// modules, keeping the build layout identical to the photon clusterer.
namespace hermes_event_reconstructor {

const char* libraryVersion() { return kVersion; }

}  // namespace hermes_event_reconstructor
