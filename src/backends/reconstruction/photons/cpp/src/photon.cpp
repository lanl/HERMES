#include "photon.h"

#include <cmath>
#include <cstdint>
#include <stdexcept>

#include "timestamp.h"

namespace hermes_photon_clusterer {

Photon buildPhoton(const PixelCluster& cluster,
                   const ClusterEvaluation& evaluation,
                   const TimewalkCorrection* correction,
                   const std::string& estimator) {
    if (estimator != "average" && estimator != "leading_edge" &&
        estimator != "brightest") {
        throw std::runtime_error("unsupported photon_time_estimator: " + estimator);
    }
    Photon photon;
    photon.quality_flags = evaluation.quality_flags;
    photon.tot = evaluation.integrated_tot;

    if (cluster.hits.empty()) {
        return photon;
    }

    std::uint64_t sum_x = 0;
    std::uint64_t sum_y = 0;
    std::uint64_t earliest_raw = cluster.hits.front().timestamp_canonical;
    const PixelHit* brightest = &cluster.hits.front();
    for (const auto& hit : cluster.hits) {
        sum_x += hit.x;
        sum_y += hit.y;
        if (hit.timestamp_canonical < earliest_raw) {
            earliest_raw = hit.timestamp_canonical;
        }
        if (hit.tot_raw > brightest->tot_raw ||
            (hit.tot_raw == brightest->tot_raw &&
             hit.timestamp_canonical < brightest->timestamp_canonical)) {
            brightest = &hit;
        }
    }

    const double count = static_cast<double>(cluster.hits.size());
    photon.x = static_cast<double>(sum_x) / count;
    photon.y = static_cast<double>(sum_y) / count;

    if (estimator == "leading_edge") {
        photon.timestamp_canonical = correction != nullptr
            ? earliestCorrectedToa(cluster, *correction)
            : static_cast<double>(earliest_raw);
    } else if (estimator == "brightest") {
        photon.timestamp_canonical = correction != nullptr
            ? correctedToa(brightest->timestamp_canonical, brightest->tot_raw,
                           *correction)
            : static_cast<double>(brightest->timestamp_canonical);
    } else {
        // Subtract integer timestamps before converting, preserving small
        // differences even when the absolute timestamp exceeds 2^53.
        long double sum_offsets = 0.0L;
        for (const auto& hit : cluster.hits) {
            sum_offsets += static_cast<long double>(
                hit.timestamp_canonical - earliest_raw);
            if (correction != nullptr) {
                sum_offsets -= timewalkDelay(hit.tot_raw, *correction);
            }
        }
        long double mean_offset =
            sum_offsets / static_cast<long double>(cluster.hits.size());
        if (!std::isfinite(mean_offset)) {
            // Individual finite corrections can overflow their sum when long
            // double has float64 range. Scale before summing in that case;
            // each scaled value is in [-1,1], so its mean cannot overflow.
            const auto offset = [&](const PixelHit& hit) {
                return static_cast<long double>(hit.timestamp_canonical - earliest_raw) -
                       (correction != nullptr ? timewalkDelay(hit.tot_raw, *correction) : 0.0);
            };
            long double scale = 0.0L;
            for (const auto& hit : cluster.hits) {
                const long double magnitude = std::fabs(offset(hit));
                if (magnitude > scale) scale = magnitude;
            }
            long double scaled_sum = 0.0L;
            for (const auto& hit : cluster.hits) {
                scaled_sum += offset(hit) / scale;
            }
            mean_offset =
                (scaled_sum / static_cast<long double>(cluster.hits.size())) * scale;
        }
        photon.timestamp_canonical = timestampWithOffset(earliest_raw, mean_offset);
    }
    return photon;
}

}  // namespace hermes_photon_clusterer
