#include "test_helpers.h"
#include "unpacker.h"
#include "summary_json.h"

#include <sstream>

using namespace hermes_tpx3_spidr;

namespace {

void testWorkflowWithEmptyInput(TestContext& test) {
    std::istringstream input("");
    const auto result = runTwoPassWorkflow(input, "/tmp/test_output");

    test.expect(result.success, "workflow succeeded with empty input");
    test.expectEqual(result.output_directory, std::string("/tmp/test_output"),
                     "output directory preserved");
    test.expectEqual(result.summary.status, std::string("complete"),
                     "status set to complete");
}

void testWorkflowWithSingleChunk(TestContext& test) {
    std::string bytes;
    const auto header = makeChunkHeader(0, 0, 8);
    appendLittleEndianWord(bytes, header);

    std::istringstream input(bytes);
    const auto result = runTwoPassWorkflow(input, "/tmp/test_output");

    test.expect(result.success, "workflow succeeded with single chunk");
    test.expectEqual(result.summary.unpack_summary.chunks_read,
                     std::uint64_t{1}, "one chunk read");
    test.expectEqual(result.summary.unpack_summary.packets_read,
                     std::uint64_t{0}, "zero packets in empty chunk");
}

void testWorkflowWithPixelPacket(TestContext& test) {
    std::string bytes;
    const auto header = makeChunkHeader(0, 0, 16);
    appendLittleEndianWord(bytes, header);

    const std::uint64_t pixel_packet = 0xB000000000000000ULL |
                                       (0x0100ULL << 44U) |
                                       (0x0200ULL << 30U) |
                                       (0x0050ULL << 16U) |
                                       0x1234ULL;
    appendLittleEndianWord(bytes, pixel_packet);

    std::istringstream input(bytes);
    const auto result = runTwoPassWorkflow(input, "/tmp/test_output");

    test.expect(result.success, "workflow succeeded with pixel packet");
    test.expectEqual(result.summary.unpack_summary.pixel_hit_count,
                     std::uint64_t{1}, "one pixel hit decoded");
}

void testSummaryJsonGeneration(TestContext& test) {
    SummaryJsonContent content;
    content.backend_name = "test-backend";
    content.backend_version = "1.0.0";
    content.source_file_path = "/tmp/test.tpx3";
    content.output_directory = "/tmp/output";
    content.status = "complete";

    const auto json_str = generateSummaryJson(content);

    test.expect(json_str.find("\"backend\"") != std::string::npos,
                "JSON contains backend section");
    test.expect(json_str.find("\"test-backend\"") != std::string::npos,
                "JSON contains backend name");
    test.expect(json_str.find("\"source\"") != std::string::npos,
                "JSON contains source section");
    test.expect(json_str.find("\"output\"") != std::string::npos,
                "JSON contains output section");
    test.expect(json_str.find("\"complete\"") != std::string::npos,
                "JSON contains status");
}

void testSummaryJsonStructure(TestContext& test) {
    SummaryJsonContent content;
    content.unpack_summary.bytes_read = 1024;
    content.unpack_summary.chunks_read = 10;
    content.unpack_summary.packets_read = 100;

    const auto json_str = generateSummaryJson(content);

    test.expect(json_str.find("\"unpack_summary\"") != std::string::npos,
                "JSON contains unpack_summary");
    test.expect(json_str.find("\"anchor_diagnostics\"") != std::string::npos,
                "JSON contains anchor_diagnostics");
    test.expect(json_str.find("\"epoch_diagnostics\"") != std::string::npos,
                "JSON contains epoch_diagnostics");
    test.expect(json_str.find("\"sorting_diagnostics\"") != std::string::npos,
                "JSON contains sorting_diagnostics");
    test.expect(json_str.find("\"writer_diagnostics\"") != std::string::npos,
                "JSON contains writer_diagnostics");
}

void testWorkflowErrorHandling(TestContext& test) {
    std::string bytes;
    const auto malformed_header = 0x12345678ABCDEF00ULL;
    appendLittleEndianWord(bytes, malformed_header);

    std::istringstream input(bytes);
    const auto result = runTwoPassWorkflow(input, "/tmp/test_output");

    test.expect(result.summary.unpack_summary.malformed_chunk_count > 0,
                "malformed chunks detected");
    test.expect(!result.summary.unpack_summary.errors.empty(),
                "errors recorded in summary");
}

}  // namespace

int main() {
    TestContext test;
    testWorkflowWithEmptyInput(test);
    testWorkflowWithSingleChunk(test);
    testWorkflowWithPixelPacket(test);
    testSummaryJsonGeneration(test);
    testSummaryJsonStructure(test);
    testWorkflowErrorHandling(test);
    return test.finish();
}
