#include "clustering.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <queue>
#include <set>
#include <unordered_map>
#include <utility>
#include <vector>

namespace hermes_photon_clusterer {

namespace {

// Packs a pixel coordinate into one integer key for the coordinate index.
std::uint64_t coordinateKey(std::uint16_t x, std::uint16_t y) {
    return (static_cast<std::uint64_t>(x) << 16U) | static_cast<std::uint64_t>(y);
}

// Neighbor offsets including the pixel itself so an exact-coordinate repeat
// joins the same cluster. 4-connectivity is the plus shape; 8-connectivity is
// the full 3x3 block.
std::vector<std::pair<int, int>> neighborOffsets(int adjacency) {
    if (adjacency == 4) {
        return {{0, 0}, {-1, 0}, {1, 0}, {0, -1}, {0, 1}};
    }
    std::vector<std::pair<int, int>> offsets;
    for (int dx = -1; dx <= 1; ++dx) {
        for (int dy = -1; dy <= 1; ++dy) {
            offsets.emplace_back(dx, dy);
        }
    }
    return offsets;
}

struct OpenCluster {
    std::vector<PixelHit> hits;
    std::vector<std::uint64_t> coordinates;
    std::uint64_t min_timestamp = 0;
    bool bridged_components = false;
};

}  // namespace

void clusterPixelHits(const std::function<bool(PixelHit&)>& next_hit,
                      int adjacency,
                      std::uint64_t max_time_spread_ticks,
                      const std::function<void(PixelCluster&&)>& on_cluster) {
    const auto offsets = neighborOffsets(adjacency);

    std::unordered_map<std::uint64_t, OpenCluster> open_clusters;
    // coordinate key -> set of open cluster ids occupying it
    std::unordered_map<std::uint64_t, std::set<std::uint64_t>> coordinate_index;
    // min-heap of (min_timestamp, cluster_id) for time-gate expiration
    std::priority_queue<std::pair<std::uint64_t, std::uint64_t>,
                        std::vector<std::pair<std::uint64_t, std::uint64_t>>,
                        std::greater<>>
        expiration_heap;
    std::uint64_t next_cluster_id = 0;

    auto closeCluster = [&](std::uint64_t cluster_id) {
        auto node = open_clusters.find(cluster_id);
        if (node == open_clusters.end()) {
            return;
        }
        OpenCluster cluster = std::move(node->second);
        open_clusters.erase(node);
        for (std::uint64_t coordinate : cluster.coordinates) {
            auto index_entry = coordinate_index.find(coordinate);
            if (index_entry == coordinate_index.end()) {
                continue;
            }
            index_entry->second.erase(cluster_id);
            if (index_entry->second.empty()) {
                coordinate_index.erase(index_entry);
            }
        }
        PixelCluster closed;
        closed.hits = std::move(cluster.hits);
        closed.bridged_components = cluster.bridged_components;
        on_cluster(std::move(closed));
    };

    PixelHit hit;
    while (next_hit(hit)) {
        // Close every cluster whose window has fully passed for this timestamp.
        while (!expiration_heap.empty()) {
            const auto [min_timestamp, cluster_id] = expiration_heap.top();
            auto node = open_clusters.find(cluster_id);
            if (node == open_clusters.end() ||
                node->second.min_timestamp != min_timestamp) {
                expiration_heap.pop();
                continue;
            }
            if (hit.timestamp_canonical - min_timestamp <=
                max_time_spread_ticks) {
                break;
            }
            expiration_heap.pop();
            closeCluster(cluster_id);
        }

        // Find open clusters adjacent to this pixel.
        std::set<std::uint64_t> adjacent_ids;
        for (const auto& [dx, dy] : offsets) {
            const int nx = static_cast<int>(hit.x) + dx;
            const int ny = static_cast<int>(hit.y) + dy;
            if (nx < 0 || ny < 0 || nx > 0xFFFF || ny > 0xFFFF) {
                continue;
            }
            auto index_entry = coordinate_index.find(
                coordinateKey(static_cast<std::uint16_t>(nx),
                              static_cast<std::uint16_t>(ny)));
            if (index_entry != coordinate_index.end()) {
                adjacent_ids.insert(index_entry->second.begin(),
                                    index_entry->second.end());
            }
        }

        const std::uint64_t key = coordinateKey(hit.x, hit.y);
        if (adjacent_ids.empty()) {
            const std::uint64_t cluster_id = next_cluster_id++;
            OpenCluster cluster;
            cluster.hits.push_back(hit);
            cluster.coordinates.push_back(key);
            cluster.min_timestamp = hit.timestamp_canonical;
            open_clusters.emplace(cluster_id, std::move(cluster));
            coordinate_index[key].insert(cluster_id);
            expiration_heap.emplace(hit.timestamp_canonical, cluster_id);
            continue;
        }

        // Join the lowest-id adjacent cluster and merge the rest into it.
        const std::uint64_t surviving_id = *adjacent_ids.begin();
        OpenCluster& surviving = open_clusters[surviving_id];
        surviving.hits.push_back(hit);
        surviving.coordinates.push_back(key);
        coordinate_index[key].insert(surviving_id);
        if (adjacent_ids.size() > 1) {
            surviving.bridged_components = true;
        }

        for (std::uint64_t merged_id : adjacent_ids) {
            if (merged_id == surviving_id) {
                continue;
            }
            OpenCluster merged = std::move(open_clusters[merged_id]);
            open_clusters.erase(merged_id);
            surviving.hits.insert(surviving.hits.end(), merged.hits.begin(),
                                  merged.hits.end());
            surviving.coordinates.insert(surviving.coordinates.end(),
                                         merged.coordinates.begin(),
                                         merged.coordinates.end());
            surviving.min_timestamp =
                std::min(surviving.min_timestamp, merged.min_timestamp);
            surviving.bridged_components =
                surviving.bridged_components || merged.bridged_components;
            for (std::uint64_t coordinate : merged.coordinates) {
                auto& ids = coordinate_index[coordinate];
                ids.erase(merged_id);
                ids.insert(surviving_id);
            }
        }
    }

    // Flush remaining open clusters in earliest-timestamp order.
    std::vector<std::pair<std::uint64_t, std::uint64_t>> remaining;
    remaining.reserve(open_clusters.size());
    for (const auto& [cluster_id, cluster] : open_clusters) {
        remaining.emplace_back(cluster.min_timestamp, cluster_id);
    }
    std::sort(remaining.begin(), remaining.end());
    for (const auto& [min_timestamp, cluster_id] : remaining) {
        (void)min_timestamp;
        closeCluster(cluster_id);
    }
}

}  // namespace hermes_photon_clusterer
