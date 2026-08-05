#include <iostream>
#include <string>

#include "version.h"

namespace {

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
    std::cout << "    Writes one event_candidates file at the given path. The\n";
    std::cout << "    reconstruction-summary JSON is written to a logs/ "
                 "directory\n";
    std::cout << "    beside the output directory.\n";
}

void printVersion() {
    std::cout << "HERMES Event Reconstructor v"
              << hermes_event_reconstructor::kVersion << "\n";
    std::cout << "C++17 connected-components event reconstruction\n";
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

    // Stage 0 scaffold: argument parsing only. Later stages load settings, read
    // photons, cluster into events, and write the event and summary files.
    (void)output_file;
    (void)settings_file;
    (void)overwrite;
    (void)have_output;
    std::cerr << "Error: event reconstruction is not yet implemented\n";
    return 1;
}
