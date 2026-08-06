#ifndef HERMES_EVENT_RECONSTRUCTOR_RECONSTRUCTION_H
#define HERMES_EVENT_RECONSTRUCTOR_RECONSTRUCTION_H

#include <cstdint>
#include <vector>

#include "event.h"
#include "event_writer.h"
#include "photon_reader.h"
#include "settings.h"

namespace hermes_event_reconstructor {

// Tallies gathered while reconstructing events for one chip, mapping directly
// onto the reconstruction summary counts.
struct EventReconstructionCounts {
    std::uint64_t photons_read = 0;             // photons handed to clustering
    std::uint64_t components_formed = 0;        // photon clusters closed
    std::uint64_t event_count = 0;              // candidate events built
    std::uint64_t single_photon_count = 0;      // events flagged single_photon
    std::uint64_t duration_exceeded_count = 0;  // events flagged duration_exceeded
    std::uint64_t min_photon_count_below = 0;   // events below min_photon_count
};

// Candidate events and optional per-photon membership rows for one chip.
struct EventReconstruction {
    std::vector<CandidateEvent> events;
    std::vector<EventPhotonRow> event_photons;
    EventReconstructionCounts counts;
};

// Groups a chip's photons into candidate events with connected-components
// clustering and builds one event per cluster.
//
// photons must already be sorted by timestamp_canonical (the photon reader
// guarantees this). Clusters close in time order, and each becomes one event
// through buildEvent, so events come out in cluster-close order with event_id
// assigned in that order. The counts tally the components formed, the events
// built, the two quality flags, and how many events fall below
// settings.min_photon_count (recorded only; never dropped). When
// collect_event_photons is true, one event_photons row is emitted per member
// photon, tagged with its event_id, so cluster membership can be written out for
// inspection.
EventReconstruction reconstructEvents(const std::vector<PhotonEvent>& photons,
                                      const ReconParams& settings,
                                      bool collect_event_photons);

}  // namespace hermes_event_reconstructor

#endif
