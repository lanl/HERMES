#include <cmath>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

#include <arrow/array.h>
#include <arrow/io/file.h>
#include <arrow/table.h>
#include <arrow/util/key_value_metadata.h>
#include <parquet/arrow/reader.h>

#include "photon.h"
#include "photon_writer.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::Photon;
using hermes_photon_clusterer::PhotonFileMetadata;
using hermes_photon_clusterer::PhotonPixelRow;
using hermes_photon_clusterer::writePhotonEventsParquet;
using hermes_photon_clusterer::writePhotonPixelsParquet;

// Reads an entire Parquet file into a single table.
std::shared_ptr<arrow::Table> readTable(const std::string& path) {
    auto input = arrow::io::ReadableFile::Open(path).ValueOrDie();
    auto reader =
        parquet::arrow::OpenFile(input, arrow::default_memory_pool()).ValueOrDie();
    std::shared_ptr<arrow::Table> table;
    (void)reader->ReadTable(&table);
    return table;
}

double doubleAt(const std::shared_ptr<arrow::Table>& table, int col, int row) {
    auto chunk = std::static_pointer_cast<arrow::DoubleArray>(
        table->column(col)->chunk(0));
    return chunk->Value(row);
}

std::uint64_t uint64At(const std::shared_ptr<arrow::Table>& table, int col,
                       int row) {
    auto chunk = std::static_pointer_cast<arrow::UInt64Array>(
        table->column(col)->chunk(0));
    return chunk->Value(row);
}

PhotonFileMetadata sampleMetadata() {
    PhotonFileMetadata metadata;
    metadata.raw_file_stem = "raw";
    metadata.chip_index = 0;
    metadata.canonical_tick_seconds = 25e-9 / 12288.0;
    metadata.clustering_algorithm = "connected_components";
    metadata.clustering_settings_json = R"({"adjacency":8})";
    metadata.position_averaging = "arithmetic";
    metadata.photon_time_estimator = "leading_edge";
    metadata.correction_model = "inverse";
    metadata.correction_parameters_json = R"({"a":1000.0,"b":5.0})";
    metadata.high_tot_anchor = 20.0;
    metadata.save_photon_pixels = true;
    return metadata;
}

bool nearlyEqual(double lhs, double rhs) { return std::fabs(lhs - rhs) < 1e-9; }

}  // namespace

int main() {
    TestContext test;

    const auto base =
        std::filesystem::temp_directory_path() / "hermes_photon_writer_tests";
    std::filesystem::remove_all(base);
    std::filesystem::create_directories(base);

    // photon_events round-trips with float64 x/y/timestamp and uint64 tot.
    {
        std::vector<Photon> photons = {
            Photon{2.5, 4.5, 1000.75, 100, 0},
            Photon{7.0, 9.0, 500.0, 15, 0b11},
        };
        std::vector<std::string> errors;
        const auto dir = (base / "events").string();
        auto result = writePhotonEventsParquet(photons, dir,
                                               sampleMetadata(), 1000, errors);
        test.expect(errors.empty(), "events write reports no errors");
        test.expectEqual(result.row_count, std::uint64_t{2}, "two events written");
        test.expectEqual(result.files.size(), std::size_t{1}, "one events part");

        if (result.files.size() == 1) {
            test.expect(result.files[0] ==
                            "raw-chip-0-photon-events-part-00000.parquet",
                        "events filename follows convention");
            auto table = readTable((std::filesystem::path(dir) / result.files[0]).string());
            test.expectEqual(table->num_rows(), std::int64_t{2},
                             "events file has two rows");
            // Columns: photon_id, x, y, timestamp_canonical, tot, quality_flags.
            test.expectEqual(uint64At(table, 0, 0), std::uint64_t{0},
                             "photon_id is zero-based");
            test.expect(nearlyEqual(doubleAt(table, 1, 0), 2.5), "x preserved");
            test.expect(nearlyEqual(doubleAt(table, 3, 0), 1000.75),
                        "fractional timestamp preserved as float64");
            test.expectEqual(uint64At(table, 4, 0), std::uint64_t{100},
                             "tot preserved");

            // Schema metadata is attached.
            auto metadata = table->schema()->metadata();
            test.expect(metadata != nullptr, "events schema carries metadata");
            if (metadata != nullptr) {
                test.expect(
                    metadata->Get("schema_name").ValueOr("") ==
                        "hermes_tpx3_spidr_photon_events",
                    "events schema_name metadata");
                test.expect(metadata->Get("correction_model").ValueOr("") ==
                                "inverse",
                            "correction_model metadata");
                test.expect(metadata->Get("photon_time_estimator").ValueOr("") ==
                                "leading_edge",
                            "photon_time_estimator metadata");
            }
        }
    }

    // photon_pixels round-trips source-pixel columns.
    {
        std::vector<PhotonPixelRow> rows = {
            PhotonPixelRow{0, 3, 2, 4, 100, 1000},
            PhotonPixelRow{0, 7, 3, 4, 90, 1005},
            PhotonPixelRow{1, 9, 7, 9, 15, 500},
        };
        std::vector<std::string> errors;
        const auto dir = (base / "pixels").string();
        auto result = writePhotonPixelsParquet(rows, dir,
                                               sampleMetadata(), 1000, errors);
        test.expect(errors.empty(), "pixels write reports no errors");
        test.expectEqual(result.row_count, std::uint64_t{3}, "three pixels");
        if (result.files.size() == 1) {
            test.expect(result.files[0] ==
                            "raw-chip-0-photon-pixels-part-00000.parquet",
                        "pixels filename follows convention");
            auto table = readTable((std::filesystem::path(dir) / result.files[0]).string());
            test.expectEqual(table->num_rows(), std::int64_t{3},
                             "pixels file has three rows");
            // Columns: photon_id, pixel_event_id, x, y, tot_raw, timestamp.
            test.expectEqual(uint64At(table, 0, 2), std::uint64_t{1},
                             "third pixel maps to photon 1");
            test.expectEqual(uint64At(table, 1, 0), std::uint64_t{3},
                             "pixel_event_id preserved");
        }
    }

    // Empty inputs write no files and report no errors.
    {
        std::vector<std::string> errors;
        auto result = writePhotonEventsParquet({}, (base / "empty").string(),
                                               sampleMetadata(), 1000, errors);
        test.expect(errors.empty(), "empty events write has no errors");
        test.expectEqual(result.row_count, std::uint64_t{0}, "no rows");
        test.expect(result.files.empty(), "no files for empty events");
    }

    // Multiple parts are produced when the row count exceeds rows_per_part.
    {
        std::vector<Photon> photons(5, Photon{1.0, 1.0, 1.0, 1, 0});
        std::vector<std::string> errors;
        auto result = writePhotonEventsParquet(photons, (base / "multi").string(),
                                               sampleMetadata(), 2, errors);
        test.expect(errors.empty(), "multi-part write has no errors");
        test.expectEqual(result.files.size(), std::size_t{3},
                         "five rows at two per part yields three files");
        test.expectEqual(result.row_count, std::uint64_t{5}, "row count is five");
    }

    std::filesystem::remove_all(base);
    return test.finish();
}
