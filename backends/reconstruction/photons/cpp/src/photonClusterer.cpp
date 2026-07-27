#include <cstring>
#include <iostream>

#include "clusterer.h"

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
    std::cout << "  -h, --help     Show this help message\n";
    std::cout << "  -v, --version  Show version information\n";
}

void printVersion() {
    std::cout << "HERMES Photon Clusterer v" << hermes_photon_clusterer::kVersion
              << "\n";
    std::cout << "C++17 connected-components photon reconstruction\n";
}
}  // namespace

int main(const int argc, char* argv[]) {
    if (argc == 2) {
        if (std::strcmp(argv[1], "-h") == 0 ||
            std::strcmp(argv[1], "--help") == 0) {
            printHelp(argv[0]);
            return 0;
        }
        if (std::strcmp(argv[1], "-v") == 0 ||
            std::strcmp(argv[1], "--version") == 0) {
            printVersion();
            return 0;
        }
    }

    // Clustering execution is wired up in the following Stage 4 steps.
    std::cerr << "Error: photon clustering is not implemented yet\n";
    std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
    return 2;
}
