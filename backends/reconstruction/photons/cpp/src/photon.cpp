#include "photon.h"

#include <cstdint>

namespace hermes_photon_clusterer {

Photon buildPhoton(const PixelCluster& cluster,
                   const ClusterEvaluation& evaluation,
                   const TimewalkCorrection* correction) {
    Photon photon;
    photon.quality_flags = evaluation.quality_flags;
    photon.tot = evaluation.integrated_tot;

    if (cluster.hits.empty()) {
        return photon;
    }

    std::uint64_t sum_x = 0;
    std::uint64_t sum_y = 0;
    std::uint64_t earliest_raw = cluster.hits.front().timestamp_canonical;
    for (const auto& hit : cluster.hits) {
        sum_x += hit.x;
        sum_y += hit.y;
        if (hit.timestamp_canonical < earliest_raw) {
            earliest_raw = hit.timestamp_canonical;
        }
    }

    const double count = static_cast<double>(cluster.hits.size());
    photon.x = static_cast<double>(sum_x) / count;
    photon.y = static_cast<double>(sum_y) / count;

    // Time-walk correction can reorder pixels in time, so the earliest corrected
    // ToA is not necessarily the raw-earliest pixel's corrected time; scan all
    // pixels. Without a calibration, fall back to the earliest raw timestamp.
    photon.timestamp_canonical =
        correction != nullptr
            ? earliestCorrectedToa(cluster, *correction)
            : static_cast<double>(earliest_raw);
    return photon;
}

}  // namespace hermes_photon_clusterer
