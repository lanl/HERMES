#include "clustering.h"

#include <algorithm>
#include <cstdint>
#include <deque>
#include <vector>

namespace hermes_event_reconstructor {

namespace {

// Fixed chip width in pixels; the spatial grid spans one 256 x 256 chip.
constexpr int kChipWidthPixels = 256;

// Union-Find (disjoint-set) over photon indices with union by size and path
// compression. Each cluster's root photon carries the data needed to close the
// cluster: its member photon indices, its earliest photon time, and how many of
// its members are still inside the current time window (see clusterPhotons). A
// cluster can be finished once none of its photons remain in the window.
class PhotonClusterSets {
  public:
    explicit PhotonClusterSets(std::size_t photon_count)
        : parent_(photon_count),
          cluster_size_(photon_count, 1),
          photons_in_window_count_(photon_count, 0) {
        members_.resize(photon_count);
        earliest_time_.resize(photon_count, 0.0);
        for (std::size_t i = 0; i < photon_count; ++i) {
            parent_[i] = i;
        }
    }

    // Starts photon i as its own single-member cluster. That one photon is
    // currently inside the time window.
    void startCluster(std::size_t i, double timestamp) {
        members_[i] = {i};
        earliest_time_[i] = timestamp;
        photons_in_window_count_[i] = 1;
    }

    std::size_t findRoot(std::size_t i) {
        while (parent_[i] != i) {
            parent_[i] = parent_[parent_[i]];
            i = parent_[i];
        }
        return i;
    }

    // Links the clusters of photons a and b into one. The larger member list
    // survives so the splice is cheap; earliest time and active count combine.
    void linkClusters(std::size_t a, std::size_t b) {
        std::size_t root_a = findRoot(a);
        std::size_t root_b = findRoot(b);
        if (root_a == root_b) {
            return;
        }
        if (members_[root_a].size() < members_[root_b].size()) {
            std::swap(root_a, root_b);
        }
        auto& survivor = members_[root_a];
        auto& absorbed = members_[root_b];
        survivor.insert(survivor.end(), absorbed.begin(), absorbed.end());
        absorbed.clear();
        earliest_time_[root_a] =
            std::min(earliest_time_[root_a], earliest_time_[root_b]);
        photons_in_window_count_[root_a] += photons_in_window_count_[root_b];
        photons_in_window_count_[root_b] = 0;
        cluster_size_[root_a] += cluster_size_[root_b];
        parent_[root_b] = root_a;
    }

    // Records that one photon of i's cluster has dropped out of the time window.
    // Returns true when the cluster now has no photons left in the window, so it
    // can never grow again and is finished.
    bool removeOnePhotonFromWindow(std::size_t i) {
        const std::size_t root = findRoot(i);
        --photons_in_window_count_[root];
        return photons_in_window_count_[root] == 0;
    }

    double earliestTime(std::size_t i) { return earliest_time_[findRoot(i)]; }

    // Removes and returns the member photon indices of i's cluster, ascending.
    std::vector<std::size_t> takeMembers(std::size_t i) {
        const std::size_t root = findRoot(i);
        std::vector<std::size_t> members = std::move(members_[root]);
        members_[root].clear();
        std::sort(members.begin(), members.end());
        return members;
    }

