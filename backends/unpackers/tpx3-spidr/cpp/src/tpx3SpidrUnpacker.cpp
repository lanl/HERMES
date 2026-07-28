#include <fstream>
#include <iostream>
#include <cstring>
#include <string>
#include <vector>

#include "diagnostics.h"
#include "unpacker.h"

namespace {
void printHelp(const char* program_name) {
    std::cout << "HERMES TPX3 SPIDR Unpacker v0.1.0\n\n";
    std::cout << "Usage: " << program_name << " [OPTIONS] <input.tpx3> [analysis_directory]\n\n";
    std::cout << "Arguments:\n";
    std::cout << "  <input.tpx3>        Input TPX3 raw data file\n";
    std::cout << "  [analysis_directory]  Shared directory for analysis files\n\n";
    std::cout << "Options:\n";
    std::cout << "  -h, --help       Show this help message\n";
    std::cout << "  -v, --version    Show version information\n";
    std::cout << "      --overwrite  Overwrite existing summary and Parquet files\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without analysis_directory:\n";
    std::cout << "    Prints summary statistics to stdout\n\n";
    std::cout << "  With analysis_directory:\n";
    std::cout << "    Creates Parquet files for each dataset type:\n";
    std::cout << "      - pixelHits/          Sorted pixel hit events\n";
    std::cout << "      - tdcTriggers/        Sorted TDC trigger events\n";
    std::cout << "      - globalTimestamps/   Global timestamp anchors\n";
    std::cout << "      - controlPackets/     Control packets\n";
    std::cout << "      - unknownPackets/     Unknown packets\n";
    std::cout << "      - logs/               Input-specific summary JSON\n\n";
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
    // Separate options from positional arguments.
    bool overwrite = false;
    std::vector<std::string> positionals;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "-h") == 0 || std::strcmp(argv[i], "--help") == 0) {
            printHelp(argv[0]);
            return 0;
        }
        if (std::strcmp(argv[i], "-v") == 0 || std::strcmp(argv[i], "--version") == 0) {
            printVersion();
            return 0;
        }
        if (std::strcmp(argv[i], "--overwrite") == 0) {
            overwrite = true;
            continue;
        }
        positionals.emplace_back(argv[i]);
    }

    if (positionals.empty() || positionals.size() > 2) {
        std::cerr << "Error: Invalid number of arguments\n\n";
        std::cerr << "Usage: " << argv[0] << " [OPTIONS] <input.tpx3> [analysis_directory]\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }

    const std::string input_path = positionals[0];
    std::ifstream input(input_path, std::ios::binary);
    if (!input) {
        std::cerr << "Unable to open TPX3 input file: " << input_path << '\n';
        return 2;
    }

    if (positionals.size() == 2) {
        // Two-pass workflow with output
        const std::string output_dir = positionals[1];
        const auto result = hermes_tpx3_spidr::runTwoPassWorkflow(
            input, input_path, output_dir, overwrite);

        if (!result.success) {
            std::cerr << "Workflow failed with errors:\n";
            for (const auto& error : result.errors) {
                std::cerr << "  " << error << '\n';
            }
            return 1;
        }

        std::cout << "Successfully wrote output to: " << output_dir << '\n';
        std::cout << "\nTiming:\n";
        std::cout << "  Unpacking:         " << result.summary.timing_diagnostics.unpacking_seconds << " s\n";
        std::cout << "  Epoch assignment:  " << result.summary.timing_diagnostics.epoch_assignment_seconds << " s\n";
        std::cout << "  Sorting:           " << result.summary.timing_diagnostics.sorting_seconds << " s\n";
        std::cout << "  Conversion:        " << result.summary.timing_diagnostics.conversion_seconds << " s\n";
        std::cout << "  Parquet writing:   " << result.summary.timing_diagnostics.parquet_writing_seconds << " s\n";
        std::cout << "  Total:             " << result.summary.timing_diagnostics.total_seconds << " s\n";
        std::cout << "\nSummary:\n";
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
