#include <fstream>
#include <iostream>

#include "diagnostics.h"
#include "unpacker.h"

int main(const int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Usage: " << argv[0] << " input.tpx3\n";
        return 2;
    }

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
        std::cerr << "Unable to open TPX3 input file: " << argv[1] << '\n';
        return 2;
    }

    const auto result = hermes_tpx3_spidr::unpack(input);
    hermes_tpx3_spidr::printSummary(result.summary, std::cout);
    hermes_tpx3_spidr::printMessages(result.summary, std::cerr);

    return result.summary.errors.empty() ? 0 : 1;
}
