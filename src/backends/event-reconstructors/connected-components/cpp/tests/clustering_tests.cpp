#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

#include "clustering.h"
#include "photon_reader.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::clusterPhotons;
using hermes_event_reconstructor::PhotonEvent;

// Runs clustering and returns each component as a sorted list of member
// photon_ids, with the components themselves sorted for order-independent
// comparison. Photons must already be in non-decreasing time order.
std::vector<std::vector<std::uint64_t>> componentsOf(
    const std::vector<PhotonEvent>& photons,
    double r_link,
    double dt_link,
    int cell_width) {
    std::vector<std::vector<std::uint64_t>> result;
    clusterPhotons(photons, r_link, dt_link, cell_width,
                   [&](std::vector<std::size_t>&& members) {
                       std::vector<std::uint64_t> ids;
                       for (const std::size_t index : members) {
                           ids.push_back(photons[index].photon_id);
                       }
                       std::sort(ids.begin(), ids.end());
                       result.push_back(std::move(ids));
                   });
    std::sort(result.begin(), result.end());
    return result;
}

}  // namespace

int main() {
    TestContext test;

    const double r_link = 4.0;
    const double dt_link = 100.0;
    const int cell_width = 16;

    // Two photons within both bounds form one component.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 12.0, 10.0, 50.0},  // distance 2, dt 50
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{1}, "within bounds: one component");
        if (comps.size() == 1) {
            test.expectEqual(comps[0].size(), std::size_t{2}, "both photons joined");
        }
    }

    // Just outside the spatial bound: two components.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 15.0, 10.0, 10.0},  // distance 5 > r_link 4
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{2}, "too far apart: two components");
    }

    // Exactly on the spatial bound (distance == r_link) is inclusive: joined.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 14.0, 10.0, 10.0},  // distance exactly 4
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{1},
                         "distance == r_link is inclusive");
    }

    // Just outside the temporal bound: two components.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 10.0, 10.0, 150.0},  // dt 150 > dt_link 100
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{2}, "too far in time: two components");
    }

    // Exactly on the temporal bound (dt == dt_link) is inclusive: joined.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 10.0, 10.0, 100.0},  // dt exactly 100
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{1}, "dt == dt_link is inclusive");
    }

    // Transitive chain: each step within bounds, so all three join even though
    // photon 0 and photon 2 are 6 pixels apart (> r_link).
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 13.0, 10.0, 20.0},
            PhotonEvent{2, 16.0, 10.0, 40.0},
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{1}, "transitive chain: one component");
        if (comps.size() == 1) {
            test.expectEqual(comps[0].size(), std::size_t{3}, "all three chained");
        }
    }

    // A spatial gap in the middle of a chain keeps two components apart.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 13.0, 10.0, 20.0},   // links to 0
            PhotonEvent{2, 30.0, 10.0, 40.0},   // far from the first pair
            PhotonEvent{3, 32.0, 10.0, 60.0},   // links to 2
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{2}, "spatial gap: two components");
    }

    // Branching: a central photon links to three neighbors in different
    // directions; all four form one component.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 20.0, 20.0, 0.0},   // center
            PhotonEvent{1, 23.0, 20.0, 10.0},  // right
            PhotonEvent{2, 17.0, 20.0, 20.0},  // left
            PhotonEvent{3, 20.0, 23.0, 30.0},  // up
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{1}, "branching: one component");
        if (comps.size() == 1) {
            test.expectEqual(comps[0].size(), std::size_t{4}, "all four branches joined");
        }
    }

    // Single photon yields a single-member component (never discarded).
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 100.0, 100.0, 0.0},
        };
        const auto comps = componentsOf(photons, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{1}, "single photon: one component");
        if (comps.size() == 1) {
            test.expectEqual(comps[0].size(), std::size_t{1}, "one member");
        }
    }

    // Invariance: the components must be identical for several cell widths at or
    // above the linking radius. This guards the "cell size never changes
    // results" principle. Uses a mixed scene with a chain, a branch, a lone
    // photon, and a time-separated pair at the same location.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 13.0, 10.0, 15.0},
            PhotonEvent{2, 16.0, 10.0, 30.0},
            PhotonEvent{3, 200.0, 200.0, 45.0},
            PhotonEvent{4, 202.0, 202.0, 60.0},
            PhotonEvent{5, 50.0, 50.0, 75.0},
            PhotonEvent{6, 50.0, 50.0, 500.0},  // same spot, far in time
            PhotonEvent{7, 120.0, 12.0, 90.0},
            PhotonEvent{8, 122.0, 30.0, 110.0},
        };
        // cell widths: 4 (== r_link), 8, 16, 52 (default 5 cells), 64, 256.
        const std::vector<int> widths = {4, 8, 16, 52, 64, 256};
        const auto reference = componentsOf(photons, r_link, dt_link, widths[0]);
        bool all_match = true;
        for (const int width : widths) {
            if (componentsOf(photons, r_link, dt_link, width) != reference) {
                all_match = false;
            }
        }
        test.expect(all_match, "components are identical across cell widths");
        // Sanity: the same-location pair split by time is two components, not one.
        bool found_lone_500 = false;
        for (const auto& comp : reference) {
            if (comp.size() == 1 &&
                (comp[0] == 5 || comp[0] == 6)) {
                found_lone_500 = true;
            }
        }
        test.expect(found_lone_500,
                    "same-location photons far apart in time stay separate");
    }

    // Emission order: closed components are delivered in time order. Build two
    // well-separated events; the earlier one must be emitted first.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 11.0, 10.0, 5.0},
            PhotonEvent{2, 200.0, 200.0, 1000.0},
            PhotonEvent{3, 201.0, 200.0, 1005.0},
        };
        std::vector<double> first_times;
        clusterPhotons(photons, r_link, dt_link, cell_width,
                       [&](std::vector<std::size_t>&& members) {
                           double earliest = photons[members[0]].timestamp_canonical;
                           for (const std::size_t index : members) {
                               earliest = std::min(
                                   earliest, photons[index].timestamp_canonical);
                           }
                           first_times.push_back(earliest);
                       });
        test.expectEqual(first_times.size(), std::size_t{2}, "two components emitted");
        if (first_times.size() == 2) {
            test.expect(first_times[0] <= first_times[1],
                        "components emitted in time order");
        }
    }

    // Empty input produces no components.
    {
        const auto comps = componentsOf({}, r_link, dt_link, cell_width);
        test.expectEqual(comps.size(), std::size_t{0}, "empty input: no components");
    }

    return test.finish();
}
