#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include <nlohmann/json.hpp>

#include "summary_writer.h"
#include "test_helpers.h"
#include "timewalk.h"

namespace {

using hermes_photon_clusterer::ReconstructionSummaryContent;
using hermes_photon_clusterer::TimewalkCorrection;
using hermes_photon_clusterer::generateReconstructionSummaryJson;
using hermes_photon_clusterer::writeReconstructionSummaryJson;

std::string readFile(const std::string& path) {
    std::ifstream in(path);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

// A content struct whose counts satisfy the summary's cross-field relationships:
// total_photons + rejected_clusters == clusters_formed and quality flags <=
// total_photons. It also carries the run identity, an inverse time-walk
// correction, and the input/output Parquet paths the summary reports.
ReconstructionSummaryContent consistentContent() {
    ReconstructionSummaryContent content;
    content.measurement_id = "harness-test";
    content.run = "unit-run";

    content.pixels_read = 1000;
    content.clusters_formed = 100;
    content.total_photons = 70;
    content.rejected_clusters = 30;
    content.rejection_reasons.below_min_cluster_size = 10;
    content.rejection_reasons.above_max_aspect_ratio = 25;
    content.saturated_pixel_count = 5;
    content.bridged_components_count = 3;

    content.clustering_algorithm = "connected_components";
    content.settings.timewalk_calibration_file =
        "calibrations/tpx3/time-walk_example.json";
    content.settings.save_photon_pixels = true;

    content.photon_time_estimator = "leading_edge";
    content.has_correction = true;
    content.correction.model = TimewalkCorrection::Model::kInverse;
    content.correction.a = 382443.0;
    content.correction.b = 3.98;
    content.correction.high_tot_anchor = 83.0;

    content.input_pixel_data_file =
        "analysis/pixel_hits/Example_chip_0_pixels_00000.parquet";
    content.photons_file = "analysis/photons/Example_photon_00000.parquet";
    content.photons_row_count = 70;
    content.pixel_clusters_requested = true;
    content.pixel_clusters_file =
        "analysis/pixel_clusters/Example_pixel_clusters_00000.parquet";
    content.pixel_clusters_row_count = 900;

    content.total_seconds = 2.0;
    content.parquet_reading_seconds = 0.5;
    content.clustering_and_filtering_seconds = 1.0;
    content.parquet_writing_seconds = 0.5;
    return content;
}

}  // namespace

int main() {
    TestContext test;

    // Counts, rejection/quality tallies, settings echo, timing, file lists, and
    // derived throughput render into the expected structure.
    {
        auto content = consistentContent();
        const auto text = generateReconstructionSummaryJson(content);
        auto j = nlohmann::json::parse(text);

        test.expectEqual(
            j["measurement_info"]["measurement_id"].get<std::string>(),
            std::string("harness-test"), "measurement_id rendered");
        test.expectEqual(j["measurement_info"]["run"].get<std::string>(),
                         std::string("unit-run"), "run rendered");

        test.expectEqual(j["reconstruction"]["pixels_read"].get<int>(), 1000,
                         "pixels_read rendered");
        test.expectEqual(j["reconstruction"]["clusters_formed"].get<int>(), 100,
                         "clusters_formed rendered");
        test.expectEqual(j["reconstruction"]["rejected_clusters"].get<int>(), 30,
                         "rejected_clusters rendered");
        test.expectEqual(j["reconstruction"]["total_photons"].get<int>(), 70,
                         "total_photons rendered");
        test.expectEqual(
            j["reconstruction"]["rejection_reasons"]["above_max_aspect_ratio"]
                .get<int>(),
            25, "rejection reason rendered");
        test.expectEqual(
            j["reconstruction"]["quality_flag_counts"]["saturated_pixel"]
                .get<int>(),
            5, "quality flag count rendered");
        // The slimmed schema drops the schema_version tag and the low-ToT count.
        test.expect(!j.contains("schema_version"), "no schema_version tag");
        test.expect(!j["reconstruction"].contains("pixel_rows_below_min_tot"),
                    "no low-ToT pixel count");

        // Clustering echo carries the algorithm and the full settings block.
        test.expectEqual(j["clustering"]["algorithm"].get<std::string>(),
                         std::string("connected_components"),
                         "clustering algorithm rendered");
        test.expectEqual(
            j["clustering"]["settings"]["timewalk_calibration_file"]
                .get<std::string>(),
            std::string("calibrations/tpx3/time-walk_example.json"),
            "settings calibration path rendered");
        test.expect(
            j["clustering"]["settings"]["save_photon_pixels"].get<bool>(),
            "settings save_photon_pixels rendered");

        // Photon timing carries the correction model and fitted parameters.
        test.expectEqual(
            j["photon_timing"]["correction_model"].get<std::string>(),
            std::string("inverse"), "correction model rendered");
        test.expectEqual(j["photon_timing"]["parameters"]["a"].get<double>(),
                         382443.0, "correction parameter a rendered");
        test.expectEqual(j["photon_timing"]["high_tot_anchor"].get<double>(),
                         83.0, "high_tot_anchor rendered");

        // Parquet file lists report the input path and the written outputs.
        test.expectEqual(
            j["parquet_files"]["input_pixel_data_file"][0].get<std::string>(),
            std::string(
                "analysis/pixel_hits/Example_chip_0_pixels_00000.parquet"),
            "input path rendered");
        test.expectEqual(
            j["parquet_files"]["photons"]["files"][0].get<std::string>(),
            std::string("analysis/photons/Example_photon_00000.parquet"),
            "photon path rendered");
        test.expectEqual(
            j["parquet_files"]["photons"]["row_count"].get<int>(), 70,
            "photon row count rendered");
        test.expect(
            j["parquet_files"]["pixel_clusters"]["requested"].get<bool>(),
            "pixel_clusters requested rendered");
        test.expectEqual(
            j["parquet_files"]["pixel_clusters"]["row_count"].get<int>(), 900,
            "pixel_clusters row count rendered");

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

    // With no correction the photon_timing block reports "none" with empty
    // parameters and null calibration path and anchor.
    {
        auto content = consistentContent();
        content.has_correction = false;
        content.settings.timewalk_calibration_file.clear();
        auto j = nlohmann::json::parse(
            generateReconstructionSummaryJson(content));
        test.expectEqual(
            j["photon_timing"]["correction_model"].get<std::string>(),
            std::string("none"), "correction model none");
        test.expect(j["photon_timing"]["calibration_file"].is_null(),
                    "null calibration file");
        test.expect(j["photon_timing"]["parameters"].empty(),
                    "empty timing parameters");
        test.expect(j["photon_timing"]["high_tot_anchor"].is_null(),
                    "null high_tot_anchor");
        test.expect(
            j["clustering"]["settings"]["timewalk_calibration_file"].is_null(),
            "null settings calibration path");
    }

    // An unwritten pixel-clusters table has zero files and a zero row count.
    {
        auto content = consistentContent();
        content.pixel_clusters_file.clear();
        content.pixel_clusters_row_count = 0;
        auto j = nlohmann::json::parse(
            generateReconstructionSummaryJson(content));
        test.expect(j["parquet_files"]["pixel_clusters"]["files"].empty(),
                    "empty pixel_clusters file list");
        test.expectEqual(
            j["parquet_files"]["pixel_clusters"]["row_count"].get<int>(), 0,
            "zero pixel_clusters row count");
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

    // overwrite == false refuses an existing summary; overwrite == true replaces.
    {
        const auto base = std::filesystem::temp_directory_path() /
                           "hermes_summary_writer_tests";
        std::filesystem::remove_all(base);
        std::filesystem::create_directories(base);
        const auto path = (base / "summary.json").string();

        auto content = consistentContent();
        writeReconstructionSummaryJson(path, content, false);
        test.expect(std::filesystem::exists(path), "summary written initially");

        // A second write with overwrite == false must throw.
        bool refused = false;
        try {
            writeReconstructionSummaryJson(path, content, false);
        } catch (const std::exception&) {
            refused = true;
        }
        test.expect(refused, "overwrite == false refuses existing summary");

        // With overwrite == true the file is replaced with the new content.
        auto replacement = consistentContent();
        replacement.total_photons = 12;
        replacement.rejected_clusters = 88;  // keeps clusters_formed
        writeReconstructionSummaryJson(path, replacement, true);
        auto j = nlohmann::json::parse(readFile(path));
        test.expectEqual(j["reconstruction"]["total_photons"].get<int>(), 12,
                         "overwrite == true replaces the summary content");

        std::filesystem::remove_all(base);
    }

    return test.finish();
}
