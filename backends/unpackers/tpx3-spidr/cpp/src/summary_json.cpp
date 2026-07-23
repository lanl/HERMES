#include "summary_json.h"

#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <stdexcept>

using json = nlohmann::json;

namespace hermes_tpx3_spidr {

namespace {

json categoryJson(const ParquetCategoryFiles& category) {
    return {
        {"row_count", category.row_count},
        {"files", category.files}
    };
}

}  // namespace

std::string generateSummaryJson(const SummaryJsonContent& content) {
    json j;

    j["unpacking"] = {
        {"chunks_read", content.unpack_summary.chunks_read},
        {"packets_read", content.unpack_summary.packets_read},
        {"decoded_pixel_hits", content.unpack_summary.pixel_data_packet_count},
        {"decoded_tdc_triggers", content.unpack_summary.tdc_timestamp_count},
        {"decoded_global_timestamps", content.unpack_summary.heartbeat_packet_count},
        {"decoded_spidr_control_packets", content.unpack_summary.spidr_control_count},
        {"decoded_tpx3_control_packets", content.unpack_summary.tpx3_control_count},
        {"decoded_unknown_packets", content.unpack_summary.unrecognized_packet_count},
        {"warnings", content.unpack_summary.warnings},
        {"errors", content.unpack_summary.errors}
    };

    j["timestamp_processing"] = {
        {"anchors", {
            {"total", content.anchor_diagnostics.total_anchors},
            {"unpaired_low", content.anchor_diagnostics.unpaired_low_count},
            {"unpaired_high", content.anchor_diagnostics.unpaired_high_count},
            {"warnings", content.anchor_diagnostics.warnings}
        }},
        {"epoch_assignment", {
            {"pixels_assigned", content.epoch_diagnostics.pixels_assigned},
            {"tdc_triggers_assigned", content.epoch_diagnostics.tdcs_assigned},
            {"controls_assigned", content.epoch_diagnostics.controls_assigned},
            {"ambiguous_timestamps", content.epoch_diagnostics.ambiguous_timestamps},
            {"unresolved_timestamps", content.epoch_diagnostics.unresolved_timestamps},
            {"used_fallback", content.epoch_diagnostics.used_fallback},
            {"warnings", content.epoch_diagnostics.warnings}
        }}
    };

    j["sorting"] = {
        {"method", content.sorting_diagnostics.path_used == SortingPath::in_memory ? "in_memory" : "external_merge"},
        {"memory_budget_bytes", content.sorting_diagnostics.memory_budget_bytes},
        {"estimated_memory_bytes", content.sorting_diagnostics.estimated_memory_bytes},
        {"temporary_runs_created", content.sorting_diagnostics.temporary_runs_created}
    };

    j["parquet"] = {
        {"pixel_hits", categoryJson(content.writer_diagnostics.pixel_hits)},
        {"tdc_triggers", categoryJson(content.writer_diagnostics.tdc_triggers)},
        {"global_timestamps", categoryJson(content.writer_diagnostics.global_timestamps)},
        {"control_packets", categoryJson(content.writer_diagnostics.control_packets)},
        {"unknown_packets", categoryJson(content.writer_diagnostics.unknown_packets)},
        {"errors", content.writer_diagnostics.errors}
    };

    j["processing_times_seconds"] = {
        {"unpacking", content.timing_diagnostics.unpacking_seconds},
        {"epoch_assignment", content.timing_diagnostics.epoch_assignment_seconds},
        {"conversion", content.timing_diagnostics.conversion_seconds},
        {"sorting", content.timing_diagnostics.sorting_seconds},
        {"parquet_writing", content.timing_diagnostics.parquet_writing_seconds},
        {"total", content.timing_diagnostics.total_seconds}
    };

    return j.dump(2);
}

void writeSummaryJsonFile(const std::string& output_path,
                          const SummaryJsonContent& content) {
    if (std::filesystem::exists(output_path)) {
        throw std::runtime_error(
            "Refusing to overwrite existing summary JSON file");
    }

    const auto json_str = generateSummaryJson(content);
    std::ofstream out(output_path);
    if (!out) {
        throw std::runtime_error("Unable to open summary JSON file");
    }
    out << json_str;
    if (!out) {
        throw std::runtime_error("Unable to write summary JSON file");
    }
}

}  // namespace hermes_tpx3_spidr
