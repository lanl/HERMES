#include <fstream>
#include <iostream>
#include <cstring>

#include "diagnostics.h"
#include "unpacker.h"

int main(const int argc, char* argv[]) {
    if (argc < 2 || argc > 3) {
        std::cerr << "Usage: " << argv[0] << " input.tpx3 [output_directory]\n";
        std::cerr << "  If output_directory is provided, writes Parquet files and summary.json\n";
        std::cerr << "  Otherwise, prints summary to stdout\n";
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
