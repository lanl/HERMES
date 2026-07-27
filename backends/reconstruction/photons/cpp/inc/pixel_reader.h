#ifndef HERMES_PHOTON_CLUSTERER_PIXEL_READER_H
#define HERMES_PHOTON_CLUSTERER_PIXEL_READER_H

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

namespace hermes_photon_clusterer {

// One pixel-data row, carrying only the columns reconstruction needs. The
// unpacker also writes chunk_index and packet_index, which clustering ignores.
struct PixelHit {
    std::uint16_t x = 0;
    std::uint16_t y = 0;
    std::uint16_t tot_raw = 0;
    std::uint64_t timestamp_canonical = 0;
    // Zero-based row number within the chip's sorted input parts, used to
    // reference the source pixel in photon_pixels output.
    std::uint64_t pixel_event_id = 0;
};

// Pixel-data Parquet files for one raw stem, grouped by chip index and ordered
// by part number. The unpacker writes each chip's parts in timestamp order and
// numbers them contiguously from zero, so reading parts in order yields a
// time-sorted stream per chip.
struct PixelFileGroups {
    std::map<int, std::vector<std::string>> files_by_chip;
    std::vector<std::string> errors;
};

// Discover pixel_data files named "<stem>-chip-<chip>-part-<00000>.parquet" in
// pixel_data_directory for the given raw stem. Reports an error when a chip's
// part numbers are not contiguous from zero.
PixelFileGroups discoverPixelFiles(const std::string& pixel_data_directory,
                                   const std::string& raw_file_stem);

// Stream the pixel_data rows of the ordered files, invoking on_hit for each row
// in file/part order. Returns false and appends to errors on a read failure.
bool readPixelHits(const std::vector<std::string>& files,
                   const std::function<void(const PixelHit&)>& on_hit,
                   std::vector<std::string>& errors);

// Same as readPixelHits, but drops rows whose tot_raw is below min_pixel_tot_raw
// before invoking on_hit. This removes thermal and sensor noise pixels as they
// are read, before clustering. rejected_count is incremented per dropped row.
bool readPixelHitsFiltered(const std::vector<std::string>& files,
                           std::uint16_t min_pixel_tot_raw,
                           const std::function<void(const PixelHit&)>& on_hit,
                           std::uint64_t& rejected_count,
                           std::vector<std::string>& errors);

}  // namespace hermes_photon_clusterer

#endif
