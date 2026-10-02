#ifndef HERMES_TPX3_SPIDR_SUMMARY_JSON_H
#define HERMES_TPX3_SPIDR_SUMMARY_JSON_H

#include "packet_types.h"
#include "parquet_writer.h"
#include "time_sort.h"

#include <cstdint>
#include <optional>
#include <string>

namespace hermes_tpx3_spidr {

struct TimingDiagnostics {
    double unpacking_seconds = 0.0;
    double epoch_assignment_seconds = 0.0;
    double sorting_seconds = 0.0;
    double conversion_seconds = 0.0;
    double parquet_writing_seconds = 0.0;
    double total_seconds = 0.0;
};

struct SummaryJsonContent {
    std::string measurement_id;
    std::string run;
    std::string inputfile;
    UnpackSummary unpack_summary;
    AnchorIndexDiagnostics anchor_diagnostics;
    // The earliest and latest global timestamp in this file, over all chips,
    // in canonical ticks; empty when the file has none.
    std::optional<std::uint64_t> first_timestamp_canonical;
    std::optional<std::uint64_t> last_timestamp_canonical;
    // The value given with --previous-global-timestamp; empty when not given.
    std::optional<std::uint64_t> previous_file_timestamp_canonical;
    EpochAssignmentDiagnostics epoch_diagnostics;
    SortingDiagnostics sorting_diagnostics;
    ParquetWriterDiagnostics writer_diagnostics;
    TimingDiagnostics timing_diagnostics;
};

std::string generateSummaryJson(const SummaryJsonContent& content);

void writeSummaryJsonFile(const std::string& output_path,
                          const SummaryJsonContent& content,
                          bool overwrite = false);

}  // namespace hermes_tpx3_spidr

#endif
