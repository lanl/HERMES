#include "event.h"

#include <cmath>

namespace hermes_event_reconstructor {

CandidateEvent buildEvent(const std::vector<PhotonEvent>& photons,
                          const std::vector<std::size_t>& members,
                          const std::uint64_t event_id,
                          const double max_event_duration_ticks) {
    CandidateEvent event;
    event.event_id = event_id;
    event.photon_count = members.size();

    // First pass: centroid, earliest/latest time, and bounding box.
    const PhotonEvent& first = photons[members[0]];
    double sum_x = 0.0;
    double sum_y = 0.0;
    event.timestamp_canonical = first.timestamp_canonical;
    event.latest_time_canonical = first.timestamp_canonical;
    event.min_x = first.x;
    event.max_x = first.x;
    event.min_y = first.y;
    event.max_y = first.y;
    for (const std::size_t index : members) {
        const PhotonEvent& p = photons[index];
        sum_x += p.x;
        sum_y += p.y;
        if (p.timestamp_canonical < event.timestamp_canonical)
            event.timestamp_canonical = p.timestamp_canonical;
        if (p.timestamp_canonical > event.latest_time_canonical)
            event.latest_time_canonical = p.timestamp_canonical;
        if (p.x < event.min_x) event.min_x = p.x;
        if (p.x > event.max_x) event.max_x = p.x;
        if (p.y < event.min_y) event.min_y = p.y;
        if (p.y > event.max_y) event.max_y = p.y;
    }
    const double count = static_cast<double>(members.size());
    event.x = sum_x / count;
    event.y = sum_y / count;
    event.duration_ticks = event.latest_time_canonical - event.timestamp_canonical;

    // Second pass: RMS distance of members about the centroid.
    double sum_sq = 0.0;
    for (const std::size_t index : members) {
        const PhotonEvent& p = photons[index];
        const double dx = p.x - event.x;
        const double dy = p.y - event.y;
        sum_sq += dx * dx + dy * dy;
    }
    event.spatial_rms = std::sqrt(sum_sq / count);

    // Flags: never discard, only mark.
    if (members.size() == 1) event.quality_flags |= kSinglePhoton;
    if (event.duration_ticks > max_event_duration_ticks)
        event.quality_flags |= kDurationExceeded;

    return event;
}

}  // namespace hermes_event_reconstructor
