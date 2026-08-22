#include <chrono>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

#include "event_writer.h"
#include "photon_reader.h"
#include "reconstruction.h"
#include "settings.h"
#include "summary_writer.h"
#include "version.h"

namespace {

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

// One canonical tick in seconds: the 25 ns SPIDR coarse period split into the
// 12,288 fine steps the unpacker uses. Written into the event file metadata so
// it matches the unpacker and photon reconstruction.
constexpr double kCanonicalTickSeconds = 25.0e-9 / 12288.0;

double secondsSince(const Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

void printHelp(const char* program_name) {
    std::cout << "HERMES Event Reconstructor v"
              << hermes_event_reconstructor::kVersion << "\n\n";
    std::cout << "Usage: " << program_name
              << " --input <photon_events_file> [--output <event_file>]"
                 " [--settings <file>] [--overwrite]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <photon_events_file>   One photon_events Parquet "
                 "file to reconstruct (required)\n";
    std::cout << "  --output <event_file>          Full path of the "
                 "event_candidates file to write (optional)\n";
    std::cout << "  --settings <file>              JSON file overriding "
                 "individual event\n";
    std::cout << "                                 settings (any field omitted "
                 "keeps its default)\n";
    std::cout << "  --overwrite                    Overwrite existing event and "
                 "summary files\n";
    std::cout << "  -h, --help                     Show this help message\n";
    std::cout << "  -v, --version                  Show version information\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without --output:\n";
    std::cout << "    Prints summary counts only; writes no files.\n\n";
    std::cout << "  With --output:\n";
    std::cout << "    Writes one event_candidates file at the given path. When\n";
    std::cout << "    save_event_photons is set, the event_photons file is "
                 "written to\n";
    std::cout << "    an event_photons/ directory beside the output directory. "
                 "The\n";
    std::cout << "    reconstruction-summary JSON is written to a logs/events/ "
                 "directory\n";
    std::cout << "    beside the output directory.\n";
}

void printVersion() {
    std::cout << "HERMES Event Reconstructor v"
              << hermes_event_reconstructor::kVersion << "\n";
    std::cout << "C++17 connected-components event reconstruction\n";
}

// The raw TPX3 filename stem and chip index carried by a photon file. The photon
// stage names photon files "<raw_file_stem>_chip_<chip>_photon_<part>.parquet";
// event reconstruction reads the raw stem and chip index back out so the event
// file metadata records the true provenance instead of the compound photon-file
// stem. Mirrors the photon stage's parsePixelFileName.
struct PhotonFileName {
    std::string raw_file_stem;
    std::string chip_label;
    std::string part_index;
    bool matched = false;
};

PhotonFileName parsePhotonFileName(const std::string& input_stem) {
    PhotonFileName parsed;
    const std::string chip_marker = "_chip_";
    const std::string photon_marker = "_photon_";
    const auto chip_position = input_stem.find(chip_marker);
    const auto photon_position = input_stem.rfind(photon_marker);
    if (chip_position == std::string::npos ||
        photon_position == std::string::npos ||
        photon_position < chip_position) {
        return parsed;
    }
    parsed.raw_file_stem = input_stem.substr(0, chip_position);
    parsed.chip_label = input_stem.substr(
        chip_position + chip_marker.size(),
        photon_position - (chip_position + chip_marker.size()));
    parsed.part_index =
        input_stem.substr(photon_position + photon_marker.size());
    parsed.matched = !parsed.raw_file_stem.empty() &&
                     !parsed.chip_label.empty() && !parsed.part_index.empty();
    return parsed;
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
        std::cerr << "Error: --input <photon_events_file> is required\n";
        return 2;
    }

    // Start from built-in defaults; a settings file overrides only named fields.
    hermes_event_reconstructor::ReconParams settings;
    try {
        if (settings_file.empty()) {
            hermes_event_reconstructor::validateReconParams(settings);
        } else {
            settings =
                hermes_event_reconstructor::loadReconParams(settings_file);
        }
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 2;
    }

    const int cell_width =
        hermes_event_reconstructor::deriveCellWidth(settings.spatial_cells_per_axis);
    const std::string settings_json =
        hermes_event_reconstructor::clusteringSettingsJson(settings, cell_width);

    // The event_photons and summary paths derive from the output file. The
    // event_photons file goes in its own event_photons/ directory beside the
    // events/ output directory, mirroring how the photon stage writes its
    // pixel_clusters/ file beside photons/. The summary is a log artifact written
    // to a logs/events/ directory beside the output directory (the photon stage
    // writes to logs/photons/). The events/ and logs/events/ directories are
    // created up front so the summary is written even when reconstruction
    // produces zero events; event_photons/ is created only when
    // save_event_photons is set. Only used when --output is set.
    std::string event_photons_file;
    std::string summary_path;
    if (have_output) {
        const fs::path output_path(output_file);
        const fs::path parent = output_path.parent_path();
        const std::string stem = output_path.stem().string();
        const fs::path analysis_dir = parent.parent_path();
        const fs::path logs_dir = analysis_dir / "logs" / "events";
        const fs::path event_photons_dir = analysis_dir / "event_photons";
        std::vector<fs::path> directories = {parent, logs_dir};
        if (settings.save_event_photons) {
            directories.push_back(event_photons_dir);
        }
        for (const fs::path& directory : directories) {
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
        event_photons_file =
            (event_photons_dir / (stem + "-event-photons.parquet")).string();
        summary_path =
            (logs_dir / (stem + "-reconstruction-summary.json")).string();
    }

    const auto total_start = Clock::now();

    // Event-file metadata; provenance lives here, not in the summary. Parse the
    // photon input filename so the metadata records the true raw stem and chip
    // index rather than the compound photon-file stem, matching the photon stage.
    const std::string input_stem = fs::path(input_file).stem().string();
    const PhotonFileName photon_name = parsePhotonFileName(input_stem);
    hermes_event_reconstructor::EventFileMetadata metadata;
    metadata.raw_file_stem =
        photon_name.matched ? photon_name.raw_file_stem : input_stem;
    if (photon_name.matched) {
        try {
            metadata.chip_index = std::stoi(photon_name.chip_label);
        } catch (...) {
            std::cerr << "Error: chip label is not a valid integer: "
                      << photon_name.chip_label << "\n";
            return 2;
        }
    }
    metadata.canonical_tick_seconds = kCanonicalTickSeconds;
    metadata.event_algorithm = "connected_components";
    metadata.event_settings_json = settings_json;
    metadata.position_rule = "arithmetic";
    metadata.event_time_estimator = "earliest_photon";
    metadata.save_event_photons = settings.save_event_photons;

    hermes_event_reconstructor::EventReconstructionSummaryContent summary;
    summary.clustering_algorithm = "connected_components";
    summary.clustering_settings_json = settings_json;
    summary.input_photon_events_files = {input_file};

    // Read the one photon file into memory, sorted by time for clustering.
    std::vector<hermes_event_reconstructor::PhotonEvent> photons;
    const auto read_start = Clock::now();
    std::vector<std::string> read_errors;
    const bool read_ok = hermes_event_reconstructor::readPhotonEvents(
        input_file, photons, read_errors);
    summary.photon_reading_seconds = secondsSince(read_start);
    if (!read_ok) {
        for (const auto& error : read_errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }

    // Group photons into candidate events for this file.
    const auto cluster_start = Clock::now();
    auto result = hermes_event_reconstructor::reconstructEvents(
        photons, settings, settings.save_event_photons);
    summary.clustering_seconds = secondsSince(cluster_start);

    summary.photons_read = result.counts.photons_read;
    summary.components_formed = result.counts.components_formed;
    summary.event_count = result.counts.event_count;
    summary.single_photon_count = result.counts.single_photon_count;
    summary.duration_exceeded_count = result.counts.duration_exceeded_count;
    summary.min_photon_count_below = result.counts.min_photon_count_below;

    std::cout << "Reconstructed " << summary.event_count << " events from "
              << summary.photons_read << " photons.\n";

    // Without --output, print the summary counts and write no files.
    if (!have_output) {
        std::cout << "No files written (no --output).\n";
        return 0;
    }

    // Write the event_candidates file, plus an event_photons file when enabled.
    const auto write_start = Clock::now();
    std::vector<std::string> write_errors;
    const auto candidates_result =
        hermes_event_reconstructor::writeEventCandidatesParquet(
            result.events, output_file, metadata, overwrite, write_errors);
    if (!write_errors.empty()) {
        for (const auto& error : write_errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }
    summary.event_candidates_row_count = candidates_result.row_count;
    if (!candidates_result.file.empty()) {
        summary.event_candidates_files = {candidates_result.file};
    }

    if (settings.save_event_photons) {
        const auto photons_result =
            hermes_event_reconstructor::writeEventPhotonsParquet(
                result.event_photons, event_photons_file, metadata, overwrite,
                write_errors);
        if (!write_errors.empty()) {
            for (const auto& error : write_errors) {
                std::cerr << "Error: " << error << "\n";
            }
            return 1;
        }
        summary.event_photons_row_count = photons_result.row_count;
        if (!photons_result.file.empty()) {
            summary.event_photons_files = {photons_result.file};
        }
    }
    summary.parquet_writing_seconds = secondsSince(write_start);
    summary.total_seconds = secondsSince(total_start);

    try {
        hermes_event_reconstructor::writeEventReconstructionSummaryJson(
            summary_path, summary, overwrite);
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 1;
    }

    std::cout << "Wrote: " << output_file << "\n";
    std::cout << "Summary: " << summary_path << "\n";
    return 0;
}
