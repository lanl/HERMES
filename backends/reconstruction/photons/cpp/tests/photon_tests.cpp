#include <cstdint>

#include "cluster_filter.h"
#include "clustering.h"
#include "photon.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::ClusterEvaluation;
using hermes_photon_clusterer::PixelCluster;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::buildPhoton;

}  // namespace

int main() {
    TestContext test;

    // A 2x2 block centers between its pixels, sums ToT, and takes the earliest
    // source-pixel timestamp as the uncorrected leading edge.
    {
        PixelCluster cluster;
        cluster.hits = {
            PixelHit{2, 4, 10, 205},
            PixelHit{3, 4, 20, 200},
            PixelHit{2, 5, 30, 210},
            PixelHit{3, 5, 40, 208},
        };
        ClusterEvaluation evaluation;
        evaluation.integrated_tot = 100;
        evaluation.quality_flags = 0;

        auto photon = buildPhoton(cluster, evaluation, nullptr);
        test.expect(photon.x == 2.5, "x is the arithmetic mean");
        test.expect(photon.y == 4.5, "y is the arithmetic mean");
        test.expectEqual(photon.tot, std::uint64_t{100},
                         "tot comes from the evaluation's summed tot_raw");
        test.expect(photon.timestamp_canonical == 200.0,
                    "timestamp is the earliest source-pixel time");
    }

    // A single pixel maps straight through and carries its quality flags.
    {
        PixelCluster cluster;
        cluster.hits = {PixelHit{7, 9, 15, 500}};
        ClusterEvaluation evaluation;
        evaluation.integrated_tot = 15;
        evaluation.quality_flags = 0b11;

        auto photon = buildPhoton(cluster, evaluation, nullptr);
        test.expect(photon.x == 7.0, "single-pixel x");
        test.expect(photon.y == 9.0, "single-pixel y");
        test.expect(photon.timestamp_canonical == 500.0, "single-pixel time");
        test.expectEqual(photon.quality_flags, std::uint16_t{0b11},
                         "quality flags carried from the evaluation");
    }

    return test.finish();
}
