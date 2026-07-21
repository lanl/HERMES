#include "parquet_writer.h"
#include "parquet_schemas.h"

namespace hermes_tpx3_spidr {

void writePixelHitsParquet(const std::vector<PixelOutputRow>& rows,
                           const ParquetWriterConfig& config,
                           ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    (void)diagnostics;
}

void writeTdcTriggersParquet(const std::vector<TdcOutputRow>& rows,
                             const ParquetWriterConfig& config,
                             ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    (void)diagnostics;
}

void writeGlobalTimestampsParquet(const std::vector<GlobalOutputRow>& rows,
                                   const ParquetWriterConfig& config,
                                   ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    (void)diagnostics;
}

void writeControlPacketsParquet(const std::vector<ControlOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    (void)diagnostics;
}

void writeUnknownPacketsParquet(const std::vector<UnknownOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    (void)diagnostics;
}

}  // namespace hermes_tpx3_spidr
