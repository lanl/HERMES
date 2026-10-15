#ifndef HERMES_PHOTON_CLUSTERER_PHOTON_H
#define HERMES_PHOTON_CLUSTERER_PHOTON_H

#include <cstdint>
#include <string>

#include "cluster_filter.h"
#include "clustering.h"
#include "timewalk.h"

namespace hermes_photon_clusterer {

// One reconstructed photon, matching the photon_events schema. timestamp_canonical
// is float64 to carry fractional averages and time-walk corrections.
struct Photon {
    double x = 0.0;
    double y = 0.0;
    double timestamp_canonical = 0.0;
    std::uint64_t tot = 0;
    std::uint16_t quality_flags = 0;
};

// Builds a photon from an accepted cluster and its evaluation. Position is the
// arithmetic mean of the source-pixel coordinates and tot is the summed
// tot_raw. The estimator uses source-hit times after optional global correction.
Photon buildPhoton(const PixelCluster& cluster,
                   const ClusterEvaluation& evaluation,
                   const TimewalkCorrection* correction,
                   const std::string& estimator = "average");

}  // namespace hermes_photon_clusterer

#endif
