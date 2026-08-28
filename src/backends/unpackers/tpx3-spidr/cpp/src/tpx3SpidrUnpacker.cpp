#include <fstream>
#include <iostream>
#include <string>

#include "diagnostics.h"
#include "unpacker.h"

namespace {
void printHelp(const char* program_name) {
    std::cout << "HERMES TPX3 SPIDR Unpacker v0.1.0\n\n";
    std::cout << "Usage: " << program_name
              << " --input <input.tpx3> [--output <analysis_directory>"
                 " --measurement-id <id> --run <run>]"
                 " [--overwrite] [--time-sort <true|false>]\n\n";
    std::cout << "Options:\n";
    std::cout << "  --input <input.tpx3>          Input TPX3 raw data file (required)\n";
    std::cout << "  --input-list <file>           Unpack every raw file listed in <file>\n";
    std::cout << "                                (one path per line) in this one process,\n";
    std::cout << "                                paying the startup cost once for the whole\n";
    std::cout << "                                list. Use instead of --input; requires\n";
    std::cout << "                                --output, --measurement-id, and --run\n";
    std::cout << "  --output <analysis_directory> Shared analysis directory (optional)\n";
    std::cout << "  --measurement-id <id>         Measurement identifier copied into the\n";
    std::cout << "                                summary JSON (required with --output)\n";
    std::cout << "  --run <run>                   Run label copied into the summary JSON\n";
    std::cout << "                                (required with --output)\n";
    std::cout << "  --overwrite                   Overwrite existing summary and Parquet files\n";
    std::cout << "  --time-sort <true|false>      Sort rows by timestamp (default: true).\n";
    std::cout << "                                false leaves rows in source packet order\n";
    std::cout << "                                (diagnostics only; downstream clustering\n";
    std::cout << "                                assumes time-ordered data)\n";
    std::cout << "  -h, --help                    Show this help message\n";
    std::cout << "  -v, --version                 Show version information\n\n";
    std::cout << "Output Modes:\n";
    std::cout << "  Without --output:\n";
    std::cout << "    Prints summary statistics only; writes no files.\n\n";
    std::cout << "  With --output:\n";
    std::cout << "    Creates Parquet files under the analysis directory:\n";
    std::cout << "      - pixel_hits/          Sorted pixel hit events\n";
    std::cout << "      - tdc_triggers/        Sorted TDC trigger events\n";
    std::cout << "      - global_timestamps/   Global timestamp anchors\n";
    std::cout << "      - control_packets/     Control packets\n";
    std::cout << "      - unrecognized_packets/ Unrecognized packets\n";
    std::cout << "      - logs/unpacking/     Input-specific summary JSON\n\n";
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

// Unpack every raw file named in list_path (one path per line) in a single
// process, so the one-time cost of loading Arrow/Parquet is paid once for the
// whole list instead of once per file. Each file is unpacked in its own scope
// so its decoded packets and output rows are freed before the next file starts.
// A file that cannot be opened, or whose workflow reports errors or throws, is
// logged and skipped so the rest of the list still runs. The exit code only
// reports whether the list itself could be read; the Python runner decides each
// file's success from its summary JSON, not from this process's exit code.
int runBatch(const std::string& list_path, const std::string& output_dir,
             const std::string& measurement_id, const std::string& run,
             const bool overwrite, const bool time_sort) {
    std::ifstream list_file(list_path);
    if (!list_file) {
        std::cerr << "Unable to open input list file: " << list_path << '\n';
        return 2;
    }

    std::string raw_path;
    while (std::getline(list_file, raw_path)) {
        if (!raw_path.empty() && raw_path.back() == '\r') {
            raw_path.pop_back();
        }
        if (raw_path.empty()) {
            continue;
        }
        try {
            std::ifstream input(raw_path, std::ios::binary);
            if (!input) {
                std::cerr << "Unable to open TPX3 input file: " << raw_path
                          << '\n';
                continue;
            }
            const auto result = hermes_tpx3_spidr::runTwoPassWorkflow(
                input, raw_path, output_dir, measurement_id, run, overwrite,
                time_sort);
            if (result.success) {
                std::cout << "Unpacked: " << raw_path << '\n';
            } else {
                std::cerr << "Failed: " << raw_path << '\n';
                for (const auto& error : result.errors) {
                    std::cerr << "  " << error << '\n';
                }
            }
        } catch (const std::exception& error) {
            std::cerr << "Failed: " << raw_path << " (" << error.what() << ")\n";
        }
    }
    return 0;
}
}  // namespace

int main(const int argc, char* argv[]) {
    bool overwrite = false;
    bool time_sort = true;
    std::string input_path;
    std::string input_list_path;
    std::string output_dir;
    std::string measurement_id;
    std::string run;
    bool have_input = false;
    bool have_input_list = false;
    bool have_output = false;
    bool have_measurement_id = false;
    bool have_run = false;

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
        if (arg == "--time-sort") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --time-sort requires true or false\n";
                return 2;
            }
            // Defaults to true; only an explicit "false" disables sorting.
            time_sort = std::string(argv[++i]) != "false";
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
        if (arg == "--input-list") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --input-list requires a file path\n";
                return 2;
            }
            input_list_path = argv[++i];
            have_input_list = true;
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
        if (arg == "--measurement-id") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --measurement-id requires a value\n";
                return 2;
            }
            measurement_id = argv[++i];
            have_measurement_id = true;
            continue;
        }
        if (arg == "--run") {
            if (i + 1 >= argc) {
                std::cerr << "Error: --run requires a value\n";
                return 2;
            }
            run = argv[++i];
            have_run = true;
            continue;
        }
        std::cerr << "Error: unrecognized argument: " << arg << "\n\n";
        std::cerr << "Try '" << argv[0] << " --help' for more information.\n";
        return 2;
    }

    if (have_input_list) {
        // Batched mode: unpack every file in the list in one process, always
        // writing output. It shares the single-file options but reads its
        // inputs from the list file instead of --input.
        if (have_input) {
            std::cerr << "Error: use either --input or --input-list, not both\n";
            return 2;
        }
        if (!have_output || !have_measurement_id || !have_run) {
            std::cerr << "Error: --input-list requires --output, "
                         "--measurement-id, and --run\n";
            return 2;
        }
        return runBatch(input_list_path, output_dir, measurement_id, run,
                        overwrite, time_sort);
    }

    if (!have_input) {
        std::cerr << "Error: --input <input.tpx3> or --input-list <file> is "
                     "required\n";
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

    if (!have_measurement_id || !have_run) {
        std::cerr << "Error: --measurement-id and --run are required with "
                     "--output\n";
        return 2;
    }

    const auto result = hermes_tpx3_spidr::runTwoPassWorkflow(
        input, input_path, output_dir, measurement_id, run, overwrite,
        time_sort);

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
