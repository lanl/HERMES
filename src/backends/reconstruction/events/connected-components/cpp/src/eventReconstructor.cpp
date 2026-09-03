#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>

#include "event_writer.h"
#include "photon_reader.h"
#include "reconstruction.h"
#include "sensor_layout.h"
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
              << " --input <analysis_directory> --raw-file-stem <stem>"
                 " [--settings <file>] [--overwrite]\n";
    std::cout << "       " << program_name
              << " --input <analysis_directory> --input-list <file>"
                 " [--settings <file>] [--overwrite]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <analysis_directory>   Analysis directory holding "
                 "the photons/ subdirectory (required)\n";
    std::cout << "  --raw-file-stem <stem>         Raw TPX3 filename stem whose "
                 "photon files to reconstruct\n";
    std::cout << "  --input-list <file>            Reconstruct every photon file "
                 "listed in <file> (one path\n";
    std::cout << "                                 per line), grouped by raw "
                 "stem, in one process\n";
    std::cout << "  --settings <file>              JSON file overriding "
                 "individual event\n";
    std::cout << "                                 settings (any field omitted "
                 "keeps its default)\n";
    std::cout << "  --overwrite                    Overwrite existing event and "
                 "summary files\n";
    std::cout << "  -h, --help                     Show this help message\n";
    std::cout << "  -v, --version                  Show version information\n\n";
    std::cout << "Output:\n";
    std::cout << "  Gathers every photons/<stem>_chip_<chip>_photon_<part>"
                 ".parquet file for the\n";
    std::cout << "  raw stem and clusters them together in the shared sensor "
                 "frame, writing one\n";
    std::cout << "  events/<stem>_event_candidates.parquet, an "
                 "event_photons/<stem>_event_photons.parquet\n";
    std::cout << "  when save_event_photons is set, and a "
                 "logs/event_reconstruction/<stem>_event_reconstruction_summary"
                 ".json,\n";
    std::cout << "  all under the analysis directory.\n";
}

void printVersion() {
    std::cout << "HERMES Event Reconstructor v"
              << hermes_event_reconstructor::kVersion << "\n";
    std::cout << "C++17 connected-components event reconstruction\n";
}

// Gathers every photons/<stem>_chip_<chip>_photon_<part>.parquet file for one
// raw stem, sorted by filename so parts are read in a stable order. The
// "<stem>_chip_" prefix and "_photon_" marker match the photon stage's naming
// and keep stems that are prefixes of each other from picking up one another's
// files.
std::vector<std::string> gatherPhotonFiles(const fs::path& photons_dir,
                                           const std::string& raw_file_stem) {
    std::vector<std::string> files;
    std::error_code ec;
    if (!fs::is_directory(photons_dir, ec)) {
        return files;
    }
    const std::string prefix = raw_file_stem + "_chip_";
    for (const auto& entry : fs::directory_iterator(photons_dir, ec)) {
        if (!entry.is_regular_file()) {
            continue;
        }
        const std::string name = entry.path().filename().string();
        if (name.rfind(prefix, 0) != 0) {
            continue;
        }
        if (name.find("_photon_") == std::string::npos) {
            continue;
        }
        if (entry.path().extension() != ".parquet") {
            continue;
        }
        files.push_back(entry.path().string());
    }
    std::sort(files.begin(), files.end());
    return files;
}

// Returns the raw TPX3 filename stem a photon file belongs to, or an empty
// string when the name does not match <stem>_chip_<chip>_photon_<part>.parquet.
// This is the inverse of the "<stem>_chip_" prefix gatherPhotonFiles builds and
// matches the Python side's _parse_photon_file_name, so batch mode can group
// listed files by stem without scanning the photons/ directory. Parsing the
// exact stem (the whole token before "_chip_") means a stem that is a prefix of
// another can never pick up the other's files.
std::string stemForPhotonFile(const std::string& file_path) {
    const std::string name = fs::path(file_path).filename().string();
    const std::string chip_marker = "_chip_";
    const std::string photon_marker = "_photon_";
    const auto chip_position = name.find(chip_marker);
    const auto photon_position = name.rfind(photon_marker);
    if (chip_position == std::string::npos ||
        photon_position == std::string::npos ||
        photon_position < chip_position) {
        return {};
    }
    if (fs::path(name).extension() != ".parquet") {
        return {};
    }
    return name.substr(0, chip_position);
}

