#include <cstdint>

#include "cluster_filter.h"
#include "clustering.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::ClusterFilterSettings;
using hermes_photon_clusterer::PixelCluster;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::RejectionCounts;
using hermes_photon_clusterer::evaluateCluster;
using hermes_photon_clusterer::kQualityBridgedComponents;
using hermes_photon_clusterer::kQualitySaturatedPixel;
using hermes_photon_clusterer::kSaturatedTot;

// Permissive settings that accept a small compact cluster; individual tests
// tighten one bound at a time.
ClusterFilterSettings permissiveSettings() {
    ClusterFilterSettings settings;
    settings.min_cluster_size = 1;
    settings.max_cluster_size = 64;
    settings.min_cluster_tot_raw = 0;
    settings.max_cluster_tot_raw = 1000000;
    settings.max_aspect_ratio = 3.0;
    settings.min_filled_fraction = 0.5;
    return settings;
}

PixelCluster makeCluster(std::vector<PixelHit> hits, bool bridged = false) {
    PixelCluster cluster;
    cluster.hits = std::move(hits);
    cluster.bridged_components = bridged;
    return cluster;
}

}  // namespace

int main() {
    TestContext test;

    // A compact 2x2 block passes every filter.
    {
        auto cluster = makeCluster({
            PixelHit{0, 0, 10, 100},
            PixelHit{1, 0, 10, 100},
            PixelHit{0, 1, 10, 100},
            PixelHit{1, 1, 10, 100},
        });
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, permissiveSettings(), counts);
        test.expect(evaluation.accepted, "compact 2x2 cluster is accepted");
        test.expectEqual(evaluation.pixel_count, std::uint32_t{4},
                         "pixel count is four");
        test.expectEqual(evaluation.integrated_tot, std::uint64_t{40},
                         "integrated ToT sums pixels");
        test.expect(evaluation.aspect_ratio == 1.0, "square aspect ratio is one");
        test.expect(evaluation.filled_fraction == 1.0, "block is fully filled");
        test.expectEqual(evaluation.quality_flags, std::uint16_t{0},
                         "clean cluster has no quality flags");
    }

    // A single pixel below the minimum cluster size is rejected.
    {
        auto settings = permissiveSettings();
        settings.min_cluster_size = 2;
        auto cluster = makeCluster({PixelHit{5, 5, 10, 100}});
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, settings, counts);
        test.expect(!evaluation.accepted, "undersized cluster is rejected");
        test.expectEqual(counts.below_min_cluster_size, std::uint64_t{1},
                         "below-min-size reason counted");
    }

    // A long thin line (cosmic-ray-like) is fully filled along its length but
    // trips the aspect-ratio bound.
    {
        auto cluster = makeCluster({
            PixelHit{0, 0, 10, 100},
            PixelHit{1, 0, 10, 100},
            PixelHit{2, 0, 10, 100},
            PixelHit{3, 0, 10, 100},
            PixelHit{4, 0, 10, 100},
        });
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, permissiveSettings(), counts);
        test.expect(!evaluation.accepted, "long thin track is rejected");
        test.expectEqual(counts.above_max_aspect_ratio, std::uint64_t{1},
                         "aspect-ratio reason counted");
    }

    // A sparse diagonal cluster fills too little of its bounding box.
    {
        auto cluster = makeCluster({
            PixelHit{0, 0, 10, 100},
            PixelHit{1, 1, 10, 100},
            PixelHit{2, 2, 10, 100},
        });
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, permissiveSettings(), counts);
        test.expect(!evaluation.accepted, "sparse diagonal cluster is rejected");
        test.expectEqual(counts.below_min_filled_fraction, std::uint64_t{1},
                         "filled-fraction reason counted");
    }

    // Integrated ToT above the maximum is rejected.
    {
        auto settings = permissiveSettings();
        settings.max_cluster_tot_raw = 15;
        auto cluster = makeCluster({
            PixelHit{0, 0, 10, 100},
            PixelHit{1, 0, 10, 100},
        });
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, settings, counts);
        test.expect(!evaluation.accepted, "over-bright cluster is rejected");
        test.expectEqual(counts.above_max_cluster_tot, std::uint64_t{1},
                         "above-max-tot reason counted");
    }

    // An accepted cluster with a saturated pixel and a bridged merge carries
    // both quality flags.
    {
        auto cluster = makeCluster(
            {
                PixelHit{0, 0, kSaturatedTot, 100},
                PixelHit{1, 0, 10, 100},
                PixelHit{0, 1, 10, 100},
                PixelHit{1, 1, 10, 100},
            },
            /*bridged=*/true);
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, permissiveSettings(), counts);
        test.expect(evaluation.accepted, "compact bridged cluster still accepted");
        test.expect((evaluation.quality_flags & kQualitySaturatedPixel) != 0,
                    "saturated-pixel flag set");
        test.expect((evaluation.quality_flags & kQualityBridgedComponents) != 0,
                    "bridged-components flag set");
    }

    // A rejected cluster does not report quality flags.
    {
        auto settings = permissiveSettings();
        settings.min_cluster_size = 10;
        auto cluster = makeCluster({PixelHit{0, 0, kSaturatedTot, 100}},
                                   /*bridged=*/true);
        RejectionCounts counts;
        auto evaluation = evaluateCluster(cluster, settings, counts);
        test.expect(!evaluation.accepted, "undersized cluster rejected");
        test.expectEqual(evaluation.quality_flags, std::uint16_t{0},
                         "rejected cluster reports no quality flags");
    }

    return test.finish();
}
