#include <algorithm>
#include <cstddef>
#include <vector>

#include "clustering.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::PixelCluster;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::clusterPixelHits;

// Runs clustering over a fixed list of hits and returns the closed clusters in
// delivery order.
std::vector<PixelCluster> runClustering(std::vector<PixelHit> hits,
                                        int adjacency,
                                        std::uint64_t max_time_spread_ticks) {
    std::size_t cursor = 0;
    auto next_hit = [&](PixelHit& out) {
        if (cursor >= hits.size()) {
            return false;
        }
        out = hits[cursor++];
        return true;
    };
    std::vector<PixelCluster> clusters;
    clusterPixelHits(next_hit, adjacency, max_time_spread_ticks,
                     [&](PixelCluster&& cluster) {
                         clusters.push_back(std::move(cluster));
                     });
    return clusters;
}

std::vector<std::pair<int, int>> coordinatesOf(const PixelCluster& cluster) {
    std::vector<std::pair<int, int>> coordinates;
    for (const auto& hit : cluster.hits) {
        coordinates.emplace_back(hit.x, hit.y);
    }
    std::sort(coordinates.begin(), coordinates.end());
    return coordinates;
}

}  // namespace

int main() {
    TestContext test;

    // 8-connected diagonal chain grows transitively but does not jump the gap
    // between (2,2) and (4,4).
    {
        auto clusters = runClustering(
            {
                PixelHit{0, 0, 10, 100},
                PixelHit{1, 1, 10, 101},
                PixelHit{2, 2, 10, 102},
                PixelHit{4, 4, 10, 103},
            },
            8, 2000);
        test.expectEqual(clusters.size(), std::size_t{2},
                         "8-connected chain yields two clusters");
        if (clusters.size() == 2) {
            test.expectEqual(clusters[0].hits.size(), std::size_t{3},
                             "first cluster has three pixels");
            test.expectEqual(clusters[1].hits.size(), std::size_t{1},
                             "gap pixel is its own cluster");
        }
    }

    // 4-connected does not join diagonal neighbors.
    {
        auto clusters = runClustering(
            {
                PixelHit{0, 0, 10, 100},
                PixelHit{1, 1, 10, 101},
            },
            4, 2000);
        test.expectEqual(clusters.size(), std::size_t{2},
                         "4-connected diagonals stay separate");
    }

    // 4-connected joins an orthogonal neighbor.
    {
        auto clusters = runClustering(
            {
                PixelHit{0, 0, 10, 100},
                PixelHit{1, 0, 10, 101},
            },
            4, 2000);
        test.expectEqual(clusters.size(), std::size_t{1},
                         "4-connected orthogonal neighbors join");
    }

    // Two spatial neighbors separated by more than the time gate form two
    // clusters; the gate is measured from the cluster's earliest timestamp.
    {
        auto clusters = runClustering(
            {
                PixelHit{5, 5, 10, 1000},
                PixelHit{5, 6, 10, 4000},
            },
            8, 2000);
        test.expectEqual(clusters.size(), std::size_t{2},
                         "time gate splits late neighbor into new cluster");
    }

    // A neighbor exactly at the inclusive gate joins the same cluster.
    {
        auto clusters = runClustering(
            {
                PixelHit{5, 5, 10, 1000},
                PixelHit{5, 6, 10, 3000},
            },
            8, 2000);
        test.expectEqual(clusters.size(), std::size_t{1},
                         "neighbor at the inclusive gate joins");
    }

    // Merging two separate open components via a bridging pixel marks the
    // cluster as bridged and collects all pixels.
    {
        auto clusters = runClustering(
            {
                PixelHit{0, 0, 10, 100},
                PixelHit{2, 0, 10, 101},
                PixelHit{1, 0, 10, 102},
            },
            8, 2000);
        test.expectEqual(clusters.size(), std::size_t{1},
                         "bridging pixel merges two components");
        if (clusters.size() == 1) {
            test.expect(clusters[0].bridged_components,
                        "merged cluster is flagged as bridged");
            test.expectEqual(clusters[0].hits.size(), std::size_t{3},
                             "merged cluster keeps all three pixels");
            const auto coordinates = coordinatesOf(clusters[0]);
            test.expect(coordinates ==
                            (std::vector<std::pair<int, int>>{
                                {0, 0}, {1, 0}, {2, 0}}),
                        "merged cluster has the expected coordinates");
        }
    }

    return test.finish();
}
