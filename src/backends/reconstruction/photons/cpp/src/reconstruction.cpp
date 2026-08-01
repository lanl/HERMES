#include "reconstruction.h"

#include "clustering.h"

namespace hermes_photon_clusterer {

PhotonReconstruction reconstructPhotons(
    const std::function<bool(PixelHit&)>& next_hit,
    const ClusteringSettings& settings,
    const TimewalkCorrection* correction,
    bool collect_pixels) {
    PhotonReconstruction result;

    // Wrap the source stream with the per-pixel min-ToT filter so noise pixels
    // are dropped before clustering. Counting happens here, on the raw stream,
    // so pixel_rows_read reflects every row delivered by next_hit.
    auto filtered_next_hit = [&](PixelHit& hit) -> bool {
        while (next_hit(hit)) {
            ++result.counts.pixel_rows_read;
            if (hit.tot_raw < settings.min_pixel_tot_raw) {
                ++result.counts.pixel_rows_below_min_tot;
                continue;
            }
            return true;
        }
        return false;
    };

    const ClusterFilterSettings filter_settings{
        settings.min_cluster_size,   settings.max_cluster_size,
        settings.min_cluster_tot_raw, settings.max_cluster_tot_raw,
        settings.max_aspect_ratio,   settings.min_filled_fraction};

    auto on_cluster = [&](PixelCluster&& cluster) {
        ++result.counts.components_formed;

        ClusterEvaluation evaluation =
            evaluateCluster(cluster, filter_settings, result.counts.rejection_counts);
        if (!evaluation.accepted) {
            ++result.counts.rejected_component_count;
            return;
        }

        const std::uint64_t photon_id = result.photons.size();
        Photon photon = buildPhoton(cluster, evaluation, correction);
        result.photons.push_back(photon);
        ++result.counts.photon_count;

        if (evaluation.quality_flags & kQualitySaturatedPixel) {
            ++result.counts.saturated_pixel_count;
        }
        if (evaluation.quality_flags & kQualityBridgedComponents) {
            ++result.counts.bridged_components_count;
        }

        if (collect_pixels) {
            for (const PixelHit& hit : cluster.hits) {
                PhotonPixelRow row;
                row.photon_id = photon_id;
                row.pixel_event_id = hit.pixel_event_id;
                row.x = hit.x;
                row.y = hit.y;
                row.tot_raw = hit.tot_raw;
                row.timestamp_canonical = hit.timestamp_canonical;
                result.photon_pixels.push_back(row);
            }
        }
    };

    clusterPixelHits(filtered_next_hit, settings.adjacency,
                     settings.max_time_spread_ticks, on_cluster);

    return result;
}

}  // namespace hermes_photon_clusterer
