#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "clusterer.h"
#include "settings.h"

namespace {
void printHelp(const char* program_name) {
    std::cout << "HERMES Photon Clusterer v" << hermes_photon_clusterer::kVersion
              << "\n\n";
    std::cout << "Usage: " << program_name
              << " [OPTIONS] <pixel_data_directory> <analysis_directory>\n\n";
    std::cout << "Arguments:\n";
    std::cout << "  <pixel_data_directory>  Directory of sorted pixel_data "
                 "Parquet files for one raw stem\n";
    std::cout << "  <analysis_directory>    Shared analysis directory for "
                 "photon output and logs\n\n";
    std::cout << "Options:\n";
    std::cout << "  -s, --settings <file>  JSON file overriding individual "
                 "clustering settings\n";
    std::cout << "                         (any field omitted keeps its "
                 "built-in default)\n";
    std::cout << "  -h, --help             Show this help message\n";
    std::cout << "  -v, --version          Show version information\n";
}

void printVersion() {
    std::cout << "HERMES Photon Clusterer v" << hermes_photon_clusterer::kVersion
              << "\n";
    std::cout << "C++17 connected-components photon reconstruction\n";
}
}  // namespace

int main(const int argc, char* argv[]) {
    std::string settings_file;
    std::vector<std::string> positionals;

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
        if (arg == "-s" || arg == "--settings") {
            if (i + 1 >= argc) {
                std::cerr << "Error: " << arg << " requires a file path\n";
                return 2;
            }
            settings_file = argv[++i];
            continue;
        }
        if (!arg.empty() && arg[0] == '-') {
            std::cerr << "Error: unknown option '" << arg << "'\n";
            std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
            return 2;
        }
        positionals.push_back(arg);
    }

    if (positionals.size() != 2) {
        std::cerr << "Error: expected <pixel_data_directory> and "
                     "<analysis_directory>\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }
    const std::string pixel_data_directory = positionals[0];
    const std::string analysis_directory = positionals[1];

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

    (void)pixel_data_directory;
    (void)analysis_directory;
    (void)settings;

    // The read -> cluster -> filter -> correct -> write -> summary pipeline is
    // wired up in the following Stage 4 step.
    std::cerr << "Error: photon clustering is not implemented yet\n";
    std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
    return 2;
}
