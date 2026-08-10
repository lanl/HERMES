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

double secondsSince(const Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

void printHelp(const char* program_name) {
    std::cout << "HERMES Photon Clusterer v" << hermes_photon_clusterer::kVersion
              << "\n\n";
    std::cout << "Usage: " << program_name
              << " --input <pixel_file> [--output <photon_file>]"
                 " [--settings <file>] [--overwrite]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <pixel_file>           One pixel_hits Parquet file "
                 "to reconstruct (required)\n";
    std::cout << "  --output <photon_file>         Full path of the photon file "
                 "to write (optional)\n";
    std::cout << "  --settings <file>              JSON file overriding "
                 "individual clustering\n";
    std::cout << "                                 settings (any field omitted "
                 "keeps its default)\n";
    std::cout << "  --overwrite                    Overwrite existing photon and "
                 "summary files\n";
    std::cout << "  -h, --help                     Show this help message\n";
    std::cout << "  -v, --version                  Show version information\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without --output:\n";
    std::cout << "    Prints summary counts only; writes no files.\n\n";
    std::cout << "  With --output:\n";
    std::cout << "    Writes one photon file at the given path and a "
                 "photon_pixels\n";
    std::cout << "    sidecar when enabled. The reconstruction-summary JSON is "
                 "written\n";
    std::cout << "    to a logs/photons/ directory beside the output "
                 "directory.\n";
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
    std::string input_file;
    std::string output_file;
    std::string settings_file;
    bool overwrite = false;
    bool have_input = false;
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
                std::cerr << "Error: --input requires a file path\n";
                return 2;
            }
            input_file = argv[++i];
            have_input = true;
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
                std::cerr << "Error: --output requires a file path\n";
                return 2;
            }
            output_file = argv[++i];
            have_output = true;
            continue;
        }
        std::cerr << "Error: unrecognized argument: " << arg << "\n\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }

    if (!have_input) {
        std::cerr << "Error: --input <pixel_file> is required\n";
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

    // Sidecar photon_pixels and summary paths derive from the output file: same
    // directory, output basename with a suffix. Only used when --output is set.
    std::string pixels_output_file;
    std::string summary_path;
    if (have_output) {
        const fs::path output_path(output_file);
        const fs::path parent = output_path.parent_path();
        const std::string stem = output_path.stem().string();
        // The summary is a log artifact: it goes in a logs/photons/ directory
        // beside the photon output directory (the unpacker writes to
        // logs/unpacker/), while the photon file and its photon_pixels sidecar
        // stay at the output path. Both directories are created up front so the
        // summary is written even when reconstruction produces zero photons (no
        // parquet files).
        const fs::path logs_dir = parent.parent_path() / "logs" / "photons";
        for (const fs::path& directory : {parent, logs_dir}) {
            if (directory.empty()) {
                continue;
            }
            std::error_code ec;
            fs::create_directories(directory, ec);
            if (ec) {
                std::cerr << "Error: cannot create directory "
                          << directory.string() << ": " << ec.message() << "\n";
                return 1;
            }
        }
        pixels_output_file =
            (parent / (stem + "-photon-pixels.parquet")).string();
        summary_path =
            (logs_dir / (stem + "-reconstruction-summary.json")).string();
    }

    const auto total_start = Clock::now();

    // Photon-file metadata; provenance lives here, not in the summary.
    hermes_photon_clusterer::PhotonFileMetadata metadata;
    metadata.raw_file_stem = fs::path(input_file).stem().string();
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

    hermes_photon_clusterer::ReconstructionSummaryContent summary;

    const hermes_photon_clusterer::TimewalkCorrection* correction_ptr =
        has_correction ? &correction : nullptr;

    // Read the one input file into memory in its stored (time-sorted) order.
    std::vector<hermes_photon_clusterer::PixelHit> hits;
    const auto read_start = Clock::now();
    std::vector<std::string> read_errors;
    const bool read_ok = hermes_photon_clusterer::readPixelHits(
        {input_file},
        [&](const hermes_photon_clusterer::PixelHit& hit) {
            hits.push_back(hit);
        },
        read_errors);
    summary.parquet_reading_seconds = secondsSince(read_start);
    if (!read_ok) {
        for (const auto& error : read_errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }

    // Cluster, filter, and build photons for this file.
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
    summary.clustering_and_filtering_seconds = secondsSince(cluster_start);

    summary.pixel_rows_read = result.counts.pixel_rows_read;
    summary.pixel_rows_below_min_tot = result.counts.pixel_rows_below_min_tot;
    summary.components_formed = result.counts.components_formed;
    summary.photon_count = result.counts.photon_count;
    summary.rejected_component_count = result.counts.rejected_component_count;
    summary.rejection_counts = result.counts.rejection_counts;
    summary.saturated_pixel_count = result.counts.saturated_pixel_count;
    summary.bridged_components_count = result.counts.bridged_components_count;

    std::cout << "Reconstructed " << summary.photon_count << " photons from "
              << summary.pixel_rows_read << " pixel rows.\n";

    // Without --output, print the summary counts and write no files.
    if (!have_output) {
        std::cout << "Rejected " << summary.rejected_component_count
                  << " component(s); no files written (no --output).\n";
        return 0;
    }

    // Write the single photon file, plus a photon_pixels sidecar when enabled.
    const auto write_start = Clock::now();
    std::vector<std::string> write_errors;
    hermes_photon_clusterer::writePhotonEventsParquet(
        result.photons, output_file, metadata, overwrite, write_errors);
    if (!write_errors.empty()) {
        for (const auto& error : write_errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }
    if (settings.save_photon_pixels) {
        hermes_photon_clusterer::writePhotonPixelsParquet(
            result.photon_pixels, pixels_output_file, metadata, overwrite,
            write_errors);
        if (!write_errors.empty()) {
            for (const auto& error : write_errors) {
                std::cerr << "Error: " << error << "\n";
            }
            return 1;
        }
    }
    summary.parquet_writing_seconds = secondsSince(write_start);
    summary.total_seconds = secondsSince(total_start);

    try {
        hermes_photon_clusterer::writeReconstructionSummaryJson(
            summary_path, summary, overwrite);
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 1;
    }

    std::cout << "Wrote: " << output_file << "\n";
    std::cout << "Summary: " << summary_path << "\n";
    return 0;
}
