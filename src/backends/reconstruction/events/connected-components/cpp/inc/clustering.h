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
// reader guarantees this). Two photons are linked when they satisfy both:
//   spatial:  (x_i - x_j)^2 + (y_i - y_j)^2 <= spatial_link_radius_pixels^2
//   temporal: |t_i - t_j| <= max_time_difference_ticks
// Both bounds are inclusive. Linking is transitive, so a photon cluster may
// branch; every linked photon contributes equally, with no dependence on
// processing order. Each connected cluster of photons becomes one candidate
// event downstream.
//
// A fixed spatial grid over the sensor_width-pixel frame (256 for a single chip,
// 516 for a quad) with the given cell_width (in pixels) accelerates the neighbor
// search over active photons; a rolling time window expires photons that can no
// longer link to any future photon. cell_width is a lookup accelerator only: any
// cell_width at least the linking radius produces the same photon clusters.
// on_photon_cluster receives the member photon indices (into the photons vector,
// ascending) of each cluster as it closes, in the order clusters close; any
// still-open clusters are flushed at end of input in earliest-photon-time order.
void clusterPhotons(
    const std::vector<PhotonEvent>& photons,
    double spatial_link_radius_pixels,
    double max_time_difference_ticks,
    int cell_width,
    int sensor_width,
    const std::function<void(std::vector<std::size_t>&&)>& on_photon_cluster);

}  // namespace hermes_event_reconstructor

#endif
