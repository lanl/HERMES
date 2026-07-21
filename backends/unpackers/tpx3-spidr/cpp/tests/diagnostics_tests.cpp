#include "test_helpers.h"

#include <sstream>
#include <string>

#include "diagnostics.h"

int main() {
    TestContext test;
    hermes_tpx3_spidr::UnpackSummary summary;
    summary.bytes_read = 24U;
    summary.chunks_read = 2U;
    summary.packets_read = 3U;
    summary.pixel_hit_count = 1U;
    summary.tdc1_rising_count = 1U;
    summary.shutter_open_count = 1U;
    summary.unknown_tpx3_control_count = 1U;
    summary.warnings.push_back("example warning");
    summary.errors.push_back("example error");

    std::ostringstream summary_output;
    hermes_tpx3_spidr::printSummary(summary, summary_output);
    const auto text = summary_output.str();
    test.expect(text.find("bytes=24 chunks=2 packets=3") != std::string::npos,
                "diagnostics file counts");
    test.expect(text.find("pixel_hits=1") != std::string::npos,
                "diagnostics pixel count");
    test.expect(text.find("tdc1_rising=1") != std::string::npos,
                "diagnostics TDC subtype");
    test.expect(text.find("shutter_open=1") != std::string::npos,
                "diagnostics SPIDR subtype");
    test.expect(text.find("unknown_tpx3=1") != std::string::npos,
                "diagnostics TPX3 subtype");
    test.expect(text.find("warnings=1 errors=1") != std::string::npos,
                "diagnostics message counts");

    std::ostringstream messages;
    hermes_tpx3_spidr::printMessages(summary, messages);
    test.expect(messages.str() ==
                    "Warning: example warning\nError: example error\n",
                "diagnostics warning and error text");
    return test.finish();
}
