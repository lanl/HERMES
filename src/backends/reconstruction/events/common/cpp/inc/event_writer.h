#ifndef HERMES_EVENT_RECONSTRUCTOR_EVENT_WRITER_H
#define HERMES_EVENT_RECONSTRUCTOR_EVENT_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

#include "event.h"

namespace hermes_event_reconstructor {

// Schema identity written into every event Parquet file's key-value metadata.
constexpr char kEventCandidatesSchemaName[] =
    "hermes_tpx3_spidr_event_candidates";
constexpr char kEventPhotonsSchemaName[] = "hermes_tpx3_spidr_event_photons";
constexpr char kEventSchemaVersion[] = "1";

// String metadata attached to every event Parquet file so a reader can recover
// how the events were produced without the summary JSON. Mirrors the photon
// stage's PhotonFileMetadata. A whole-sensor run covers every chip at once, so
// the file records the detector layout ("single_chip" or "quad") rather than a
// single chip index.
struct EventFileMetadata {
    std::string raw_file_stem;
    std::string detector_layout;
    double canonical_tick_seconds = 0.0;
    std::string event_algorithm;
    std::string event_settings_json;
    std::string position_rule;      // "arithmetic"
    std::string event_time_estimator;  // "earliest_photon"
    bool save_event_photons = false;
};

// One row of the event_photons file: a member photon tied to its event. The
// x, y, and timestamp_canonical are copied from the source photon so cluster
// membership can be plotted without joining back to the photon file.
struct EventPhotonRow {
    std::uint64_t event_id = 0;
    std::uint64_t photon_id = 0;
    double x = 0.0;
    double y = 0.0;
    double timestamp_canonical = 0.0;
};

// Result of writing one event file: the path written and the row count.
struct EventWriteResult {
    std::string file;
    std::uint64_t row_count = 0;
};

// Writes event_candidates for one input file to output_file_path as a single
// Parquet file with the six documented columns. Appends to errors and returns an
// empty result on failure. Writes nothing when events is empty. When overwrite is
// false, refuses to replace an existing file; when true, replaces it.
EventWriteResult writeEventCandidatesParquet(
    const std::vector<CandidateEvent>& events,
    const std::string& output_file_path,
    const EventFileMetadata& metadata,
    bool overwrite,
    std::vector<std::string>& errors);

// Writes the event_photons file for one input file to output_file_path as a
// single Parquet file. Rows are written in the given order. Appends to errors on
// failure. Writes nothing when rows is empty. When overwrite is false, refuses to
// replace an existing file; when true, replaces it.
EventWriteResult writeEventPhotonsParquet(
    const std::vector<EventPhotonRow>& rows,
    const std::string& output_file_path,
    const EventFileMetadata& metadata,
    bool overwrite,
    std::vector<std::string>& errors);

}  // namespace hermes_event_reconstructor

#endif
