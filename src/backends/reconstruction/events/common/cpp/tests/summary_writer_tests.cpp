#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include <nlohmann/json.hpp>

#include "summary_writer.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::EventReconstructionSummaryContent;
using hermes_event_reconstructor::generateEventReconstructionSummaryJson;
using hermes_event_reconstructor::writeEventReconstructionSummaryJson;

std::string readFile(const std::string& path) {
    std::ifstream in(path);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

// Content with representative counts, the default settings, and one input and
// output file listed.
EventReconstructionSummaryContent sampleContent() {
    EventReconstructionSummaryContent content;
    content.photons_read = 1000;
    content.components_formed = 400;
    content.event_count = 400;
    content.single_photon_count = 320;
    content.duration_exceeded_count = 5;
    content.min_photon_count_below = 0;

    // The clustering program owns its settings shape and hands it in as a JSON
    // object string; the common writer renders it verbatim. This mirrors what
    // connected-components produces (its six settings plus the derived cell
    // width), but the common library stays neutral about the fields.
    content.clustering_algorithm = "connected_components";
    content.clustering_settings_json =
        R"({"spatial_link_radius_pixels":10.0,)"
        R"("spatial_cells_per_axis":5,)"
        R"("max_time_difference_ticks":4915200.0,)"
        R"("max_event_duration_ticks":14745600.0,)"
        R"("min_photon_count":1,)"
        R"("save_event_photons":false,)"
        R"("derived_cell_width":52})";

    content.input_photon_events_files = {
        "rawCdI_000000-chip-0-photon-events-part-00000.parquet"};
    content.event_candidates_row_count = 400;
    content.event_candidates_files = {
        "rawCdI_000000-chip-0-event-candidates-part-00000.parquet"};

    content.photon_reading_seconds = 0.5;
    content.clustering_seconds = 1.0;
    content.parquet_writing_seconds = 0.5;
    content.total_seconds = 2.0;
    return content;
}

}  // namespace

int main() {
    TestContext test;

    // The structure, counts, provenance, and derived throughput render.
    {
        const auto content = sampleContent();
        const auto text = generateEventReconstructionSummaryJson(content);
        auto j = nlohmann::json::parse(text);

        test.expectEqual(j["schema_version"].get<int>(), 1, "schema_version");

        const auto& r = j["reconstruction"];
        test.expectEqual(r["photons_read"].get<int>(), 1000, "photons_read");
        test.expectEqual(r["components_formed"].get<int>(), 400,
                         "components_formed");
        test.expectEqual(r["event_count"].get<int>(), 400, "event_count");
        test.expectEqual(r["quality_flag_counts"]["single_photon"].get<int>(),
                         320, "single_photon count");
        test.expectEqual(
            r["quality_flag_counts"]["duration_exceeded"].get<int>(), 5,
            "duration_exceeded count");
        test.expectEqual(r["min_photon_count_below"].get<int>(), 0,
                         "min_photon_count_below");
        test.expect(r["warnings"].is_array() && r["warnings"].empty(),
                    "warnings is an empty array");
        test.expect(r["errors"].is_array() && r["errors"].empty(),
                    "errors is an empty array");

        const auto& c = j["clustering"];
        test.expectEqual(c["algorithm"].get<std::string>(),
                         std::string("connected_components"), "algorithm");
        // Settings provenance: the defaults locked in earlier plus derived width.
        const auto& cs = c["settings"];
        test.expectEqual(cs["spatial_link_radius_pixels"].get<double>(), 10.0,
                         "settings link radius");
        test.expectEqual(cs["max_time_difference_ticks"].get<double>(),
                         4915200.0, "settings time link");
        test.expectEqual(cs["max_event_duration_ticks"].get<double>(),
                         14745600.0, "settings duration threshold");
        test.expectEqual(cs["spatial_cells_per_axis"].get<int>(), 5,
                         "settings cells per axis");
        test.expectEqual(cs["min_photon_count"].get<int>(), 1,
                         "settings min_photon_count");
        test.expect(!cs["save_event_photons"].get<bool>(),
                    "settings save_event_photons default false");
        test.expectEqual(cs["derived_cell_width"].get<int>(), 52,
                         "derived cell width recorded");

        test.expectEqual(j["event_timing"]["estimator"].get<std::string>(),
                         std::string("earliest_photon"), "time estimator");

        const auto& p = j["parquet"];
        test.expectEqual(p["input_photon_events_files"].size(), std::size_t{1},
                         "one input file listed");
        test.expectEqual(p["event_candidates"]["row_count"].get<int>(), 400,
                         "event_candidates row_count");
        test.expectEqual(p["event_candidates"]["files"].size(), std::size_t{1},
                         "one event_candidates file listed");
        // event_photons is absent when no such file was written.
        test.expect(!p.contains("event_photons"),
                    "event_photons omitted when not written");

        const auto& t = j["processing_times_seconds"];
        test.expectEqual(t["total"].get<double>(), 2.0, "total time");
        // Throughput derives from counts / total time.
        test.expectEqual(t["throughput"]["photons_per_second"].get<double>(),
                         500.0, "photons per second");
        test.expectEqual(t["throughput"]["events_per_second"].get<double>(),
                         200.0, "events per second");
    }

    // Throughput is zero when total time is zero (no division by zero).
    {
        auto content = sampleContent();
        content.total_seconds = 0.0;
        const auto text = generateEventReconstructionSummaryJson(content);
        auto j = nlohmann::json::parse(text);
        const auto& t = j["processing_times_seconds"]["throughput"];
        test.expectEqual(t["photons_per_second"].get<double>(), 0.0,
                         "zero photons/s when total time is zero");
        test.expectEqual(t["events_per_second"].get<double>(), 0.0,
                         "zero events/s when total time is zero");
    }

    // event_photons is reported when that output was written.
    {
        auto content = sampleContent();
        content.event_photons_row_count = 680;
        content.event_photons_files = {
            "rawCdI_000000-chip-0-event-photons-part-00000.parquet"};
        const auto text = generateEventReconstructionSummaryJson(content);
        auto j = nlohmann::json::parse(text);
        const auto& p = j["parquet"];
        test.expect(p.contains("event_photons"),
                    "event_photons present when written");
        test.expectEqual(p["event_photons"]["row_count"].get<int>(), 680,
                         "event_photons row_count");
        test.expectEqual(p["event_photons"]["files"].size(), std::size_t{1},
                         "one event_photons file listed");
    }

    // Writing to disk, and overwrite refusal.
    {
        const auto base = std::filesystem::temp_directory_path() /
                          "hermes_event_summary_tests";
        std::filesystem::remove_all(base);
        std::filesystem::create_directories(base);
        const auto path = (base / "summary.json").string();

        writeEventReconstructionSummaryJson(path, sampleContent(), false);
        test.expect(std::filesystem::exists(path), "summary file written");
        // The written file parses and matches the generated string.
        test.expectEqual(readFile(path),
                         generateEventReconstructionSummaryJson(sampleContent()),
                         "written file matches generated JSON");

        bool refused = false;
        try {
            writeEventReconstructionSummaryJson(path, sampleContent(), false);
        } catch (const std::runtime_error&) {
            refused = true;
        }
        test.expect(refused, "refuses to overwrite without the flag");

        bool replaced = true;
        try {
            writeEventReconstructionSummaryJson(path, sampleContent(), true);
        } catch (const std::runtime_error&) {
            replaced = false;
        }
        test.expect(replaced, "overwrite with the flag succeeds");

        std::filesystem::remove_all(base);
    }

    return test.finish();
}
