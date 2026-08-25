#include "reconstruction.h"

#include "clustering.h"

namespace hermes_event_reconstructor {

EventReconstruction reconstructEvents(const std::vector<PhotonEvent>& photons,
                                      const ReconParams& settings,
                                      int sensor_width,
                                      bool collect_event_photons) {
    EventReconstruction result;
    result.counts.photons_read = photons.size();

    const int cell_width =
        deriveCellWidth(settings.spatial_cells_per_axis, sensor_width);

    // Each closed photon cluster becomes one candidate event. event_id is the
    // event's index in the events vector, so it counts up in cluster-close order.
    auto on_photon_cluster = [&](std::vector<std::size_t>&& members) {
        ++result.counts.components_formed;

        const std::uint64_t event_id = result.events.size();
        CandidateEvent event = buildEvent(photons, members, event_id,
                                          settings.max_event_duration_ticks);
        ++result.counts.event_count;

        if (event.quality_flags & kSinglePhoton) {
            ++result.counts.single_photon_count;
        }
        if (event.quality_flags & kDurationExceeded) {
            ++result.counts.duration_exceeded_count;
        }
        if (event.photon_count < settings.min_photon_count) {
            ++result.counts.min_photon_count_below;
        }

        if (collect_event_photons) {
            for (const std::size_t member : members) {
                const PhotonEvent& photon = photons[member];
                EventPhotonRow row;
                row.event_id = event_id;
                row.photon_id = photon.photon_id;
                row.x = photon.x;
                row.y = photon.y;
                row.timestamp_canonical = photon.timestamp_canonical;
                result.event_photons.push_back(row);
            }
        }

        result.events.push_back(event);
    };

    clusterPhotons(photons, settings.spatial_link_radius_pixels,
                   settings.max_time_difference_ticks, cell_width, sensor_width,
                   on_photon_cluster);

    return result;
}

}  // namespace hermes_event_reconstructor
