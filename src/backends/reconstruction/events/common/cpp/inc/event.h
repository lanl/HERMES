#ifndef HERMES_EVENT_RECONSTRUCTOR_EVENT_H
#define HERMES_EVENT_RECONSTRUCTOR_EVENT_H

#include <cstddef>
#include <cstdint>
#include <vector>

#include "photon_reader.h"

namespace hermes_event_reconstructor {

// Quality-flag bits carried by every candidate event. The clustering stage never
// discards a cluster; these bits let downstream analysis decide how to treat the
// two flagged situations. All other bits are reserved.
enum QualityFlag : std::uint16_t {
    // The event has exactly one member photon. It may be a genuine low-light
    // event, detector background, or a dark count.
    kSinglePhoton = 0x0001,
    // The event duration (latest - earliest member time) is greater than
    // max_event_duration_ticks. Connected components can occasionally chain
    // separate events, so a long duration is suspicious rather than invalid.
    kDurationExceeded = 0x0002,
};

// One candidate event built from a photon cluster. The first six fields are the
// columns written to event_candidates; the remaining fields are diagnostics that
// stay in the reconstruction summary and are not written as event columns in this
// first program.
struct CandidateEvent {
    // Written columns.
    std::uint64_t event_id = 0;             // set by the caller, per chip
    double x = 0.0;                         // arithmetic mean member x
    double y = 0.0;                         // arithmetic mean member y
    double timestamp_canonical = 0.0;       // earliest member time (canonical ticks)
    std::uint64_t photon_count = 0;         // number of member photons
    std::uint16_t quality_flags = 0;        // OR of QualityFlag bits

    // Diagnostics (summary only).
    double latest_time_canonical = 0.0;     // latest member time
    double duration_ticks = 0.0;            // latest - earliest
    double spatial_rms = 0.0;               // RMS distance of members about (x, y)
    double min_x = 0.0;                     // bounding box
    double min_y = 0.0;
    double max_x = 0.0;
    double max_y = 0.0;
};

// Builds one candidate event from the member photons of a closed cluster. members
// holds indices into photons (as delivered by clusterPhotons); it must be
// non-empty. event_id is assigned as given. quality_flags is set from the member
// count and from the event duration relative to max_event_duration_ticks. Position
// is the arithmetic mean of member x and y; the event time is the earliest member
// timestamp. The diagnostics (latest time, duration, spatial RMS about the
// centroid, and the bounding box) are filled in as well.
CandidateEvent buildEvent(const std::vector<PhotonEvent>& photons,
                          const std::vector<std::size_t>& members,
                          std::uint64_t event_id,
                          double max_event_duration_ticks);

}  // namespace hermes_event_reconstructor

#endif
