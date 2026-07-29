#include <chrono>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "clusterer.h"
#include "photon_writer.h"
#include "pixel_reader.h"
#include "reconstruction.h"
#include "settings.h"
#include "summary_writer.h"
#include "timewalk.h"

namespace {

namespace fs = std::filesystem;
using json = nlohmann::ordered_json;
using Clock = std::chrono::steady_clock;

// One canonical tick in seconds: the 25 ns SPIDR coarse period split into the
// 12,288 fine steps the unpacker uses. Written into the photon file metadata.
constexpr double kCanonicalTickSeconds = 25.0e-9 / 12288.0;

// Photon rows per Parquet part file.
constexpr std::uint64_t kRowsPerPart = 1'000'000;

double secondsSince(const Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

void printHelp(const char* program_name) {
    std::cout << "HERMES Photon Clusterer v" << hermes_photon_clusterer::kVersion
              << "\n\n";
    std::cout << "Usage: " << program_name
              << " --input <analysis_directory> --base-file-name <name>"
                 " [--settings <file>] [--output <analysis_directory>]"
                 " [--overwrite]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <analysis_directory>   Directory holding pixelHits/ "
                 "to read (required)\n";
    std::cout << "  --base-file-name <name>        Base name of the raw file "
                 "selecting the\n";
    std::cout << "                                 pixel_data files to read "
                 "(required)\n";
    std::cout << "  --settings <file>              JSON file overriding "
                 "individual clustering\n";
    std::cout << "                                 settings (any field omitted "
                 "keeps its default)\n";
    std::cout << "  --output <analysis_directory>  Directory to write photons/ "
                 "and logs/ (optional)\n";
    std::cout << "  --overwrite                    Overwrite existing photon and "
                 "summary files\n";
    std::cout << "  -h, --help                     Show this help message\n";
    std::cout << "  -v, --version                  Show version information\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without --output:\n";
    std::cout << "    Prints summary counts only; writes no files.\n\n";
    std::cout << "  With --output:\n";
    std::cout << "    Writes photons/ and logs/ under the output directory.\n";
}

void printVersion() {
    std::cout << "HERMES Photon Clusterer v" << hermes_photon_clusterer::kVersion
              << "\n";
    std::cout << "C++17 connected-components photon reconstruction\n";
}

// Serializes the clustering settings to the JSON object stored verbatim in the
// photon file metadata.
json settingsToJson(const hermes_photon_clusterer::ClusteringSettings& s) {
    json j;
    j["max_time_spread_ticks"] = s.max_time_spread_ticks;
    j["min_cluster_size"] = s.min_cluster_size;
    j["max_cluster_size"] = s.max_cluster_size;
    j["min_pixel_tot_raw"] = s.min_pixel_tot_raw;
    j["min_cluster_tot_raw"] = s.min_cluster_tot_raw;
    j["max_cluster_tot_raw"] = s.max_cluster_tot_raw;
    j["max_aspect_ratio"] = s.max_aspect_ratio;
    j["min_filled_fraction"] = s.min_filled_fraction;
    j["adjacency"] = s.adjacency;
    j["position_averaging"] = s.position_averaging;
    j["photon_time_estimator"] = s.photon_time_estimator;
    j["timewalk_calibration_file"] =
        s.timewalk_calibration_file.empty()
            ? json(nullptr)
            : json(s.timewalk_calibration_file);
    j["save_photon_pixels"] = s.save_photon_pixels;
    return j;
}

// Copies the clustering settings into the summary's settings block.
hermes_photon_clusterer::SummaryClusteringSettings summarySettings(
    const hermes_photon_clusterer::ClusteringSettings& s) {
    hermes_photon_clusterer::SummaryClusteringSettings out;
    out.max_time_spread_ticks = s.max_time_spread_ticks;
    out.min_cluster_size = s.min_cluster_size;
    out.max_cluster_size = s.max_cluster_size;
    out.min_pixel_tot_raw = s.min_pixel_tot_raw;
    out.min_cluster_tot_raw = s.min_cluster_tot_raw;
    out.max_cluster_tot_raw = s.max_cluster_tot_raw;
    out.max_aspect_ratio = s.max_aspect_ratio;
    out.min_filled_fraction = s.min_filled_fraction;
    out.adjacency = s.adjacency;
    out.position_averaging = s.position_averaging;
    out.photon_time_estimator = s.photon_time_estimator;
    out.timewalk_calibration_file = s.timewalk_calibration_file;
    out.save_photon_pixels = s.save_photon_pixels;
    return out;
}

// Model name written into metadata and the summary.
std::string correctionModelName(
    const hermes_photon_clusterer::TimewalkCorrection& c) {
    return c.model == hermes_photon_clusterer::TimewalkCorrection::Model::kInverse
               ? "inverse"
               : "linear";
}

// Fitted parameters as (name, value) pairs for the correction model.
std::vector<std::pair<std::string, double>> correctionParameters(
    const hermes_photon_clusterer::TimewalkCorrection& c) {
    if (c.model ==
        hermes_photon_clusterer::TimewalkCorrection::Model::kInverse) {
        return {{"a", c.a}, {"b", c.b}};
    }
    return {{"m", c.m}};
}

}  // namespace

int main(const int argc, char* argv[]) {
    std::string input_dir;
    std::string base_file_name;
    std::string settings_file;
    std::string output_dir;
    bool overwrite = false;
    bool have_input = false;
    bool have_base_name = false;
    bool have_output = false;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "-h" || arg == "--help") {
            printHelp(argv[0]);
            return 0;
        }
        if (arg == "-v" || arg == "--version") {
            printVersion();
            return 0;
        }
        if (arg == "--overwrite") {
            overwrite = true;
            continue;
        }
        if (arg == "--input") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --input requires a directory path\n";
                return 2;
            }
            input_dir = argv[++i];
            have_input = true;
            continue;
        }
        if (arg == "--base-file-name") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --base-file-name requires a name\n";
                return 2;
            }
            base_file_name = argv[++i];
            have_base_name = true;
            continue;
        }
        if (arg == "--settings") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --settings requires a file path\n";
                return 2;
            }
            settings_file = argv[++i];
            continue;
        }
        if (arg == "--output") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --output requires a directory path\n";
                return 2;
            }
            output_dir = argv[++i];
            have_output = true;
            continue;
        }
        std::cerr << "Error: unrecognized argument: " << arg << "\n\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }

    if (!have_input) {
        std::cerr << "Error: --input <analysis_directory> is required\n";
        return 2;
    }
    if (!have_base_name) {
        std::cerr << "Error: --base-file-name <name> is required\n";
        return 2;
    }

    // Start from built-in defaults; a settings file overrides only named fields.
    hermes_photon_clusterer::ClusteringSettings settings;
    try {
        if (settings_file.empty()) {
            hermes_photon_clusterer::validateClusteringSettings(settings);
        } else {
            settings = hermes_photon_clusterer::loadClusteringSettings(
                settings_file);
        }
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 2;
    }

    // Load the time-walk correction now so a malformed calibration fails before
    // any output is written. An empty path means the uncorrected leading edge.
    bool has_correction = false;
    hermes_photon_clusterer::TimewalkCorrection correction;
    if (!settings.timewalk_calibration_file.empty()) {
        try {
            correction = hermes_photon_clusterer::loadTimewalkCorrection(
                settings.timewalk_calibration_file);
            has_correction = true;
        } catch (const std::exception& error) {
            std::cerr << "Error: " << error.what() << "\n";
            return 2;
        }
    }

    const fs::path input_path(input_dir);
    const std::string pixel_hits_dir = (input_path / "pixelHits").string();

    // Output paths are only used when --output is supplied; otherwise the run
    // prints summary counts and writes nothing.
    std::string photons_dir;
    std::string logs_dir;
    std::string summary_path;
    if (have_output) {
        const fs::path output_path(output_dir);
        photons_dir = (output_path / "photons").string();
        logs_dir = (output_path / "logs").string();
        summary_path =
            (fs::path(logs_dir) /
             (base_file_name + "-reconstruction-summary.json"))
                .string();
    }

    const auto total_start = Clock::now();

    // Discover the pixel_data files for this base name, grouped and ordered per
    // chip.
    auto groups = hermes_photon_clusterer::discoverPixelFiles(pixel_hits_dir,
                                                              base_file_name);
    if (!groups.errors.empty()) {
        for (const auto& error : groups.errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }

    // Shared photon-file metadata; chip_index is filled in per chip.
    hermes_photon_clusterer::PhotonFileMetadata metadata;
    metadata.raw_file_stem = base_file_name;
    metadata.canonical_tick_seconds = kCanonicalTickSeconds;
    metadata.clustering_algorithm = "connected_components";
    metadata.clustering_settings_json = settingsToJson(settings).dump();
    metadata.position_averaging = settings.position_averaging;
    metadata.photon_time_estimator = settings.photon_time_estimator;
    metadata.correction_model =
        has_correction ? correctionModelName(correction) : "none";
    if (has_correction) {
        json params;
        for (const auto& [name, value] : correctionParameters(correction)) {
            params[name] = value;
        }
        metadata.correction_parameters_json = params.dump();
        metadata.high_tot_anchor = correction.high_tot_anchor;
    }
    metadata.save_photon_pixels = settings.save_photon_pixels;

    // Accumulate the whole-stem summary across all chips.
    hermes_photon_clusterer::ReconstructionSummaryContent summary;
    summary.algorithm = "connected_components";
    summary.settings = summarySettings(settings);
    summary.photon_timing.estimator = settings.photon_time_estimator;
    summary.photon_timing.correction_model =
        has_correction ? correctionModelName(correction) : "none";
    if (has_correction) {
        summary.photon_timing.calibration_file =
            settings.timewalk_calibration_file;
        summary.photon_timing.parameters = correctionParameters(correction);
        summary.photon_timing.has_high_tot_anchor = true;
        summary.photon_timing.high_tot_anchor = correction.high_tot_anchor;
    }
    summary.photon_pixels_requested = settings.save_photon_pixels;

    double reading_seconds = 0.0;
    double clustering_seconds = 0.0;
    double writing_seconds = 0.0;

    const hermes_photon_clusterer::TimewalkCorrection* correction_ptr =
        has_correction ? &correction : nullptr;

    // Reconstruct each chip independently and accumulate counts and output.
    for (const auto& [chip, files] : groups.files_by_chip) {
        // Record the input files relative to the input directory.
        for (const auto& file : files) {
            summary.input_pixel_data_files.push_back(
                fs::relative(file, input_path).string());
        }

        // Read the chip's ordered pixel_data into memory in timestamp order.
        std::vector<hermes_photon_clusterer::PixelHit> hits;
        const auto read_start = Clock::now();
        std::vector<std::string> read_errors;
        const bool read_ok = hermes_photon_clusterer::readPixelHits(
            files,
            [&](const hermes_photon_clusterer::PixelHit& hit) {
                hits.push_back(hit);
            },
            read_errors);
        reading_seconds += secondsSince(read_start);
        if (!read_ok) {
            for (const auto& error : read_errors) {
                std::cerr << "Error: " << error << "\n";
            }
            return 1;
        }

        // Cluster, filter, and build photons for this chip.
        std::size_t cursor = 0;
        auto next_hit = [&](hermes_photon_clusterer::PixelHit& out) {
            if (cursor >= hits.size()) {
                return false;
            }
            out = hits[cursor++];
            return true;
        };
        const auto cluster_start = Clock::now();
        auto result = hermes_photon_clusterer::reconstructPhotons(
            next_hit, settings, correction_ptr, settings.save_photon_pixels);
        clustering_seconds += secondsSince(cluster_start);

        // Accumulate counts.
        summary.pixel_rows_read += result.counts.pixel_rows_read;
        summary.pixel_rows_below_min_tot +=
            result.counts.pixel_rows_below_min_tot;
        summary.components_formed += result.counts.components_formed;
        summary.photon_count += result.counts.photon_count;
        summary.rejected_component_count +=
            result.counts.rejected_component_count;
        summary.rejection_counts.below_min_cluster_size +=
            result.counts.rejection_counts.below_min_cluster_size;
        summary.rejection_counts.above_max_cluster_size +=
            result.counts.rejection_counts.above_max_cluster_size;
        summary.rejection_counts.below_min_cluster_tot +=
            result.counts.rejection_counts.below_min_cluster_tot;
        summary.rejection_counts.above_max_cluster_tot +=
            result.counts.rejection_counts.above_max_cluster_tot;
        summary.rejection_counts.above_max_aspect_ratio +=
            result.counts.rejection_counts.above_max_aspect_ratio;
        summary.rejection_counts.below_min_filled_fraction +=
            result.counts.rejection_counts.below_min_filled_fraction;
        summary.saturated_pixel_count += result.counts.saturated_pixel_count;
        summary.bridged_components_count +=
            result.counts.bridged_components_count;

        // Write this chip's photon output only when --output was supplied.
        if (!have_output) {
            continue;
        }
        metadata.chip_index = chip;
        const auto write_start = Clock::now();
        std::vector<std::string> write_errors;
        auto events_result = hermes_photon_clusterer::writePhotonEventsParquet(
            result.photons, photons_dir, metadata, kRowsPerPart, overwrite,
            write_errors);
        if (!write_errors.empty()) {
            for (const auto& error : write_errors) {
                std::cerr << "Error: " << error << "\n";
            }
            return 1;
        }
        summary.photon_events_row_count += events_result.row_count;
        for (const auto& file : events_result.files) {
            summary.photon_events_files.push_back("photons/" + file);
        }

        if (settings.save_photon_pixels) {
            auto pixels_result =
                hermes_photon_clusterer::writePhotonPixelsParquet(
                    result.photon_pixels, photons_dir, metadata, kRowsPerPart,
                    overwrite, write_errors);
            if (!write_errors.empty()) {
                for (const auto& error : write_errors) {
                    std::cerr << "Error: " << error << "\n";
                }
                return 1;
            }
            summary.photon_pixels_row_count += pixels_result.row_count;
            for (const auto& file : pixels_result.files) {
                summary.photon_pixels_files.push_back("photons/" + file);
            }
        }
        writing_seconds += secondsSince(write_start);
    }

    summary.parquet_reading_seconds = reading_seconds;
    summary.clustering_and_filtering_seconds = clustering_seconds;
    summary.parquet_writing_seconds = writing_seconds;
    summary.total_seconds = secondsSince(total_start);

    std::cout << "Reconstructed " << summary.photon_count << " photons from "
              << summary.pixel_rows_read << " pixel rows across "
              << groups.files_by_chip.size() << " chip(s).\n";

    // Without --output, print the summary counts and write no files.
    if (!have_output) {
        std::cout << "Rejected " << summary.rejected_component_count
                  << " component(s); no files written (no --output).\n";
        return 0;
    }

    // Write the whole-base-name reconstruction summary under logs/.
    std::error_code ec;
    fs::create_directories(logs_dir, ec);
    if (ec) {
        std::cerr << "Error: failed to create logs directory " << logs_dir
                  << ": " << ec.message() << "\n";
        return 1;
    }
    try {
        hermes_photon_clusterer::writeReconstructionSummaryJson(
            summary_path, summary, overwrite);
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 1;
    }

    std::cout << "Summary: " << summary_path << "\n";
    return 0;
}
