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
// compression. Each set root also carries the data needed to close a component:
// its member indices, its earliest photon time, and how many of its members are
// still active in the rolling time window.
class ComponentSets {
  public:
    explicit ComponentSets(std::size_t count)
        : parent_(count), size_(count, 1), active_(count, 0) {
        members_.resize(count);
        min_time_.resize(count, 0.0);
        for (std::size_t i = 0; i < count; ++i) {
            parent_[i] = i;
        }
    }

    // Starts photon i as its own single-member, single-active component.
    void start(std::size_t i, double timestamp) {
        members_[i] = {i};
        min_time_[i] = timestamp;
        active_[i] = 1;
    }

    std::size_t find(std::size_t i) {
        while (parent_[i] != i) {
            parent_[i] = parent_[parent_[i]];
            i = parent_[i];
        }
        return i;
    }

    // Merges the components of a and b. The larger member list survives so the
    // splice is cheap; earliest time and active count combine.
    void unite(std::size_t a, std::size_t b) {
        std::size_t ra = find(a);
        std::size_t rb = find(b);
        if (ra == rb) {
            return;
        }
        if (members_[ra].size() < members_[rb].size()) {
            std::swap(ra, rb);
        }
        auto& survivor = members_[ra];
        auto& merged = members_[rb];
        survivor.insert(survivor.end(), merged.begin(), merged.end());
        merged.clear();
        min_time_[ra] = std::min(min_time_[ra], min_time_[rb]);
        active_[ra] += active_[rb];
        active_[rb] = 0;
        size_[ra] += size_[rb];
        parent_[rb] = ra;
    }

    // Records that one member of i's component has left the time window. Returns
    // true when the component now has no active members and can be closed.
    bool deactivateOne(std::size_t i) {
        const std::size_t r = find(i);
        --active_[r];
        return active_[r] == 0;
    }

    double minTime(std::size_t i) { return min_time_[find(i)]; }

    // Removes and returns the member indices of i's component, ascending.
    std::vector<std::size_t> takeMembers(std::size_t i) {
        const std::size_t r = find(i);
        std::vector<std::size_t> members = std::move(members_[r]);
        members_[r].clear();
        std::sort(members.begin(), members.end());
        return members;
    }

  private:
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> size_;
    std::vector<std::size_t> active_;
    std::vector<double> min_time_;
    std::vector<std::vector<std::size_t>> members_;
};

}  // namespace

void clusterPhotons(
    const std::vector<PhotonEvent>& photons,
    double spatial_link_radius_pixels,
    double max_time_difference_ticks,
    int cell_width,
    const std::function<void(std::vector<std::size_t>&&)>& on_component) {
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

    // Fixed spatial grid over active photons, and the cell each photon occupies.
    std::vector<std::vector<std::size_t>> cells(
        static_cast<std::size_t>(cells_per_axis) * cells_per_axis);
    std::vector<int> photon_cell(photons.size(), 0);

    // Rolling time window: active photon indices in insertion (time) order.
    std::deque<std::size_t> active_by_time;

    ComponentSets components(photons.size());

    // Removes a photon from its spatial cell (swap-and-pop; cells are small).
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

        // 1. Expire photons outside the inclusive time gate, and close any
        //    component whose last active member just expired. Expired photons
        //    can never connect to this or any later photon, so a component with
        //    no active members is final and is emitted in close order.
        while (!active_by_time.empty()) {
            const std::size_t oldest = active_by_time.front();
            if (t_i - photons[oldest].timestamp_canonical <=
                max_time_difference_ticks) {
                break;
            }
            active_by_time.pop_front();
            removeFromCell(oldest);
            if (components.deactivateOne(oldest)) {
                on_component(components.takeMembers(oldest));
            }
        }

        // Start photon i as its own component before linking, so unions have a
        // valid set to join.
        components.start(i, t_i);

        // 2. Search photon i's own cell and the 3x3 neighborhood. Every photon
        //    still in the grid is active and already satisfies the time gate,
        //    so only the exact squared-distance test is applied.
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
                        components.unite(i, j);
                    }
                }
            }
        }

        // 3. Insert photon i into its cell and the rolling time window.
        const int cell_index = cy * cells_per_axis + cx;
        photon_cell[i] = cell_index;
        cells[static_cast<std::size_t>(cell_index)].push_back(i);
        active_by_time.push_back(i);
    }

    // Flush every still-open component in earliest-photon-time order. Ties are
    // broken by smallest member index so the order is deterministic.
    std::vector<std::size_t> remaining(active_by_time.begin(),
                                       active_by_time.end());
    std::vector<std::size_t> roots;
    for (const std::size_t index : remaining) {
        const std::size_t root = components.find(index);
        if (std::find(roots.begin(), roots.end(), root) == roots.end()) {
            roots.push_back(root);
        }
    }
    std::sort(roots.begin(), roots.end(),
              [&](std::size_t a, std::size_t b) {
                  const double ta = components.minTime(a);
                  const double tb = components.minTime(b);
                  if (ta != tb) {
                      return ta < tb;
                  }
                  return a < b;
              });
    for (const std::size_t root : roots) {
        on_component(components.takeMembers(root));
    }
}

}  // namespace hermes_event_reconstructor
