#ifndef HERMES_EVENT_RECONSTRUCTOR_CLUSTERING_H
#define HERMES_EVENT_RECONSTRUCTOR_CLUSTERING_H

#include <cstddef>
#include <functional>
#include <vector>

#include "photon_reader.h"

namespace hermes_event_reconstructor {

// Streaming sparse spatiotemporal connected-components clustering.
//
// Photons must arrive in non-decreasing timestamp_canonical order (the photon
// reader guarantees this). Two photons are connected when they satisfy both:
//   spatial:  (x_i - x_j)^2 + (y_i - y_j)^2 <= spatial_link_radius_pixels^2
//   temporal: |t_i - t_j| <= max_time_difference_ticks
// Both bounds are inclusive. Connectivity is transitive, so components may
// branch; every connected photon contributes equally, with no dependence on
// processing order. Every connected component becomes one candidate event.
//
// A fixed spatial grid with the given cell_width (in pixels) accelerates the
// neighbor search over active photons; a rolling time window expires photons
// that can no longer connect to any future photon. cell_width is a lookup
// accelerator only: any cell_width at least the linking radius produces the
// same components. on_component receives the member photon indices (into the
// photons vector, ascending) of each connected component as it closes, in the
// order components close; any still-open components are flushed at end of input
// in earliest-photon-time order.
void clusterPhotons(
    const std::vector<PhotonEvent>& photons,
    double spatial_link_radius_pixels,
    double max_time_difference_ticks,
    int cell_width,
    const std::function<void(std::vector<std::size_t>&&)>& on_component);

}  // namespace hermes_event_reconstructor

#endif
