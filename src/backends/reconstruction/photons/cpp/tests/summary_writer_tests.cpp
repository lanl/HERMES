#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include <nlohmann/json.hpp>

#include "summary_writer.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::ReconstructionSummaryContent;
using hermes_photon_clusterer::generateReconstructionSummaryJson;
using hermes_photon_clusterer::writeReconstructionSummaryJson;

std::string readFile(const std::string& path) {
    std::ifstream in(path);
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

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

    content.total_seconds = 2.0;
    content.parquet_reading_seconds = 0.5;
    content.clustering_and_filtering_seconds = 1.0;
    content.parquet_writing_seconds = 0.5;
    return content;
}

}  // namespace

int main() {
    TestContext test;

    // Counts, rejection/quality tallies, and derived throughput render.
    {
        auto content = consistentContent();
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
        // The slimmed summary carries no settings echo or timing provenance.
        test.expect(!j.contains("clustering"),
                    "summary omits clustering settings echo");
        test.expect(!j.contains("photon_timing"),
                    "summary omits photon_timing block");
        test.expect(!j.contains("parquet"), "summary omits parquet file lists");
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
        content.photon_count = 70;
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
        replacement.photon_count = 12;
        replacement.rejected_component_count = 88;  // keeps components_formed
        writeReconstructionSummaryJson(path, replacement, true);
        auto j = nlohmann::json::parse(readFile(path));
        test.expectEqual(j["reconstruction"]["photon_count"].get<int>(), 12,
                         "overwrite == true replaces the summary content");

        std::filesystem::remove_all(base);
    }

    return test.finish();
}