// Runs the whole per-stem reconstruction for one raw stem's photon files: read
// the shared sensor layout, size and validate the grid, pool and sort the
// photons, cluster them, and write the events, optional event_photons, and
// summary files under the analysis directory. Returns 0 on success and a
// non-zero code on failure (2 for a settings/grid problem, 1 otherwise) — the
// same codes the single-stem run returns.
int reconstructOneStem(const fs::path& analysis_path,
                       const std::string& raw_file_stem,
                       const std::vector<std::string>& photon_files,
                       const hermes_event_reconstructor::ReconParams& settings,
                       const bool overwrite) {
    if (photon_files.empty()) {
        std::cerr << "Error: no photon files found for raw file stem '"
                  << raw_file_stem << "'\n";
        return 1;
    }

    const auto total_start = Clock::now();

    // Every gathered photon file was written in the same shared sensor frame, so
    // read the layout from the first one and size the grid over that sensor.
    std::string detector_layout;
    std::vector<std::string> layout_errors;
    if (!hermes_event_reconstructor::readPhotonFileLayout(
            photon_files.front(), detector_layout, layout_errors)) {
        for (const auto& error : layout_errors) {
            std::cerr << "Error: " << error << "\n";
        }
        return 1;
    }

    int sensor_width = 0;
    try {
        sensor_width = hermes_event_reconstructor::sensorWidth(detector_layout);
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 1;
    }
    try {
        hermes_event_reconstructor::validateGridForSensor(settings,
                                                          sensor_width);
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << "\n";
        return 2;
    }

    const int cell_width = hermes_event_reconstructor::deriveCellWidth(
        settings.spatial_cells_per_axis, sensor_width);
    const std::string settings_json =
        hermes_event_reconstructor::clusteringSettingsJson(settings, cell_width);

    // Output layout under the analysis directory: events/ and
    // logs/event_reconstruction/ are created up front so a zero-event run still
    // writes a summary; event_photons/ is created only when save_event_photons
    // is set.
    const fs::path events_dir = analysis_path / "events";
    const fs::path event_photons_dir = analysis_path / "event_photons";
    const fs::path logs_dir =
        analysis_path / "logs" / "event_reconstruction";
    std::vector<fs::path> directories = {events_dir, logs_dir};
    if (settings.save_event_photons) {
        directories.push_back(event_photons_dir);
    }
    for (const fs::path& directory : directories) {
        std::error_code ec;
        fs::create_directories(directory, ec);
        if (ec) {
            std::cerr << "Error: cannot create directory " << directory.string()
                      << ": " << ec.message() << "\n";
            return 1;
        }
    }
    const std::string candidates_file =
        (events_dir / (raw_file_stem + "_event_candidates.parquet")).string();
    const std::string event_photons_file =
        (event_photons_dir / (raw_file_stem + "_event_photons.parquet"))
            .string();
    const std::string summary_path =
        (logs_dir / (raw_file_stem + "_event_reconstruction_summary.json"))
            .string();

    // Event-file metadata; provenance lives here, not in the summary. The whole
    // sensor is covered at once, so the metadata records the detector layout
    // rather than a single chip index.
    hermes_event_reconstructor::EventFileMetadata metadata;
    metadata.raw_file_stem = raw_file_stem;
    metadata.detector_layout = detector_layout;
    metadata.canonical_tick_seconds = kCanonicalTickSeconds;
    metadata.event_algorithm = "connected_components";
    metadata.event_settings_json = settings_json;
    metadata.position_rule = "arithmetic";
    metadata.event_time_estimator = "earliest_photon";
    metadata.save_event_photons = settings.save_event_photons;

    hermes_event_reconstructor::EventReconstructionSummaryContent summary;
    summary.clustering_algorithm = "connected_components";
    summary.clustering_settings_json = settings_json;
    summary.input_photon_events_files = photon_files;

    // Pool every chip's photons into one vector, then sort the pool by time so
    // clustering sees a single monotonic stream across the whole sensor.
    std::vector<hermes_event_reconstructor::PhotonEvent> photons;
    const auto read_start = Clock::now();
    for (const std::string& photon_file : photon_files) {
        std::vector<hermes_event_reconstructor::PhotonEvent> file_photons;
        std::vector<std::string> read_errors;
        if (!hermes_event_reconstructor::readPhotonEvents(
                photon_file, file_photons, read_errors)) {
            for (const auto& error : read_errors) {
                std::cerr << "Error: " << error << "\n";
            }
            return 1;
        }
        photons.insert(photons.end(), file_photons.begin(), file_photons.end());
    }
    hermes_event_reconstructor::sortPhotonEventsByTime(photons);
    summary.photon_reading_seconds = secondsSince(read_start);

    // Group the whole sensor's photons into candidate events.
    const auto cluster_start = Clock::now();
    auto result = hermes_event_reconstructor::reconstructEvents(
        photons, settings, sensor_width, settings.save_event_photons);
    summary.clustering_seconds = secondsSince(cluster_start);

    summary.photons_read = result.counts.photons_read;
    summary.components_formed = result.counts.components_formed;
    summary.event_count = result.counts.event_count;
    summary.single_photon_count = result.counts.single_photon_count;
    summary.duration_exceeded_count = result.counts.duration_exceeded_count;
    summary.min_photon_count_below = result.counts.min_photon_count_below;

    std::cout << "Reconstructed " << summary.event_count << " events from "
              << summary.photons_read << " photons across "
              << photon_files.size() << " photon file(s).\n";

    // Write the event_candidates file, plus an event_photons file when enabled.
    const auto write_start = Clock::now();
    std::vector<std::string> write_errors;
    const auto candidates_result =
        hermes_event_reconstructor::writeEventCandidatesParquet(
            result.events, candidates_file, metadata, overwrite, write_errors);
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

    if (!summary.event_candidates_files.empty()) {
        std::cout << "Wrote: " << candidates_file << "\n";
    } else {
        std::cout << "Wrote no event_candidates file (zero events).\n";
    }
    std::cout << "Summary: " << summary_path << "\n";
    return 0;
}

