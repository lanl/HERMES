#ifndef HERMES_PHOTON_CLUSTERER_PHOTON_H
#define HERMES_PHOTON_CLUSTERER_PHOTON_H

#include <cstdint>

#include "cluster_filter.h"
#include "clustering.h"
#include "timewalk.h"

namespace hermes_photon_clusterer {

// One reconstructed photon, matching the photon_events schema. timestamp_canonical
// is float64 to carry the fractional time-walk-corrected leading edge; when no
// calibration is applied it equals the earliest source-pixel timestamp.
struct Photon {
    double x = 0.0;
    double y = 0.0;
    double timestamp_canonical = 0.0;
    std::uint64_t tot = 0;
    std::uint16_t quality_flags = 0;
};

// Builds a photon from an accepted cluster and its evaluation. Position is the
// arithmetic mean of the source-pixel coordinates and tot is the summed
// tot_raw. When correction is non-null, timestamp_canonical is the earliest
// time-walk-corrected source-pixel ToA; when null it is the earliest raw
// source-pixel timestamp (the uncorrected fallback).
Photon buildPhoton(const PixelCluster& cluster,
                   const ClusterEvaluation& evaluation,
                   const TimewalkCorrection* correction);

}  // namespace hermes_photon_clusterer

#endif
