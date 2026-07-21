#include <fstream>
#include <iostream>
#include <cstring>

#include "diagnostics.h"
#include "unpacker.h"

namespace {
void printHelp(const char* program_name) {
    std::cout << "HERMES TPX3 SPIDR Unpacker v0.1.0\n\n";
    std::cout << "Usage: " << program_name << " [OPTIONS] <input.tpx3> [output_directory]\n\n";
    std::cout << "Arguments:\n";
    std::cout << "  <input.tpx3>        Input TPX3 raw data file\n";
    std::cout << "  [output_directory]  Optional output directory for Parquet files\n\n";
    std::cout << "Options:\n";
    std::cout << "  -h, --help     Show this help message\n";
    std::cout << "  -v, --version  Show version information\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without output_directory:\n";
    std::cout << "    Prints summary statistics to stdout\n\n";
    std::cout << "  With output_directory:\n";
    std::cout << "    Creates Parquet files for each dataset type:\n";
    std::cout << "      - pixel_hits/         Sorted pixel hit events\n";
    std::cout << "      - tdc_triggers/       Sorted TDC trigger events\n";
    std::cout << "      - global_timestamps/  Global timestamp anchors\n";
    std::cout << "      - control_packets/    Control packets\n";
    std::cout << "      - summary.json        Complete run diagnostics\n\n";
    std::cout << "Examples:\n";
    std::cout << "  # Print summary only\n";
    std::cout << "  " << program_name << " data.tpx3\n\n";
    std::cout << "  # Write Parquet files\n";
    std::cout << "  " << program_name << " data.tpx3 output/\n\n";
}

void printVersion() {
    std::cout << "HERMES TPX3 SPIDR Unpacker v0.1.0\n";
    std::cout << "C++17 implementation with Arrow/Parquet output\n";
}
}  // namespace

int main(const int argc, char* argv[]) {
    // Handle help and version flags
    if (argc == 2) {
        if (std::strcmp(argv[1], "-h") == 0 || std::strcmp(argv[1], "--help") == 0) {
            printHelp(argv[0]);
            return 0;
        }
        if (std::strcmp(argv[1], "-v") == 0 || std::strcmp(argv[1], "--version") == 0) {
            printVersion();
            return 0;
        }
    }

    if (argc < 2 || argc > 3) {
        std::cerr << "Error: Invalid number of arguments\n\n";
        std::cerr << "Usage: " << argv[0] << " [OPTIONS] <input.tpx3> [output_directory]\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
        std::cerr << "Unable to open TPX3 input file: " << argv[1] << '\n';
        return 2;
    }

    if (argc == 3) {
        // Two-pass workflow with output
        const std::string output_dir = argv[2];
        const auto result = hermes_tpx3_spidr::runTwoPassWorkflow(input, output_dir);

        if (!result.success) {
            std::cerr << "Workflow failed with errors:\n";
            for (const auto& error : result.errors) {
                std::cerr << "  " << error << '\n';
            }
            return 1;
        }

        std::cout << "Successfully wrote output to: " << output_dir << '\n';
        std::cout << "Status: " << result.summary.status << '\n';
        hermes_tpx3_spidr::printSummary(result.summary.unpack_summary, std::cout);

        return 0;
    } else {
        // Legacy mode: just unpack and print summary
        const auto result = hermes_tpx3_spidr::unpack(input);
        hermes_tpx3_spidr::printSummary(result.summary, std::cout);
        hermes_tpx3_spidr::printMessages(result.summary, std::cerr);

        return result.summary.errors.empty() ? 0 : 1;
    }
}