  private:
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> cluster_size_;
    std::vector<std::size_t> photons_in_window_count_;
    std::vector<double> earliest_time_;
    std::vector<std::vector<std::size_t>> members_;
};

}  // namespace

void clusterPhotons(
    const std::vector<PhotonEvent>& photons,
    double spatial_link_radius_pixels,
    double max_time_difference_ticks,
    int cell_width,
    const std::function<void(std::vector<std::size_t>&&)>& on_photon_cluster) {
    if (photons.empty()) {
        return;
    }

    const double radius_squared =
        spatial_link_radius_pixels * spatial_link_radius_pixels;

    // Number of cells along each axis. The largest pixel index is 255, so this
    // covers every in-range coordinate; out-of-range coordinates are clamped.
    const int cells_per_axis = (kChipWidthPixels - 1) / cell_width + 1;
    auto cellIndexOnAxis = [&](double coordinate) {
        int index = static_cast<int>(coordinate) / cell_width;
        if (index < 0) {
            index = 0;
        }
        if (index >= cells_per_axis) {
            index = cells_per_axis - 1;
        }
        return index;
    };

    // The spatial grid indexes only the photons currently inside the time
    // window, so a photon is added when it arrives and removed once it falls out
    // of the window. Each grid cell holds the indices of the windowed photons
    // whose (x, y) lands in that cell; photon_cell records which cell each
    // photon was put in so it can be removed later.
    std::vector<std::vector<std::size_t>> cells(
        static_cast<std::size_t>(cells_per_axis) * cells_per_axis);
    std::vector<int> photon_cell(photons.size(), 0);

    // The photons currently inside the time window, in arrival (time) order.
    // The oldest is at the front, so expired photons are dropped from the front.
    std::deque<std::size_t> photons_in_window;

    PhotonClusterSets clusters(photons.size());

    // Removes a photon from the grid cell it was put in (swap-and-pop; each cell
    // holds only a handful of windowed photons).
    auto removeFromCell = [&](std::size_t index) {
        auto& cell = cells[static_cast<std::size_t>(photon_cell[index])];
        for (std::size_t k = 0; k < cell.size(); ++k) {
            if (cell[k] == index) {
                cell[k] = cell.back();
                cell.pop_back();
                return;
            }
        }
    };

    for (std::size_t i = 0; i < photons.size(); ++i) {
        const double t_i = photons[i].timestamp_canonical;

        // 1. Drop photons that are now more than max_time_difference_ticks
        //    behind photon i. Because photons arrive in time order, such a
        //    photon is too far back in time to link with photon i or with any
        //    photon after it, so it leaves the time window: remove it from its
        //    grid cell. Removing it may empty its cluster's window count, which
        //    means that cluster can no longer gain photons and is finished, so
        //    hand its members to on_photon_cluster. Because the front of the
        //    deque is the oldest photon, clusters finish in time order.
        while (!photons_in_window.empty()) {
            const std::size_t oldest = photons_in_window.front();
            if (t_i - photons[oldest].timestamp_canonical <=
                max_time_difference_ticks) {
                break;
            }
            photons_in_window.pop_front();
            removeFromCell(oldest);
            if (clusters.removeOnePhotonFromWindow(oldest)) {
                on_photon_cluster(clusters.takeMembers(oldest));
            }
        }

        // Start photon i as its own cluster before linking, so links have a
        // valid cluster to join.
        clusters.startCluster(i, t_i);

        // 2. Look for photons within the linking radius of photon i by scanning
        //    its own grid cell and the eight cells around it. Every photon still
        //    in the grid is inside the time window, so it already passes the
        //    time bound and only the squared-distance bound has to be checked.
        const int cx = cellIndexOnAxis(photons[i].x);
        const int cy = cellIndexOnAxis(photons[i].y);
        for (int dy = -1; dy <= 1; ++dy) {
            const int ny = cy + dy;
            if (ny < 0 || ny >= cells_per_axis) {
                continue;
            }
            for (int dx = -1; dx <= 1; ++dx) {
                const int nx = cx + dx;
                if (nx < 0 || nx >= cells_per_axis) {
                    continue;
                }
                const auto& cell =
                    cells[static_cast<std::size_t>(ny) * cells_per_axis + nx];
                for (const std::size_t j : cell) {
                    const double ddx = photons[i].x - photons[j].x;
                    const double ddy = photons[i].y - photons[j].y;
                    if (ddx * ddx + ddy * ddy <= radius_squared) {
                        clusters.linkClusters(i, j);
                    }
                }
            }
        }

        // 3. Photon i is now inside the time window: record which grid cell it
        //    went into and add it to the back of the window (the newest photon).
        const int cell_index = cy * cells_per_axis + cx;
        photon_cell[i] = cell_index;
        cells[static_cast<std::size_t>(cell_index)].push_back(i);
        photons_in_window.push_back(i);
    }

    // Every remaining photon is still inside the window, so its cluster was
    // never finished above. Emit those leftover clusters in earliest-photon-time
    // order, breaking ties by smallest member index so the order is fixed.
    std::vector<bool> root_seen(photons.size(), false);
    std::vector<std::size_t> cluster_roots;
    for (const std::size_t index : photons_in_window) {
        const std::size_t root = clusters.findRoot(index);
        if (!root_seen[root]) {
            root_seen[root] = true;
            cluster_roots.push_back(root);
        }
    }
    std::sort(cluster_roots.begin(), cluster_roots.end(),
              [&](std::size_t a, std::size_t b) {
                  const double ta = clusters.earliestTime(a);
                  const double tb = clusters.earliestTime(b);
                  if (ta != tb) {
                      return ta < tb;
                  }
                  return a < b;
              });
    for (const std::size_t root : cluster_roots) {
        on_photon_cluster(clusters.takeMembers(root));
    }
}

}  // namespace hermes_event_reconstructor