// Reconstructs every photon file listed in list_path (one path per line) in a
// single process, so the one-time cost of loading Arrow/Parquet is paid once for
// the whole list instead of once per stem. Paths are grouped by raw stem so each
// stem is reconstructed from exactly its own files, without scanning the
// photons/ directory. A stem that fails is logged and skipped so the rest of the
// list still runs; the exit code only reports whether the list file itself could
// be read, and the Python runner decides each stem's success from its summary
// JSON, not from this process's exit code.
int runBatch(const fs::path& analysis_path, const std::string& list_path,
             const hermes_event_reconstructor::ReconParams& settings,
             const bool overwrite) {
    std::ifstream list_file(list_path);
    if (!list_file) {
        std::cerr << "Error: unable to open input list file: " << list_path
                  << "\n";
        return 2;
    }

    // Group the listed photon files by raw stem. std::map keeps stems in a
    // stable order, and each group is sorted below so parts read in order.
    std::map<std::string, std::vector<std::string>> files_by_stem;
    std::string photon_path;
    while (std::getline(list_file, photon_path)) {
        if (!photon_path.empty() && photon_path.back() == '\r') {
            photon_path.pop_back();
        }
        if (photon_path.empty()) {
            continue;
        }
        const std::string stem = stemForPhotonFile(photon_path);
        if (stem.empty()) {
            std::cerr << "Error: photon filename does not match "
                         "<stem>_chip_<chip>_photon_<part>.parquet: "
                      << photon_path << "\n";
            continue;
        }
        files_by_stem[stem].push_back(photon_path);
    }

    for (auto& [stem, files] : files_by_stem) {
        std::sort(files.begin(), files.end());
        if (reconstructOneStem(analysis_path, stem, files, settings,
                               overwrite) != 0) {
            std::cerr << "Failed: " << stem << "\n";
        }
    }
    return 0;
}

}  // namespace

int main(const int argc, char* argv[]) {
    std::string analysis_directory;
    std::string raw_file_stem;
    std::string input_list_path;
    std::string settings_file;
    bool overwrite = false;
    bool have_input = false;
    bool have_stem = false;
    bool have_input_list = false;

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
            analysis_directory = argv[++i];
            have_input = true;
            continue;
        }
        if (arg == "--raw-file-stem") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --raw-file-stem requires a value\n";
                return 2;
            }
            raw_file_stem = argv[++i];
            have_stem = true;
            continue;
        }
        if (arg == "--input-list") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --input-list requires a file path\n";
                return 2;
            }
            input_list_path = argv[++i];
            have_input_list = true;
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
        std::cerr << "Error: unrecognized argument: " << arg << "\n\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }

    if (!have_input) {
        std::cerr << "Error: --input <analysis_directory> is required\n";
        return 2;
    }
    if (have_stem == have_input_list) {
        std::cerr << "Error: pass exactly one of --raw-file-stem <stem> or "
                     "--input-list <file>\n";
        return 2;
    }

    // Start from built-in defaults; a settings file overrides only named fields.
    // Only the layout-independent checks run here; the grid checks that depend on
    // the sensor width wait until the layout is read from the photon files.
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

    const fs::path analysis_path(analysis_directory);
    if (have_input_list) {
        return runBatch(analysis_path, input_list_path, settings, overwrite);
    }

    const fs::path photons_dir = analysis_path / "photons";
    const std::vector<std::string> photon_files =
        gatherPhotonFiles(photons_dir, raw_file_stem);
    if (photon_files.empty()) {
        std::cerr << "Error: no photon files found for raw file stem '"
                  << raw_file_stem << "' under " << photons_dir.string()
                  << "\n";
        return 1;
    }
    return reconstructOneStem(analysis_path, raw_file_stem, photon_files,
                              settings, overwrite);
}
