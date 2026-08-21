#ifndef HERMES_TPX3_SPIDR_PARQUET_WRITER_H
#define HERMES_TPX3_SPIDR_PARQUET_WRITER_H

#include "output_rows.h"

#include <cstdint>
#include <string>
#include <vector>

namespace hermes_tpx3_spidr {

struct ParquetWriterConfig {
    std::string analysis_directory;
    std::string raw_file_stem;
    std::uint64_t rows_per_part = 1000000;
    std::uint8_t chip_index = 0;
    bool overwrite = false;
};

struct ParquetCategoryFiles {
    std::string directory;
    std::uint64_t row_count = 0;
    std::vector<std::string> files;
};

struct ParquetWriterDiagnostics {
    ParquetCategoryFiles pixel_hits{"pixel_hits", 0, {}};
    ParquetCategoryFiles tdc_triggers{"tdc_triggers", 0, {}};
    ParquetCategoryFiles global_timestamps{"global_timestamps", 0, {}};
    ParquetCategoryFiles control_packets{"control_packets", 0, {}};
    ParquetCategoryFiles unknown_packets{"unrecognized_packets", 0, {}};
    std::vector<std::string> errors;
};

void writePixelHitsParquet(const std::vector<PixelOutputRow>& rows,
                           const ParquetWriterConfig& config,
                           ParquetWriterDiagnostics& diagnostics);

void writeTdcTriggersParquet(const std::vector<TdcOutputRow>& rows,
                             const std::string& data_label,
                             const ParquetWriterConfig& config,
                             ParquetWriterDiagnostics& diagnostics);

void writeGlobalTimestampsParquet(const std::vector<GlobalOutputRow>& rows,
                                   const ParquetWriterConfig& config,
                                   ParquetWriterDiagnostics& diagnostics);

void writeControlPacketsParquet(const std::vector<ControlOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics);

void writeUnknownPacketsParquet(const std::vector<UnknownOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics);

}  // namespace hermes_tpx3_spidr

#endif
