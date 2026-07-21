#ifndef HERMES_TPX3_SPIDR_PARQUET_WRITER_H
#define HERMES_TPX3_SPIDR_PARQUET_WRITER_H

#include "output_rows.h"

#include <cstdint>
#include <string>
#include <vector>

namespace hermes_tpx3_spidr {

struct ParquetWriterConfig {
    std::string output_directory;
    std::uint64_t rows_per_part = 1000000;
    std::uint8_t chip_index = 0;
};

struct ParquetWriterDiagnostics {
    std::uint64_t pixel_files_written = 0;
    std::uint64_t tdc_files_written = 0;
    std::uint64_t global_files_written = 0;
    std::uint64_t control_files_written = 0;
    std::uint64_t unknown_files_written = 0;
    std::vector<std::string> errors;
};

void writePixelHitsParquet(const std::vector<PixelOutputRow>& rows,
                           const ParquetWriterConfig& config,
                           ParquetWriterDiagnostics& diagnostics);

void writeTdcTriggersParquet(const std::vector<TdcOutputRow>& rows,
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
