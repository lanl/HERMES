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
              << " --input <pixel_file> [--output <analysis_directory>"
                 " --measurement-id <id> --run <run>]"
                 " [--settings <file>] [--overwrite]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <pixel_file>           One pixel_hits Parquet file "
                 "to reconstruct (required)\n";
    std::cout << "  --output <analysis_directory>  Analysis directory the photon "
                 "files are\n";
    std::cout << "                                 written under (optional)\n";
    std::cout << "  --measurement-id <id>          Measurement identifier copied "
                 "into the\n";
    std::cout << "                                 summary JSON (required with "
                 "--output)\n";
    std::cout << "  --run <run>                    Run label copied into the "
                 "summary JSON\n";
    std::cout << "                                 (required with --output)\n";
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
    std::cout << "    Writes the photon table to photons/ and, when enabled, the\n";
    std::cout << "    pixel-to-cluster table to pixel_clusters/. The "
                 "reconstruction\n";
    std::cout << "    summary JSON is written to logs/photon_reconstruction/.\n";
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

// The raw TPX3 filename stem and five-digit part index carried by an unpacked
// pixel file. The unpacker names pixel files
// "<raw_file_stem>_chip_<chip>_pixels_<part>.parquet"; reconstruction reuses the
// raw stem and part index when naming its own photon, pixel-cluster, and summary
// files so every output for one raw file shares a stem.
struct PixelFileName {
    std::string raw_file_stem;
    std::string chip_label;
    std::string part_index;
    bool matched = false;
};

PixelFileName parsePixelFileName(const std::string& input_stem) {
    PixelFileName parsed;
    const std::string chip_marker = "_chip_";
    const std::string pixels_marker = "_pixels_";
    const auto chip_position = input_stem.find(chip_marker);
    const auto pixels_position = input_stem.rfind(pixels_marker);
    if (chip_position == std::string::npos ||
        pixels_position == std::string::npos ||
        pixels_position < chip_position) {
        return parsed;
    }
    parsed.raw_file_stem = input_stem.substr(0, chip_position);
    parsed.chip_label =
        input_stem.substr(chip_position + chip_marker.size(),
                          pixels_position - (chip_position + chip_marker.size()));
    parsed.part_index =
        input_stem.substr(pixels_position + pixels_marker.size());
    parsed.matched =
        !parsed.raw_file_stem.empty() && !parsed.chip_label.empty() &&
        !parsed.part_index.empty();
    return parsed;
}

}  // namespace

