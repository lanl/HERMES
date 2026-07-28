#ifndef HERMES_PHOTON_CLUSTERER_CLUSTERING_H
#define HERMES_PHOTON_CLUSTERER_CLUSTERING_H

#include <cstdint>
#include <functional>
#include <vector>

#include "pixel_reader.h"

namespace hermes_photon_clusterer {

// A closed cluster: the source pixels that were grouped together and whether it
// was formed by merging two previously separate open components (a diagnostic
// that a later step can use to flag ambiguous merges).
struct PixelCluster {
    std::vector<PixelHit> hits;
    bool bridged_components = false;
};

// Streaming connected-components clustering with an inclusive time gate.
//
// Pixels must arrive in non-decreasing timestamp_canonical order (the reader
// guarantees this per chip). A pixel joins an open cluster when it is spatially
// adjacent (4- or 8-connected per `adjacency`) to any pixel already in the
// cluster. Connectivity is transitive but never jumps across a missing pixel.
// A cluster closes once a newly read pixel's timestamp exceeds the cluster's
// earliest timestamp by more than max_time_spread_ticks. Closed clusters are
// delivered to on_cluster in time order; remaining open clusters are flushed at
// the end.
void clusterPixelHits(const std::function<bool(PixelHit&)>& next_hit,
                      int adjacency,
                      std::uint64_t max_time_spread_ticks,
                      const std::function<void(PixelCluster&&)>& on_cluster);

}  // namespace hermes_photon_clusterer

#endif
