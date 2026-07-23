#ifndef HERMES_TPX3_SPIDR_SUMMARY_JSON_H
#define HERMES_TPX3_SPIDR_SUMMARY_JSON_H

#include "packet_types.h"
#include "parquet_writer.h"
#include "time_sort.h"

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
    UnpackSummary unpack_summary;
    AnchorIndexDiagnostics anchor_diagnostics;
    EpochAssignmentDiagnostics epoch_diagnostics;
    SortingDiagnostics sorting_diagnostics;
    ParquetWriterDiagnostics writer_diagnostics;
    TimingDiagnostics timing_diagnostics;
};

std::string generateSummaryJson(const SummaryJsonContent& content);

void writeSummaryJsonFile(const std::string& output_path,
                          const SummaryJsonContent& content);

}  // namespace hermes_tpx3_spidr

#endif