int main(const int argc, char* argv[]) {
    std::string input_file;
    std::string analysis_directory;
    std::string settings_file;
    std::string measurement_id;
    std::string run;
    bool overwrite = false;
    bool have_input = false;
    bool have_output = false;
    bool have_measurement_id = false;
    bool have_run = false;

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
                std::cerr << "Error: --output requires a directory path\n";
                return 2;
            }
            analysis_directory = argv[++i];
            have_output = true;
            continue;
        }
        if (arg == "--measurement-id") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --measurement-id requires a value\n";
                return 2;
            }
            measurement_id = argv[++i];
            have_measurement_id = true;
            continue;
        }
        if (arg == "--run") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --run requires a value\n";
                return 2;
            }
            run = argv[++i];
            have_run = true;
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

    if (have_output && (!have_measurement_id || !have_run)) {
        std::cerr << "Error: --measurement-id and --run are required with "
                     "--output\n";
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

    // Every output for one raw file shares its raw filename stem and part index.
    // The photon table goes in photons/, the pixel-to-cluster table in
    // pixel_clusters/, and the summary in logs/photon_reconstruction/, all under
    // the analysis directory. The directories are created up front so the
    // summary is written even when reconstruction produces zero photons.
    const std::string input_stem = fs::path(input_file).stem().string();
    const PixelFileName pixel_name = parsePixelFileName(input_stem);
    std::string photon_output_file;
    std::string pixels_output_file;
    std::string summary_path;
    if (have_output) {
        if (!pixel_name.matched) {
            std::cerr << "Error: input filename does not match "
                         "<stem>_chip_<chip>_pixels_<part>.parquet: "
                      << input_file << "\n";
            return 2;
        }
        const fs::path analysis_path(analysis_directory);
        const fs::path photons_dir = analysis_path / "photons";
        const fs::path clusters_dir = analysis_path / "pixel_clusters";
        const fs::path logs_dir =
            analysis_path / "logs" / "photon_reconstruction";
        std::vector<fs::path> directories = {photons_dir, logs_dir};
        if (settings.save_photon_pixels) {
            directories.push_back(clusters_dir);
        }
        for (const fs::path& directory : directories) {
            std::error_code ec;
            fs::create_directories(directory, ec);
            if (ec) {
                std::cerr << "Error: cannot create directory "
                          << directory.string() << ": " << ec.message() << "\n";
                return 1;
            }
        }
        photon_output_file =
            (photons_dir / (pixel_name.raw_file_stem + "_chip_" +
                            pixel_name.chip_label + "_photon_" +
                            pixel_name.part_index + ".parquet"))
                .string();
        pixels_output_file =
            (clusters_dir / (pixel_name.raw_file_stem + "_chip_" +
                             pixel_name.chip_label + "_pixel_clusters_" +
                             pixel_name.part_index + ".parquet"))
                .string();
        summary_path =
            (logs_dir / (pixel_name.raw_file_stem + "_chip_" +
                         pixel_name.chip_label +
                         "_photon_reconstruction_summary.json"))
                .string();
    }

    const auto total_start = Clock::now();

    // Photon-file metadata; provenance lives here as well as in the summary.
    hermes_photon_clusterer::PhotonFileMetadata metadata;
    metadata.raw_file_stem =
        pixel_name.matched ? pixel_name.raw_file_stem : input_stem;
    if (pixel_name.matched) {
        try {
            metadata.chip_index = std::stoi(pixel_name.chip_label);
        } catch (...) {
            std::cerr << "Error: chip label is not a valid integer: "
                      << pixel_name.chip_label << "\n";
            return 2;
        }
    }
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
    summary.measurement_id = measurement_id;
    summary.run = run;
    summary.clustering_algorithm = "connected_components";
    summary.settings = settings;
    summary.photon_time_estimator = settings.photon_time_estimator;
    summary.has_correction = has_correction;
    if (has_correction) {
        summary.correction = correction;
    }
    summary.input_pixel_data_file = input_file;
    summary.pixel_clusters_requested = settings.save_photon_pixels;

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

    summary.pixels_read = result.counts.pixel_rows_read;
    summary.clusters_formed = result.counts.components_formed;
    summary.total_photons = result.counts.photon_count;
    summary.rejected_clusters = result.counts.rejected_component_count;
    summary.rejection_reasons = result.counts.rejection_counts;
    summary.saturated_pixel_count = result.counts.saturated_pixel_count;
    summary.bridged_components_count = result.counts.bridged_components_count;

    std::cout << "Reconstructed " << summary.total_photons << " photons from "
              << summary.pixels_read << " pixel rows.\n";

    // Without --output, print the summary counts and write no files.
    if (!have_output) {
        std::cout << "Rejected " << summary.rejected_clusters
                  << " cluster(s); no files written (no --output).\n";
        return 0;
    }

    // Write the photon table, plus the pixel-to-cluster table when enabled. The
    // summary records the paths written (empty when a table has no rows) and
    // their row counts.
    const auto write_start = Clock::now();
    std::vector<std::string> write_errors;
    const auto photon_write = hermes_photon_clusterer::writePhotonEventsParquet(
        result.photons, photon_output_file, metadata, overwrite, write_errors);
    if (!write_errors.empty()) {
        for (const auto& error : write_errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }
    summary.photons_file = photon_write.file;
    summary.photons_row_count = photon_write.row_count;
    if (settings.save_photon_pixels) {
        const auto pixels_write =
            hermes_photon_clusterer::writePhotonPixelsParquet(
                result.photon_pixels, pixels_output_file, metadata, overwrite,
                write_errors);
        if (!write_errors.empty()) {
            for (const auto& error : write_errors) {
                std::cerr << "Error: " << error << "\n";
            }
            return 1;
        }
        summary.pixel_clusters_file = pixels_write.file;
        summary.pixel_clusters_row_count = pixels_write.row_count;
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

    std::cout << "Wrote: " << photon_output_file << "\n";
    std::cout << "Summary: " << summary_path << "\n";
    return 0;
}
