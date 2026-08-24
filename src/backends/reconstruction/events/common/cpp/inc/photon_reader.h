#ifndef HERMES_EVENT_RECONSTRUCTOR_PHOTON_READER_H
#define HERMES_EVENT_RECONSTRUCTOR_PHOTON_READER_H

#include <cstdint>
#include <string>
#include <vector>

namespace hermes_event_reconstructor {

// One photon_events row, carrying only the columns clustering needs. The photon
// file also stores tot and quality_flags, which event reconstruction ignores.
struct PhotonEvent {
    std::uint64_t photon_id = 0;
    double x = 0.0;
    double y = 0.0;
    double timestamp_canonical = 0.0;
};

// Reads all photon_events rows from one Parquet file into out_rows, then sorts
// them by timestamp_canonical, breaking ties by photon_id. Photon files are
// written in reconstruction order, which is close to but not guaranteed to be
// strictly increasing in time, so the sort makes the stream monotonic for the
// clustering stage. Returns false and appends to errors on a read failure;
// out_rows is left cleared in that case.
bool readPhotonEvents(const std::string& file,
                      std::vector<PhotonEvent>& out_rows,
                      std::vector<std::string>& errors);

// Reads the detector_layout value from one photon file's key-value metadata,
// which photon reconstruction wrote to record the shared sensor coordinate
// frame ("single_chip" or "quad"). The event stage uses it to size its grid.
// Returns false and appends to errors when the file cannot be opened or the
// detector_layout key is absent; out_layout is left cleared in that case.
bool readPhotonFileLayout(const std::string& file,
                          std::string& out_layout,
                          std::vector<std::string>& errors);

// Sorts photons in place by timestamp_canonical, breaking ties by photon_id.
// A whole-sensor run pools every chip's photons into one vector; this puts the
// pool into the monotonic time order the clustering stage expects.
void sortPhotonEventsByTime(std::vector<PhotonEvent>& photons);

}  // namespace hermes_event_reconstructor

#endif
