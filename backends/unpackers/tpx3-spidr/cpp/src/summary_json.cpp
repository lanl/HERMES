#include "summary_json.h"

#include <nlohmann/json.hpp>
#include <filesystem>
#include <fstream>
#include <stdexcept>

using json = nlohmann::ordered_json;

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
    const auto total_seconds = content.timing_diagnostics.total_seconds;
    const auto packets_per_second =
        total_seconds > 0.0
            ? static_cast<double>(content.unpack_summary.packets_read) /
                  total_seconds
            : 0.0;
    const auto megabytes_per_second =
        total_seconds > 0.0
            ? static_cast<double>(content.unpack_summary.bytes_read) /
                  total_seconds / 1'000'000.0
            : 0.0;

    j["unpacking"] = {
        {"bytes_read", content.unpack_summary.bytes_read},
        {"chunks_read", content.unpack_summary.chunks_read},
        {"packets_read", content.unpack_summary.packets_read},
        {"pixel_data_packets",
         content.unpack_summary.pixel_data_packet_count},
        {"tdc_timestamps", content.unpack_summary.tdc_timestamp_count},
        {"heartbeat_packets", content.unpack_summary.heartbeat_packet_count},
        {"spidr_control_packets", content.unpack_summary.spidr_control_count},
        {"tpx3_control_packets", content.unpack_summary.tpx3_control_count},
        {"unrecognized_packets",
         content.unpack_summary.unrecognized_packet_count},
        {"tdc1_rising", content.unpack_summary.tdc1_rising_count},
        {"tdc1_falling", content.unpack_summary.tdc1_falling_count},
        {"tdc2_rising", content.unpack_summary.tdc2_rising_count},
        {"tdc2_falling", content.unpack_summary.tdc2_falling_count},
        {"unknown_tdc_edges",
         content.unpack_summary.unknown_tdc_edge_count},
        {"errors", content.unpack_summary.errors},
        {"warnings", content.unpack_summary.warnings}
    };

    j["timestamp_processing"] = {
        {"heartbeat_pairs", {
            {"number_of_beats", content.anchor_diagnostics.total_anchors}
        }},
        {"time_adjustments", {
            {"pixel_packets", content.epoch_diagnostics.pixels_assigned},
            {"tdc_packets", content.epoch_diagnostics.tdcs_assigned},
            {"control_packets", content.epoch_diagnostics.controls_assigned},
            {"failed", content.epoch_diagnostics.unresolved_timestamps}
        }}
    };

    j["sorting"] = {
        {"strategy",
         content.sorting_diagnostics.path_used == SortingPath::in_memory
             ? "in_memory"
             : "external_merge"},
        {"memory_budget_bytes", content.sorting_diagnostics.memory_budget_bytes},
        {"estimated_memory_bytes", content.sorting_diagnostics.estimated_memory_bytes},
        {"temporary_runs_created", content.sorting_diagnostics.temporary_runs_created}
    };

    j["parquet"] = {
        {"pixel_data", categoryJson(content.writer_diagnostics.pixel_hits)},
        {"tdc_timestamps", categoryJson(content.writer_diagnostics.tdc_triggers)},
        {"heartbeat_packets",
         categoryJson(content.writer_diagnostics.global_timestamps)},
        {"control_packets", categoryJson(content.writer_diagnostics.control_packets)},
        {"unrecognized_packets",
         categoryJson(content.writer_diagnostics.unknown_packets)},
        {"errors", content.writer_diagnostics.errors}
    };

    j["processing_times_seconds"] = {
        {"canonical_time_seconds", 2.0345e-12},
        {"unpacking", content.timing_diagnostics.unpacking_seconds},
        {"canonical_conversion",
         content.timing_diagnostics.conversion_seconds},
        {"time_adjustments",
         content.timing_diagnostics.epoch_assignment_seconds},
        {"sorting", content.timing_diagnostics.sorting_seconds},
        {"parquet_writing", content.timing_diagnostics.parquet_writing_seconds},
        {"total", total_seconds},
        {"throughput", {
            {"packets_per_second", packets_per_second},
            {"megabytes_per_second", megabytes_per_second}
        }}
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
