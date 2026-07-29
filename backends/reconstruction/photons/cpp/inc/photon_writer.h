#ifndef HERMES_PHOTON_CLUSTERER_PHOTON_WRITER_H
#define HERMES_PHOTON_CLUSTERER_PHOTON_WRITER_H

#include <cstdint>
#include <string>
#include <vector>

#include "photon.h"
#include "pixel_reader.h"

namespace hermes_photon_clusterer {

// Schema identity written into every photon Parquet file's key-value metadata.
constexpr char kPhotonEventsSchemaName[] = "hermes_tpx3_spidr_photon_events";
constexpr char kPhotonPixelsSchemaName[] = "hermes_tpx3_spidr_photon_pixels";
constexpr char kPhotonSchemaVersion[] = "1";

// String metadata attached to every photon Parquet file so a reader can recover
// how the photons were produced without the summary JSON.
struct PhotonFileMetadata {
    std::string raw_file_stem;
    int chip_index = 0;
    double canonical_tick_seconds = 0.0;
    std::string clustering_algorithm;
    std::string clustering_settings_json;
    std::string position_averaging;
    std::string photon_time_estimator;
    // Correction model name ("inverse", "linear", or "none"), fitted parameters
    // as JSON, and the anchor. When correction_model == "none" the parameter and
    // anchor fields are ignored.
    std::string correction_model;
    std::string correction_parameters_json;
    double high_tot_anchor = 0.0;
    bool save_photon_pixels = false;
};

// One row of the photon_pixels output: a source pixel tied to its photon.
struct PhotonPixelRow {
    std::uint64_t photon_id = 0;
    std::uint64_t pixel_event_id = 0;
    std::uint16_t x = 0;
    std::uint16_t y = 0;
    std::uint16_t tot_raw = 0;
    std::uint64_t timestamp_canonical = 0;
};

// Result of writing one file group: the relative paths written and the row count.
struct PhotonWriteResult {
    std::vector<std::string> files;
    std::uint64_t row_count = 0;
};

// Writes photon_events for one raw stem and chip under photon_output_directory,
// splitting into parts of rows_per_part rows. Files are named
// "<stem>-chip-<chip>-photon-events-part-<00000>.parquet". Photons carry an
// implicit zero-based photon_id equal to their index in the vector. Appends to
// errors and returns an empty result on failure. Writes nothing when photons is
// empty. When overwrite is false, refuses to replace an existing file; when
// true, replaces it.
PhotonWriteResult writePhotonEventsParquet(
    const std::vector<Photon>& photons,
    const std::string& photon_output_directory,
    const PhotonFileMetadata& metadata,
    std::uint64_t rows_per_part,
    bool overwrite,
    std::vector<std::string>& errors);

// Writes photon_pixels for one raw stem and chip. Files are named
// "<stem>-chip-<chip>-photon-pixels-part-<00000>.parquet". Rows are written in
// the given order. Appends to errors on failure. Writes nothing when rows empty.
// When overwrite is false, refuses to replace an existing file; when true,
// replaces it.
PhotonWriteResult writePhotonPixelsParquet(
    const std::vector<PhotonPixelRow>& rows,
    const std::string& photon_output_directory,
    const PhotonFileMetadata& metadata,
    std::uint64_t rows_per_part,
    bool overwrite,
    std::vector<std::string>& errors);

}  // namespace hermes_photon_clusterer

#endif
