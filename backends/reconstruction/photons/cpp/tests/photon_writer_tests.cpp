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
    return reader->ReadTable().ValueOrDie();
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
        const auto path = (base / "events.parquet").string();
        auto result = writePhotonEventsParquet(photons, path, sampleMetadata(),
                                               false, errors);
        test.expect(errors.empty(), "events write reports no errors");
        test.expectEqual(result.row_count, std::uint64_t{2}, "two events written");
        test.expect(result.file == path, "events written to the given path");

        auto table = readTable(path);
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

    // photon_pixels round-trips source-pixel columns.
    {
        std::vector<PhotonPixelRow> rows = {
            PhotonPixelRow{0, 3, 2, 4, 100, 1000},
            PhotonPixelRow{0, 7, 3, 4, 90, 1005},
            PhotonPixelRow{1, 9, 7, 9, 15, 500},
        };
        std::vector<std::string> errors;
        const auto path = (base / "pixels.parquet").string();
        auto result = writePhotonPixelsParquet(rows, path, sampleMetadata(),
                                               false, errors);
        test.expect(errors.empty(), "pixels write reports no errors");
        test.expectEqual(result.row_count, std::uint64_t{3}, "three pixels");
        test.expect(result.file == path, "pixels written to the given path");

        auto table = readTable(path);
        test.expectEqual(table->num_rows(), std::int64_t{3},
                         "pixels file has three rows");
        // Columns: photon_id, pixel_event_id, x, y, tot_raw, timestamp.
        test.expectEqual(uint64At(table, 0, 2), std::uint64_t{1},
                         "third pixel maps to photon 1");
        test.expectEqual(uint64At(table, 1, 0), std::uint64_t{3},
                         "pixel_event_id preserved");
    }

    // Empty inputs write no file and report no errors.
    {
        std::vector<std::string> errors;
        auto result = writePhotonEventsParquet({}, (base / "empty.parquet").string(),
                                               sampleMetadata(), false, errors);
        test.expect(errors.empty(), "empty events write has no errors");
        test.expectEqual(result.row_count, std::uint64_t{0}, "no rows");
        test.expect(result.file.empty(), "no file for empty events");
    }

    // overwrite == false refuses an existing file; overwrite == true replaces it.
    {
        const auto path = (base / "overwrite.parquet").string();
        std::vector<Photon> first = {Photon{1.0, 1.0, 1.0, 1, 0}};
        std::vector<std::string> errors;
        auto initial = writePhotonEventsParquet(first, path, sampleMetadata(),
                                                false, errors);
        test.expect(errors.empty() && initial.row_count == 1,
                    "initial events write succeeds");

        // A second write to the same file with overwrite == false must refuse.
        std::vector<std::string> refuse_errors;
        auto refused = writePhotonEventsParquet(first, path, sampleMetadata(),
                                                false, refuse_errors);
        test.expect(!refuse_errors.empty() && refused.row_count == 0,
                    "overwrite == false refuses existing photon file");

        // With overwrite == true the file is replaced with new contents.
        std::vector<Photon> second = {
            Photon{2.0, 2.0, 2.0, 2, 0},
            Photon{3.0, 3.0, 3.0, 3, 0},
        };
        std::vector<std::string> replace_errors;
        auto replaced = writePhotonEventsParquet(second, path, sampleMetadata(),
                                                 true, replace_errors);
        test.expect(replace_errors.empty() && replaced.row_count == 2,
                    "overwrite == true replaces existing photon file");
        auto table = readTable(path);
        test.expectEqual(table->num_rows(), std::int64_t{2},
                         "replaced file holds the new rows");
    }

    std::filesystem::remove_all(base);
    return test.finish();
}
