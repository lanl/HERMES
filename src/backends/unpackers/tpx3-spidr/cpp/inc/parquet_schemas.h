#ifndef HERMES_TPX3_SPIDR_PARQUET_SCHEMAS_H
#define HERMES_TPX3_SPIDR_PARQUET_SCHEMAS_H

#include <memory>

namespace arrow {
class Schema;
}

namespace hermes_tpx3_spidr {

std::shared_ptr<arrow::Schema> createPixelHitsSchema();
std::shared_ptr<arrow::Schema> createTdcTriggersSchema();
std::shared_ptr<arrow::Schema> createGlobalTimestampsSchema();
std::shared_ptr<arrow::Schema> createControlPacketsSchema();
std::shared_ptr<arrow::Schema> createUnknownPacketsSchema();

}  // namespace hermes_tpx3_spidr

#endif
