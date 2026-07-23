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
    test.expectEqual(result.summary.status, std::string("complete"),
                     "status set to complete");
    test.expectEqual(result.summary.source_file_path,
                     std::string("/tmp/empty.tpx3"),
                     "source file path preserved");
    test.expectEqual(result.summary.source_file_bytes, std::uint64_t{0},
                     "empty source file size recorded");
    test.expectEqual(result.summary.summary_json_file,
                     std::string("logs/empty-unpacker-summary.json"),
                     "input-specific summary filename recorded");

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
            first_json["output"]["analysis_directory"].get<std::string>(),
            analysis_directory.string(),
            "summary records shared analysis directory");
        test.expectEqual(
            first_json["output"]["categories"]["pixel_hits"]["row_count"]
                .get<std::uint64_t>(),
            std::uint64_t{1}, "summary records pixel row count");
        test.expectEqual(
            first_json["output"]["categories"]["pixel_hits"]["files"][0]
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
    content.backend_name = "test-backend";
    content.backend_version = "1.0.0";
    content.source_file_path = "/tmp/test.tpx3";
    content.source_file_bytes = 2048;
    content.analysis_directory = "/tmp/output";
    content.summary_json_file = "logs/test-unpacker-summary.json";
    content.status = "complete";
    content.writer_diagnostics.pixel_hits.row_count = 1;
    content.writer_diagnostics.pixel_hits.files.push_back(
        "pixelHits/test-chip-0-part-00000.parquet");

    const auto parsed = nlohmann::json::parse(generateSummaryJson(content));

    test.expectEqual(parsed["backend"]["name"].get<std::string>(),
                     std::string("test-backend"),
                     "JSON contains backend name");
    test.expectEqual(parsed["source"]["file_path"].get<std::string>(),
                     std::string("/tmp/test.tpx3"),
                     "JSON contains source file path");
    test.expectEqual(parsed["source"]["file_bytes"].get<std::uint64_t>(),
                     std::uint64_t{2048}, "JSON contains source file size");
    test.expectEqual(
        parsed["output"]["categories"]["pixel_hits"]["file_count"]
            .get<std::uint64_t>(),
        std::uint64_t{1}, "JSON contains category file count");
    test.expect(parsed["output"]["categories"]["tdc_triggers"]["files"]
                    .empty(),
                "JSON contains empty TDC file list");
}

void testSummaryJsonStructure(TestContext& test) {
    SummaryJsonContent content;
    const auto parsed = nlohmann::json::parse(generateSummaryJson(content));

    test.expect(parsed.contains("configuration"),
                "JSON contains configuration");
    test.expect(parsed.contains("unpack_summary"),
                "JSON contains unpack_summary");
    test.expect(parsed.contains("anchor_diagnostics"),
                "JSON contains anchor_diagnostics");
    test.expect(parsed.contains("epoch_diagnostics"),
                "JSON contains epoch_diagnostics");
    test.expect(parsed.contains("sorting_diagnostics"),
                "JSON contains sorting_diagnostics");
    test.expect(parsed.contains("writer_diagnostics"),
                "JSON contains writer_diagnostics");
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
