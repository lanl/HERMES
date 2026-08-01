#include "cluster_filter.h"

#include <algorithm>
#include <cstdint>

namespace hermes_photon_clusterer {

ClusterEvaluation evaluateCluster(const PixelCluster& cluster,
                                  const ClusterFilterSettings& settings,
                                  RejectionCounts& counts) {
    ClusterEvaluation evaluation;
    evaluation.pixel_count = static_cast<std::uint32_t>(cluster.hits.size());

    // Bounding box and integrated ToT over every pixel in the cluster.
    std::uint16_t min_x = 0;
    std::uint16_t max_x = 0;
    std::uint16_t min_y = 0;
    std::uint16_t max_y = 0;
    bool first = true;
    bool saturated = false;
    for (const auto& hit : cluster.hits) {
        evaluation.integrated_tot += hit.tot_raw;
        if (hit.tot_raw >= kSaturatedTot) {
            saturated = true;
        }
        if (first) {
            min_x = max_x = hit.x;
            min_y = max_y = hit.y;
            first = false;
            continue;
        }
        min_x = std::min(min_x, hit.x);
        max_x = std::max(max_x, hit.x);
        min_y = std::min(min_y, hit.y);
        max_y = std::max(max_y, hit.y);
    }

    const std::uint32_t width =
        evaluation.pixel_count == 0 ? 0 : (max_x - min_x + 1);
    const std::uint32_t height =
        evaluation.pixel_count == 0 ? 0 : (max_y - min_y + 1);
    const std::uint32_t longer = std::max(width, height);
    const std::uint32_t shorter = std::min(width, height);
    evaluation.aspect_ratio =
        shorter == 0 ? 0.0
                     : static_cast<double>(longer) / static_cast<double>(shorter);
    const std::uint32_t bounding_area = width * height;
    evaluation.filled_fraction =
        bounding_area == 0
            ? 0.0
            : static_cast<double>(evaluation.pixel_count) /
                  static_cast<double>(bounding_area);

    // Non-exclusive rejection: increment every failing reason.
    bool rejected = false;
    if (evaluation.pixel_count < settings.min_cluster_size) {
        ++counts.below_min_cluster_size;
        rejected = true;
    }
    if (evaluation.pixel_count > settings.max_cluster_size) {
        ++counts.above_max_cluster_size;
        rejected = true;
    }
    if (evaluation.integrated_tot < settings.min_cluster_tot_raw) {
        ++counts.below_min_cluster_tot;
        rejected = true;
    }
    if (evaluation.integrated_tot > settings.max_cluster_tot_raw) {
        ++counts.above_max_cluster_tot;
        rejected = true;
    }
    if (evaluation.aspect_ratio > settings.max_aspect_ratio) {
        ++counts.above_max_aspect_ratio;
        rejected = true;
    }
    if (evaluation.filled_fraction < settings.min_filled_fraction) {
        ++counts.below_min_filled_fraction;
        rejected = true;
    }

    evaluation.accepted = !rejected;
    if (evaluation.accepted) {
        if (saturated) {
            evaluation.quality_flags |= kQualitySaturatedPixel;
        }
        if (cluster.bridged_components) {
            evaluation.quality_flags |= kQualityBridgedComponents;
        }
    }
    return evaluation;
}

}  // namespace hermes_photon_clusterer
