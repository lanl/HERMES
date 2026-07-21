#ifndef HERMES_TPX3_SPIDR_SUMMARY_JSON_H
#define HERMES_TPX3_SPIDR_SUMMARY_JSON_H

#include "packet_types.h"
#include "parquet_writer.h"
#include "time_sort.h"

#include <string>

namespace hermes_tpx3_spidr {

struct SummaryJsonContent {
    std::string backend_name = "tpx3-spidr-cpp";
    std::string backend_version = "0.1.0";

    std::string source_file_path;
    std::uint64_t source_file_bytes = 0;

    std::string output_directory;
    std::string status = "incomplete";

    UnpackSummary unpack_summary;
    AnchorIndexDiagnostics anchor_diagnostics;
    EpochAssignmentDiagnostics epoch_diagnostics;
    SortingDiagnostics sorting_diagnostics;
    ParquetWriterDiagnostics writer_diagnostics;
};

std::string generateSummaryJson(const SummaryJsonContent& content);

void writeSummaryJsonFile(const std::string& output_path,
                          const SummaryJsonContent& content);

}  // namespace hermes_tpx3_spidr

#endif
