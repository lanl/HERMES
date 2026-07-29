#include <fstream>
#include <iostream>
#include <string>

#include "diagnostics.h"
#include "unpacker.h"

namespace {
void printHelp(const char* program_name) {
    std::cout << "HERMES TPX3 SPIDR Unpacker v0.1.0\n\n";
    std::cout << "Usage: " << program_name
              << " --input <input.tpx3> [--output <analysis_directory>] [--overwrite]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <input.tpx3>          Input TPX3 raw data file (required)\n";
    std::cout << "  --output <analysis_directory> Shared analysis directory (optional)\n";
    std::cout << "  --overwrite                   Overwrite existing summary and Parquet files\n";
    std::cout << "  -h, --help                    Show this help message\n";
    std::cout << "  -v, --version                 Show version information\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without --output:\n";
    std::cout << "    Prints summary statistics only; writes no files.\n\n";
    std::cout << "  With --output:\n";
    std::cout << "    Creates Parquet files under the analysis directory:\n";
    std::cout << "      - pixelHits/          Sorted pixel hit events\n";
    std::cout << "      - tdcTriggers/        Sorted TDC trigger events\n";
    std::cout << "      - globalTimestamps/   Global timestamp anchors\n";
    std::cout << "      - controlPackets/     Control packets\n";
    std::cout << "      - unknownPackets/     Unknown packets\n";
    std::cout << "      - logs/               Input-specific summary JSON\n\n";
    std::cout << "Examples:\n";
    std::cout << "  # Print summary only\n";
    std::cout << "  " << program_name << " --input data.tpx3\n\n";
    std::cout << "  # Write Parquet files\n";
    std::cout << "  " << program_name << " --input data.tpx3 --output analysis/\n\n";
}

void printVersion() {
    std::cout << "HERMES TPX3 SPIDR Unpacker v0.1.0\n";
    std::cout << "C++17 implementation with Arrow/Parquet output\n";
}
}  // namespace

int main(const int argc, char* argv[]) {
    bool overwrite = false;
    std::string input_path;
    std::string output_dir;
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
            input_path = argv[++i];
            have_input = true;
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
        std::cerr << "Error: --input <input.tpx3> is required\n";
        return 2;
    }

    std::ifstream input(input_path, std::ios::binary);
    if (!input) {
        std::cerr << "Unable to open TPX3 input file: " << input_path << '\n';
        return 2;
    }

    if (!have_output) {
        // Without --output, unpack and print a summary without writing files.
        const auto result = hermes_tpx3_spidr::unpack(input);
        hermes_tpx3_spidr::printSummary(result.summary, std::cout);
        hermes_tpx3_spidr::printMessages(result.summary, std::cerr);
        return result.summary.errors.empty() ? 0 : 1;
    }

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
}
