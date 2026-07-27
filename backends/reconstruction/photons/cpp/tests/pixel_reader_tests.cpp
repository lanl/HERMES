#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include <arrow/array.h>
#include <arrow/builder.h>
#include <arrow/io/file.h>
#include <arrow/table.h>
#include <parquet/arrow/writer.h>

#include "pixel_reader.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::discoverPixelFiles;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::readPixelHits;
using hermes_photon_clusterer::readPixelHitsFiltered;

// Writes a pixel_data Parquet file with the unpacker's column layout.
void writePixelFile(const std::string& path,
                    const std::vector<PixelHit>& hits) {
    arrow::UInt64Builder chunk_builder;
    arrow::UInt64Builder packet_builder;
    arrow::UInt16Builder x_builder;
    arrow::UInt16Builder y_builder;
    arrow::UInt16Builder tot_builder;
    arrow::UInt64Builder time_builder;
    for (const auto& hit : hits) {
        (void)chunk_builder.Append(0);
        (void)packet_builder.Append(0);
        (void)x_builder.Append(hit.x);
        (void)y_builder.Append(hit.y);
        (void)tot_builder.Append(hit.tot_raw);
        (void)time_builder.Append(hit.timestamp_canonical);
    }

    std::shared_ptr<arrow::Array> chunk_array;
    std::shared_ptr<arrow::Array> packet_array;
    std::shared_ptr<arrow::Array> x_array;
    std::shared_ptr<arrow::Array> y_array;
    std::shared_ptr<arrow::Array> tot_array;
    std::shared_ptr<arrow::Array> time_array;
    (void)chunk_builder.Finish(&chunk_array);
    (void)packet_builder.Finish(&packet_array);
    (void)x_builder.Finish(&x_array);
    (void)y_builder.Finish(&y_array);
    (void)tot_builder.Finish(&tot_array);
    (void)time_builder.Finish(&time_array);

    auto schema = arrow::schema({
        arrow::field("chunk_index", arrow::uint64()),
        arrow::field("packet_index", arrow::uint64()),
        arrow::field("local_x", arrow::uint16()),
        arrow::field("local_y", arrow::uint16()),
        arrow::field("tot_raw", arrow::uint16()),
        arrow::field("timestamp_canonical", arrow::uint64()),
    });
    auto table = arrow::Table::Make(
        schema, {chunk_array, packet_array, x_array, y_array, tot_array,
                 time_array});

    auto outfile = arrow::io::FileOutputStream::Open(path).ValueOrDie();
    (void)parquet::arrow::WriteTable(*table, arrow::default_memory_pool(),
                                     outfile, hits.size() + 1);
}

}  // namespace

int main() {
    TestContext test;

    const auto base = std::filesystem::temp_directory_path() /
                      "hermes_pixel_reader_tests";
    std::filesystem::remove_all(base);
    std::filesystem::create_directories(base);

    // Two contiguous parts for one chip, read back in part order.
    writePixelFile((base / "raw-chip-0-part-00000.parquet").string(),
                   {PixelHit{10, 20, 100, 1000}, PixelHit{11, 20, 90, 1005}});
    writePixelFile((base / "raw-chip-0-part-00001.parquet").string(),
                   {PixelHit{12, 20, 80, 1010}});
    // A file for a different stem must be ignored.
    writePixelFile((base / "other-chip-0-part-00000.parquet").string(),
                   {PixelHit{0, 0, 1, 1}});

    auto groups = discoverPixelFiles(base.string(), "raw");
    test.expect(groups.errors.empty(), "discovery reports no errors");
    test.expect(groups.files_by_chip.count(0) == 1, "chip 0 discovered");
    test.expectEqual(groups.files_by_chip[0].size(), std::size_t{2},
                     "two parts discovered for chip 0");

    std::vector<PixelHit> read_hits;
    std::vector<std::string> errors;
    const bool ok = readPixelHits(
        groups.files_by_chip[0],
        [&](const PixelHit& hit) { read_hits.push_back(hit); }, errors);
    test.expect(ok, "reading succeeds");
    test.expectEqual(read_hits.size(), std::size_t{3}, "three rows read");
    if (read_hits.size() == 3) {
        test.expectEqual(read_hits[0].x, std::uint16_t{10}, "row 0 x");
        test.expectEqual(read_hits[0].tot_raw, std::uint16_t{100}, "row 0 tot");
        test.expectEqual(read_hits[0].timestamp_canonical,
                         std::uint64_t{1000}, "row 0 timestamp");
        test.expectEqual(read_hits[2].timestamp_canonical,
                         std::uint64_t{1010}, "row 2 timestamp (part 1)");
    }

    // The per-pixel min-ToT filter drops low-ToT noise rows as they are read.
    std::vector<PixelHit> kept_hits;
    std::uint64_t rejected = 0;
    std::vector<std::string> filter_errors;
    const bool filter_ok = readPixelHitsFiltered(
        groups.files_by_chip[0], 90,
        [&](const PixelHit& hit) { kept_hits.push_back(hit); }, rejected,
        filter_errors);
    test.expect(filter_ok, "filtered reading succeeds");
    // Rows have ToT 100, 90, 80; min 90 keeps the first two, drops the last.
    test.expectEqual(kept_hits.size(), std::size_t{2}, "two rows kept at min 90");
    test.expectEqual(rejected, std::uint64_t{1}, "one row rejected at min 90");
    for (const auto& hit : kept_hits) {
        test.expect(hit.tot_raw >= 90, "kept rows meet the ToT threshold");
    }

    // A non-contiguous part set is rejected.
    const auto gap = base / "gap";
    std::filesystem::create_directories(gap);
    writePixelFile((gap / "raw-chip-0-part-00000.parquet").string(),
                   {PixelHit{0, 0, 1, 1}});
    writePixelFile((gap / "raw-chip-0-part-00002.parquet").string(),
                   {PixelHit{0, 0, 1, 2}});
    auto gap_groups = discoverPixelFiles(gap.string(), "raw");
    test.expect(!gap_groups.errors.empty(),
                "non-contiguous parts report an error");

    std::filesystem::remove_all(base);
    return test.finish();
}
