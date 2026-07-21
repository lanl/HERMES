#include "summary_json.h"

#include <nlohmann/json.hpp>
#include <fstream>

using json = nlohmann::json;

namespace hermes_tpx3_spidr {

std::string generateSummaryJson(const SummaryJsonContent& content) {
    json j;

    j["backend"] = {
        {"name", content.backend_name},
        {"version", content.backend_version}
    };

    j["source"] = {
        {"file_path", content.source_file_path},
        {"file_bytes", content.source_file_bytes}
    };

    j["output"] = {
        {"directory", content.output_directory},
        {"status", content.status}
    };

    j["unpack_summary"] = {
        {"bytes_read", content.unpack_summary.bytes_read},
        {"chunks_read", content.unpack_summary.chunks_read},
        {"packets_read", content.unpack_summary.packets_read},
        {"pixel_hit_count", content.unpack_summary.pixel_hit_count},
        {"tdc_hit_count", content.unpack_summary.tdc_hit_count},
        {"global_timestamp_count", content.unpack_summary.global_timestamp_count},
        {"spidr_control_count", content.unpack_summary.spidr_control_count},
        {"tpx3_control_count", content.unpack_summary.tpx3_control_count},
        {"unknown_packet_count", content.unpack_summary.unknown_packet_count},
        {"warnings", content.unpack_summary.warnings},
        {"errors", content.unpack_summary.errors}
    };

    j["anchor_diagnostics"] = {
        {"total_anchors", content.anchor_diagnostics.total_anchors},
        {"unpaired_low_count", content.anchor_diagnostics.unpaired_low_count},
        {"unpaired_high_count", content.anchor_diagnostics.unpaired_high_count},
        {"warnings", content.anchor_diagnostics.warnings}
    };

    j["epoch_diagnostics"] = {
        {"pixels_assigned", content.epoch_diagnostics.pixels_assigned},
        {"tdcs_assigned", content.epoch_diagnostics.tdcs_assigned},
        {"controls_assigned", content.epoch_diagnostics.controls_assigned},
        {"ambiguous_timestamps", content.epoch_diagnostics.ambiguous_timestamps},
        {"unresolved_timestamps", content.epoch_diagnostics.unresolved_timestamps},
        {"used_fallback", content.epoch_diagnostics.used_fallback},
        {"warnings", content.epoch_diagnostics.warnings}
    };

    j["sorting_diagnostics"] = {
        {"path_used", content.sorting_diagnostics.path_used == SortingPath::in_memory ? "in_memory" : "external_merge"},
        {"memory_budget_bytes", content.sorting_diagnostics.memory_budget_bytes},
        {"estimated_memory_bytes", content.sorting_diagnostics.estimated_memory_bytes},
        {"temporary_runs_created", content.sorting_diagnostics.temporary_runs_created}
    };

    j["writer_diagnostics"] = {
        {"pixel_files_written", content.writer_diagnostics.pixel_files_written},
        {"tdc_files_written", content.writer_diagnostics.tdc_files_written},
        {"global_files_written", content.writer_diagnostics.global_files_written},
        {"control_files_written", content.writer_diagnostics.control_files_written},
        {"unknown_files_written", content.writer_diagnostics.unknown_files_written},
        {"errors", content.writer_diagnostics.errors}
    };

    return j.dump(2);
}

void writeSummaryJsonFile(const std::string& output_path,
                          const SummaryJsonContent& content) {
    const auto json_str = generateSummaryJson(content);
    std::ofstream out(output_path);
    out << json_str;
}

}  // namespace hermes_tpx3_spidr
