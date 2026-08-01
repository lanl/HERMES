#include "parquet_schemas.h"

#include <arrow/api.h>

namespace hermes_tpx3_spidr {

std::shared_ptr<arrow::Schema> createPixelHitsSchema() {
    return arrow::schema({
        arrow::field("chunk_index", arrow::uint64()),
        arrow::field("packet_index", arrow::uint64()),
        arrow::field("local_x", arrow::uint16()),
        arrow::field("local_y", arrow::uint16()),
        arrow::field("tot_raw", arrow::uint16()),
        arrow::field("timestamp_canonical", arrow::uint64())
    });
}

std::shared_ptr<arrow::Schema> createTdcTriggersSchema() {
    return arrow::schema({
        arrow::field("chunk_index", arrow::uint64()),
        arrow::field("packet_index", arrow::uint64()),
        arrow::field("trigger_type", arrow::uint8()),
        arrow::field("timestamp_canonical", arrow::uint64())
    });
}

std::shared_ptr<arrow::Schema> createGlobalTimestampsSchema() {
    return arrow::schema({
        arrow::field("chunk_index", arrow::uint64()),
        arrow::field("packet_index", arrow::uint64()),
        arrow::field("timestamp_canonical", arrow::uint64())
    });
}

std::shared_ptr<arrow::Schema> createControlPacketsSchema() {
    return arrow::schema({
        arrow::field("chunk_index", arrow::uint64()),
        arrow::field("packet_index", arrow::uint64()),
        arrow::field("source", arrow::uint8()),
        arrow::field("control_type", arrow::uint16()),
        arrow::field("packet_id", arrow::uint8()),
        arrow::field("packet_id_present", arrow::boolean()),
        arrow::field("subtype", arrow::uint8()),
        arrow::field("subtype_present", arrow::boolean()),
        arrow::field("packet_count", arrow::uint64()),
        arrow::field("packet_count_present", arrow::boolean()),
        arrow::field("reserved_high", arrow::uint16()),
        arrow::field("reserved_high_present", arrow::boolean()),
        arrow::field("reserved_low", arrow::uint16()),
        arrow::field("reserved_low_present", arrow::boolean()),
        arrow::field("control_value_raw", arrow::uint16()),
        arrow::field("control_value_raw_present", arrow::boolean()),
        arrow::field("control_payload_raw", arrow::uint64()),
        arrow::field("control_payload_raw_present", arrow::boolean()),
        arrow::field("timestamp_canonical", arrow::uint64()),
        arrow::field("timestamp_canonical_present", arrow::boolean())
    });
}

std::shared_ptr<arrow::Schema> createUnknownPacketsSchema() {
    return arrow::schema({
        arrow::field("chunk_index", arrow::uint64()),
        arrow::field("packet_index", arrow::uint64()),
        arrow::field("raw_word", arrow::uint64()),
        arrow::field("most_significant_byte", arrow::uint8())
    });
}

}  // namespace hermes_tpx3_spidr
