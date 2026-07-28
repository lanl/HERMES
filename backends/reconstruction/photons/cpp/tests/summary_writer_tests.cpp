#include <cstdint>
#include <string>

#include <nlohmann/json.hpp>

#include "summary_writer.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::ReconstructionSummaryContent;
using hermes_photon_clusterer::generateReconstructionSummaryJson;

// A content struct whose counts satisfy the summary's cross-field validators:
// pixel_rows_below_min_tot <= pixel_rows_read, photon_count +
// rejected_component_count == components_formed, and quality flags <=
// photon_count.
ReconstructionSummaryContent consistentContent() {
    ReconstructionSummaryContent content;
    content.pixel_rows_read = 1000;
    content.pixel_rows_below_min_tot = 40;
    content.components_formed = 100;
    content.photon_count = 70;
    content.rejected_component_count = 30;
    content.rejection_counts.below_min_cluster_size = 10;
    content.rejection_counts.above_max_aspect_ratio = 25;
    content.saturated_pixel_count = 5;
    content.bridged_components_count = 3;

    content.settings.max_time_spread_ticks = 491520;
    content.settings.min_cluster_size = 2;
    content.settings.max_cluster_size = 64;
    content.settings.min_pixel_tot_raw = 1;
    content.settings.min_cluster_tot_raw = 2;
    content.settings.max_cluster_tot_raw = 65472;
    content.settings.max_aspect_ratio = 3.0;
    content.settings.min_filled_fraction = 0.5;
    content.settings.adjacency = 8;

    content.input_pixel_data_files = {"pixelHits/raw-chip-0-part-00000.parquet"};
    content.photon_events_row_count = 70;
    content.photon_events_files = {
        "photons/raw-chip-0-photon-events-part-00000.parquet"};
    content.photon_pixels_requested = false;

    content.total_seconds = 2.0;
    content.parquet_reading_seconds = 0.5;
    content.clustering_and_filtering_seconds = 1.0;
    content.parquet_writing_seconds = 0.5;
    return content;
}

}  // namespace

int main() {
    TestContext test;

    // Uncorrected timing: correction_model "none" with no calibration details.
    {
        auto content = consistentContent();
        content.photon_timing.correction_model = "none";
        const auto text = generateReconstructionSummaryJson(content);
        auto j = nlohmann::json::parse(text);

        test.expectEqual(j["schema_version"].get<int>(), 1, "schema_version");
        test.expectEqual(j["reconstruction"]["photon_count"].get<int>(), 70,
                         "photon_count rendered");
        test.expectEqual(
            j["reconstruction"]["rejection_counts"]["above_max_aspect_ratio"]
                .get<int>(),
            25, "rejection count rendered");
        test.expectEqual(
            j["reconstruction"]["quality_flag_counts"]["saturated_pixel"]
                .get<int>(),
            5, "quality flag count rendered");
        test.expect(j["photon_timing"]["calibration_file"].is_null(),
                    "no calibration file when uncorrected");
        test.expect(j["photon_timing"]["high_tot_anchor"].is_null(),
                    "no anchor when uncorrected");
        test.expect(j["photon_timing"]["parameters"].empty(),
                    "no parameters when uncorrected");
        test.expect(j["clustering"]["settings"]["timewalk_calibration_file"]
                        .is_null(),
                    "settings calibration file null when uncorrected");
        // Throughput derived from counts and total time.
        test.expect(j["processing_times_seconds"]["throughput"]
                            ["pixels_per_second"]
                        .get<double>() == 500.0,
                    "pixels_per_second derived");
        test.expect(j["processing_times_seconds"]["throughput"]
                            ["photons_per_second"]
                        .get<double>() == 35.0,
                    "photons_per_second derived");
    }

    // Inverse correction: model, calibration file, parameters, and anchor set.
    {
        auto content = consistentContent();
        content.photon_timing.correction_model = "inverse";
        content.photon_timing.calibration_file =
            "calibrations/tpx3/time-walk_example.json";
        content.photon_timing.parameters = {{"a", 1254855.58}, {"b", 10.6986}};
        content.photon_timing.has_high_tot_anchor = true;
        content.photon_timing.high_tot_anchor = 23.0;
        content.settings.timewalk_calibration_file =
            "calibrations/tpx3/time-walk_example.json";

        const auto text = generateReconstructionSummaryJson(content);
        auto j = nlohmann::json::parse(text);
        test.expect(j["photon_timing"]["correction_model"].get<std::string>() ==
                        "inverse",
                    "correction_model rendered");
        test.expect(!j["photon_timing"]["calibration_file"].is_null(),
                    "calibration file present when corrected");
        test.expect(j["photon_timing"]["parameters"]["a"].get<double>() ==
                        1254855.58,
                    "correction parameter a rendered");
        test.expect(j["photon_timing"]["high_tot_anchor"].get<double>() == 23.0,
                    "anchor rendered when corrected");
    }

    // Zero total time yields zero throughput without dividing by zero.
    {
        auto content = consistentContent();
        content.total_seconds = 0.0;
        auto j = nlohmann::json::parse(
            generateReconstructionSummaryJson(content));
        test.expect(j["processing_times_seconds"]["throughput"]
                            ["pixels_per_second"]
                        .get<double>() == 0.0,
                    "zero total time gives zero throughput");
    }

    return test.finish();
}
