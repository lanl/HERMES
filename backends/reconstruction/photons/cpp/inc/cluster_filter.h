#ifndef HERMES_PHOTON_CLUSTERER_CLUSTER_FILTER_H
#define HERMES_PHOTON_CLUSTERER_CLUSTER_FILTER_H

#include <cstdint>

#include "clustering.h"

namespace hermes_photon_clusterer {

// Native 10-bit per-pixel ToT maximum; a pixel at this value is saturated.
constexpr std::uint16_t kSaturatedTot = 1023;

// Accepted-photon quality flag bits stored in photon_events.quality_flags.
enum QualityFlag : std::uint16_t {
    kQualitySaturatedPixel = 1U << 0U,
    kQualityBridgedComponents = 1U << 1U,
};

// Cluster-level rejection settings. Bounds are inclusive.
struct ClusterFilterSettings {
    std::uint32_t min_cluster_size = 0;
    std::uint32_t max_cluster_size = 0;
    std::uint64_t min_cluster_tot_raw = 0;
    std::uint64_t max_cluster_tot_raw = 0;
    double max_aspect_ratio = 0.0;
    double min_filled_fraction = 0.0;
};

// Per-reason rejection tallies. Reasons are non-exclusive: one rejected cluster
// may increment more than one counter. Field names match
// Tpx3PhotonRejectionCountsSummary.
struct RejectionCounts {
    std::uint64_t below_min_cluster_size = 0;
    std::uint64_t above_max_cluster_size = 0;
    std::uint64_t below_min_cluster_tot = 0;
    std::uint64_t above_max_cluster_tot = 0;
    std::uint64_t above_max_aspect_ratio = 0;
    std::uint64_t below_min_filled_fraction = 0;
};

// Computed measures and the accept/reject decision for one closed cluster.
struct ClusterEvaluation {
    bool accepted = false;
    std::uint32_t pixel_count = 0;
    std::uint64_t integrated_tot = 0;
    double aspect_ratio = 0.0;
    double filled_fraction = 0.0;
    std::uint16_t quality_flags = 0;
};

// Evaluates a cluster against the filter settings, incrementing every failing
// reason in counts (non-exclusive). When the cluster passes every filter the
// evaluation is accepted and quality_flags carries any set flags.
ClusterEvaluation evaluateCluster(const PixelCluster& cluster,
                                  const ClusterFilterSettings& settings,
                                  RejectionCounts& counts);

}  // namespace hermes_photon_clusterer

#endif
