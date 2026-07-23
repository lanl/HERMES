#include "test_helpers.h"
#include "summary_json.h"
#include "unpacker.h"

#include <nlohmann/json.hpp>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

using namespace hermes_tpx3_spidr;

namespace {

std::filesystem::path makeTestDirectory(const std::string& name) {
    static std::uint64_t directory_number = 0;
    const auto clock_value = std::chrono::high_resolution_clock::now()
                                 .time_since_epoch()
                                 .count();
    return std::filesystem::temp_directory_path() /
           ("hermes-tpx3-spidr-" + name + "-" +
            std::to_string(clock_value) + "-" +
            std::to_string(directory_number++));
}

std::string makePixelInput() {
    std::string bytes;
    appendLittleEndianWord(bytes, makeChunkHeader(0, 0, 8));
    const std::uint64_t pixel_packet = 0xB000000000000000ULL |
                                       (0x0100ULL << 44U) |
                                       (0x0200ULL << 30U) |
                                       (0x0050ULL << 16U) |
                                       0x1234ULL;
    appendLittleEndianWord(bytes, pixel_packet);
    return bytes;
}

nlohmann::json readJson(const std::filesystem::path& path) {
    std::ifstream input(path);
    nlohmann::json content;
    input >> content;
    return content;
}

void printWorkflowErrors(const WorkflowResult& result,
                         const std::string& run_name) {
    if (result.success) {
        return;
    }
    for (const auto& error : result.errors) {
        std::cerr << run_name << ": " << error << '\n';
    }
}

void testWorkflowWithEmptyInput(TestContext& test) {
    const auto analysis_directory = makeTestDirectory("empty");
    std::istringstream input("");
    const auto result = runTwoPassWorkflow(
        input, "/tmp/empty.tpx3", analysis_directory.string());

    test.expect(result.success, "workflow succeeded with empty input");
    test.expectEqual(result.analysis_directory, analysis_directory.string(),
                     "analysis directory preserved");

    for (const auto* directory : {"pixelHits", "tdcTriggers",
                                  "globalTimestamps", "controlPackets",
                                  "unknownPackets", "logs"}) {
        test.expect(std::filesystem::is_directory(analysis_directory / directory),
                    std::string("created shared directory ") + directory);
    }
    test.expect(std::filesystem::exists(
                    analysis_directory / "logs/empty-unpacker-summary.json"),
                "empty-input summary JSON written");
    test.expectEqual(result.summary.writer_diagnostics.pixel_hits.row_count,
                     std::uint64_t{0}, "empty pixel row count recorded");
    test.expect(result.summary.writer_diagnostics.pixel_hits.files.empty(),
                "empty pixel file list recorded");

    std::filesystem::remove_all(analysis_directory);
}

void testSharedDirectoriesForTwoInputs(TestContext& test) {
    const auto analysis_directory = makeTestDirectory("shared");
    const auto bytes = makePixelInput();

    std::istringstream first_input(bytes);
    const auto first = runTwoPassWorkflow(
        first_input, "/tmp/DT_2p0V_000000.tpx3",
        analysis_directory.string());
    std::istringstream second_input(bytes);
    const auto second = runTwoPassWorkflow(
        second_input, "/tmp/DT_2p0V_000001.tpx3",
        analysis_directory.string());

    printWorkflowErrors(first, "first shared-directory run");
    printWorkflowErrors(second, "second shared-directory run");

    test.expect(first.success, "first input wrote shared analysis files");
    test.expect(second.success, "second input wrote shared analysis files");

    const auto first_parquet = analysis_directory /
        "pixelHits/DT_2p0V_000000-chip-0-part-00000.parquet";
    const auto second_parquet = analysis_directory /
        "pixelHits/DT_2p0V_000001-chip-0-part-00000.parquet";
    const auto first_summary = analysis_directory /
        "logs/DT_2p0V_000000-unpacker-summary.json";
    const auto second_summary = analysis_directory /
        "logs/DT_2p0V_000001-unpacker-summary.json";

    test.expect(std::filesystem::exists(first_parquet),
                "first input-prefixed Parquet file exists");
    test.expect(std::filesystem::exists(second_parquet),
                "second input-prefixed Parquet file exists");
    test.expect(std::filesystem::exists(first_summary),
                "first input-specific summary exists");
    test.expect(std::filesystem::exists(second_summary),
                "second input-specific summary exists");

    if (std::filesystem::exists(first_summary)) {
        const auto first_json = readJson(first_summary);
        test.expectEqual(
            first_json["parquet"]["pixel_data"]["row_count"]
                .get<std::uint64_t>(),
            std::uint64_t{1}, "summary records pixel row count");
        test.expectEqual(
            first_json["parquet"]["pixel_data"]["files"][0]
                .get<std::string>(),
            std::string(
                "pixelHits/DT_2p0V_000000-chip-0-part-00000.parquet"),
            "summary records input-prefixed Parquet filename");
    }

    std::filesystem::remove_all(analysis_directory);
}

void testExistingFilesAreNotOverwritten(TestContext& test) {
    const auto analysis_directory = makeTestDirectory("overwrite");
    const auto bytes = makePixelInput();
    const std::string source_path = "/tmp/repeated.tpx3";

    std::istringstream first_input(bytes);
    const auto first = runTwoPassWorkflow(
        first_input, source_path, analysis_directory.string());
    test.expect(first.success, "initial input wrote analysis files");

    std::istringstream summary_collision_input(bytes);
    const auto summary_collision = runTwoPassWorkflow(
        summary_collision_input, source_path, analysis_directory.string());
    test.expect(!summary_collision.success,
                "existing summary prevents repeated input");
    test.expect(!summary_collision.errors.empty(),
                "existing summary reports an error");

    const auto summary_path =
        analysis_directory / "logs/repeated-unpacker-summary.json";
    std::filesystem::remove(summary_path);

    const auto parquet_path = analysis_directory /
        "pixelHits/repeated-chip-0-part-00000.parquet";
    if (std::filesystem::exists(parquet_path)) {
        const auto parquet_size = std::filesystem::file_size(parquet_path);
        std::istringstream parquet_collision_input(bytes);
        const auto parquet_collision = runTwoPassWorkflow(
            parquet_collision_input, source_path, analysis_directory.string());
        test.expect(!parquet_collision.success,
                    "existing Parquet file prevents repeated input");
        test.expectEqual(std::filesystem::file_size(parquet_path), parquet_size,
                         "existing Parquet file was not changed");
    }

    std::filesystem::remove_all(analysis_directory);
}

void testSummaryJsonGeneration(TestContext& test) {
    SummaryJsonContent content;
    content.unpack_summary.bytes_read = 2'000'000;
    content.unpack_summary.chunks_read = 2;
    content.unpack_summary.packets_read = 4;
    content.unpack_summary.pixel_data_packet_count = 1;
    content.unpack_summary.tdc_timestamp_count = 6;
    content.unpack_summary.heartbeat_packet_count = 7;
    content.unpack_summary.spidr_control_count = 8;
    content.unpack_summary.tpx3_control_count = 9;
    content.unpack_summary.unrecognized_packet_count = 10;
    content.unpack_summary.tdc1_rising_count = 11;
    content.unpack_summary.tdc1_falling_count = 12;
    content.unpack_summary.tdc2_rising_count = 13;
    content.unpack_summary.tdc2_falling_count = 14;
    content.unpack_summary.unknown_tdc_edge_count = 15;
    content.anchor_diagnostics.total_anchors = 4;
    content.epoch_diagnostics.pixels_assigned = 3;
    content.epoch_diagnostics.tdcs_assigned = 5;
    content.epoch_diagnostics.controls_assigned = 6;
    content.epoch_diagnostics.unresolved_timestamps = 7;
    content.sorting_diagnostics.path_used = SortingPath::external_merge;
    content.sorting_diagnostics.estimated_memory_bytes = 2048;
    content.writer_diagnostics.pixel_hits.row_count = 1;
    content.writer_diagnostics.pixel_hits.files.push_back(
        "pixelHits/test-chip-0-part-00000.parquet");
    content.timing_diagnostics.conversion_seconds = 0.25;
    content.timing_diagnostics.epoch_assignment_seconds = 0.5;
    content.timing_diagnostics.total_seconds = 2.0;

    const auto parsed = nlohmann::json::parse(generateSummaryJson(content));

    test.expectEqual(
        parsed["unpacking"]["bytes_read"].get<std::uint64_t>(),
        std::uint64_t{2'000'000}, "JSON contains byte count");
    test.expectEqual(
        parsed["unpacking"]["pixel_data_packets"].get<std::uint64_t>(),
        std::uint64_t{1}, "JSON contains pixel data packet count");
    test.expectEqual(
        parsed["unpacking"]["tdc_timestamps"].get<std::uint64_t>(),
        std::uint64_t{6}, "JSON contains TDC timestamp count");
    test.expectEqual(
        parsed["unpacking"]["heartbeat_packets"].get<std::uint64_t>(),
        std::uint64_t{7}, "JSON contains heartbeat packet count");
    test.expectEqual(
        parsed["unpacking"]["spidr_control_packets"].get<std::uint64_t>(),
        std::uint64_t{8}, "JSON contains SPIDR control packet count");
    test.expectEqual(
        parsed["unpacking"]["tpx3_control_packets"].get<std::uint64_t>(),
        std::uint64_t{9}, "JSON contains TPX3 control packet count");
    test.expectEqual(
        parsed["unpacking"]["unrecognized_packets"].get<std::uint64_t>(),
        std::uint64_t{10}, "JSON contains unrecognized packet count");
    test.expectEqual(
        parsed["unpacking"]["tdc1_rising"].get<std::uint64_t>(),
        std::uint64_t{11}, "JSON contains TDC1 rising count");
    test.expectEqual(
        parsed["unpacking"]["tdc1_falling"].get<std::uint64_t>(),
        std::uint64_t{12}, "JSON contains TDC1 falling count");
    test.expectEqual(
        parsed["unpacking"]["tdc2_rising"].get<std::uint64_t>(),
        std::uint64_t{13}, "JSON contains TDC2 rising count");
    test.expectEqual(
        parsed["unpacking"]["tdc2_falling"].get<std::uint64_t>(),
        std::uint64_t{14}, "JSON contains TDC2 falling count");
    test.expectEqual(
        parsed["unpacking"]["unknown_tdc_edges"].get<std::uint64_t>(),
        std::uint64_t{15}, "JSON contains unknown TDC edge count");
    test.expectEqual(
        parsed["timestamp_processing"]["heartbeat_pairs"]["number_of_beats"]
            .get<std::uint64_t>(),
        std::uint64_t{4}, "JSON contains heartbeat pair count");
    test.expectEqual(
        parsed["timestamp_processing"]["time_adjustments"]["pixel_packets"]
            .get<std::uint64_t>(),
        std::uint64_t{3}, "JSON contains adjusted pixel packet count");
    test.expectEqual(
        parsed["timestamp_processing"]["time_adjustments"]["tdc_packets"]
            .get<std::uint64_t>(),
        std::uint64_t{5}, "JSON contains adjusted TDC packet count");
    test.expectEqual(
        parsed["timestamp_processing"]["time_adjustments"]["control_packets"]
            .get<std::uint64_t>(),
        std::uint64_t{6}, "JSON contains adjusted control packet count");
    test.expectEqual(
        parsed["timestamp_processing"]["time_adjustments"]["failed"]
            .get<std::uint64_t>(),
        std::uint64_t{7}, "JSON contains failed adjustment count");
    test.expectEqual(
        parsed["sorting"]["strategy"].get<std::string>(),
        std::string("external_merge"), "JSON contains sorting strategy");
    test.expectEqual(
        parsed["sorting"]["estimated_memory_bytes"].get<std::uint64_t>(),
        std::uint64_t{2048}, "JSON contains sorting memory estimate");
    test.expectEqual(
        parsed["parquet"]["pixel_data"]["row_count"].get<std::uint64_t>(),
        std::uint64_t{1}, "JSON contains pixel Parquet row count");
    test.expectEqual(
        parsed["parquet"]["pixel_data"]["files"][0].get<std::string>(),
        std::string("pixelHits/test-chip-0-part-00000.parquet"),
        "JSON contains relative pixel Parquet filename");
    test.expect(parsed["parquet"]["tdc_timestamps"]["files"].empty(),
                "JSON contains empty TDC file list");
    test.expectEqual(
        parsed["processing_times_seconds"]["total"].get<double>(),
        2.0, "JSON contains total processing time");
    test.expectEqual(
        parsed["processing_times_seconds"]["canonical_time_seconds"]
            .get<double>(),
        2.0345e-12, "JSON contains canonical time unit");
    test.expectEqual(
        parsed["processing_times_seconds"]["canonical_conversion"]
            .get<double>(),
        0.25, "JSON contains canonical conversion time");
    test.expectEqual(
        parsed["processing_times_seconds"]["time_adjustments"].get<double>(),
        0.5, "JSON contains time adjustment duration");
    test.expectEqual(
        parsed["processing_times_seconds"]["throughput"]
              ["packets_per_second"]
            .get<double>(),
        2.0, "JSON contains packet throughput");
    test.expectEqual(
        parsed["processing_times_seconds"]["throughput"]
              ["megabytes_per_second"]
            .get<double>(),
        1.0, "JSON contains megabyte throughput");
}

void testSummaryJsonStructure(TestContext& test) {
    SummaryJsonContent content;
    const auto parsed = nlohmann::json::parse(generateSummaryJson(content));

    test.expectEqual(parsed.size(), std::size_t{5},
                     "JSON contains exactly five top-level sections");
    for (const auto* section : {"unpacking", "timestamp_processing", "sorting",
                                "parquet", "processing_times_seconds"}) {
        test.expect(parsed.contains(section),
                    std::string("JSON contains ") + section);
    }
    for (const auto* removed : {"backend", "source", "configuration", "output",
                                "unpack_summary", "anchor_diagnostics",
                                "epoch_diagnostics", "sorting_diagnostics",
                                "writer_diagnostics", "timing_diagnostics"}) {
        test.expect(!parsed.contains(removed),
                    std::string("JSON omits ") + removed);
    }

    for (const auto* category : {"pixel_data", "tdc_timestamps",
                                 "heartbeat_packets", "control_packets",
                                 "unrecognized_packets"}) {
        const auto& category_json = parsed["parquet"][category];
        test.expectEqual(category_json.size(), std::size_t{2},
                         std::string(category) +
                             " contains only row_count and files");
        test.expect(category_json.contains("row_count"),
                    std::string(category) + " contains row_count");
        test.expect(category_json.contains("files"),
                    std::string(category) + " contains files");
        test.expect(!category_json.contains("directory"),
                    std::string(category) + " omits directory");
        test.expect(!category_json.contains("file_count"),
                    std::string(category) + " omits file_count");
    }

    test.expectEqual(
        parsed["timestamp_processing"]["heartbeat_pairs"].size(),
        std::size_t{1}, "heartbeat pairs contain only number_of_beats");
    test.expectEqual(
        parsed["timestamp_processing"]["time_adjustments"].size(),
        std::size_t{4}, "time adjustments contain four packet counts");
    test.expect(!parsed["sorting"].contains("method"),
                "sorting omits old method field");
    test.expect(!parsed["processing_times_seconds"].contains("conversion"),
                "processing times omit old conversion field");
    test.expect(
        !parsed["processing_times_seconds"].contains("epoch_assignment"),
        "processing times omit old epoch assignment field");
}

void testWorkflowErrorHandling(TestContext& test) {
    const auto analysis_directory = makeTestDirectory("malformed");
    std::string bytes;
    appendLittleEndianWord(bytes, 0x12345678ABCDEF00ULL);

    std::istringstream input(bytes);
    const auto result = runTwoPassWorkflow(
        input, "/tmp/malformed.tpx3", analysis_directory.string());

    test.expect(result.summary.unpack_summary.malformed_chunk_count > 0,
                "malformed chunks detected");
    test.expect(!result.summary.unpack_summary.errors.empty(),
                "errors recorded in summary");

    std::filesystem::remove_all(analysis_directory);
}

}  // namespace

int main() {
    TestContext test;
    testWorkflowWithEmptyInput(test);
    testSharedDirectoriesForTwoInputs(test);
    testExistingFilesAreNotOverwritten(test);
    testSummaryJsonGeneration(test);
    testSummaryJsonStructure(test);
    testWorkflowErrorHandling(test);
    return test.finish();
}
