#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include <arrow/array.h>
#include <arrow/builder.h>
#include <arrow/io/file.h>
#include <arrow/table.h>
#include <parquet/arrow/writer.h>

#include "photon_reader.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::PhotonEvent;
using hermes_event_reconstructor::readPhotonEvents;

// Writes a photon_events Parquet file with the photon writer's column layout,
// including the tot and quality_flags columns the reader ignores.
void writePhotonFile(const std::string& path,
                     const std::vector<PhotonEvent>& photons) {
    arrow::UInt64Builder id_builder;
    arrow::DoubleBuilder x_builder;
    arrow::DoubleBuilder y_builder;
    arrow::DoubleBuilder time_builder;
    arrow::UInt64Builder tot_builder;
    arrow::UInt16Builder flags_builder;
    for (const auto& photon : photons) {
        (void)id_builder.Append(photon.photon_id);
        (void)x_builder.Append(photon.x);
        (void)y_builder.Append(photon.y);
        (void)time_builder.Append(photon.timestamp_canonical);
        (void)tot_builder.Append(0);
        (void)flags_builder.Append(0);
    }

    std::shared_ptr<arrow::Array> id_array;
    std::shared_ptr<arrow::Array> x_array;
    std::shared_ptr<arrow::Array> y_array;
    std::shared_ptr<arrow::Array> time_array;
    std::shared_ptr<arrow::Array> tot_array;
    std::shared_ptr<arrow::Array> flags_array;
    (void)id_builder.Finish(&id_array);
    (void)x_builder.Finish(&x_array);
    (void)y_builder.Finish(&y_array);
    (void)time_builder.Finish(&time_array);
    (void)tot_builder.Finish(&tot_array);
    (void)flags_builder.Finish(&flags_array);

    auto schema = arrow::schema({
        arrow::field("photon_id", arrow::uint64()),
        arrow::field("x", arrow::float64()),
        arrow::field("y", arrow::float64()),
        arrow::field("timestamp_canonical", arrow::float64()),
        arrow::field("tot", arrow::uint64()),
        arrow::field("quality_flags", arrow::uint16()),
    });
    auto table = arrow::Table::Make(
        schema, {id_array, x_array, y_array, time_array, tot_array, flags_array});

    auto outfile = arrow::io::FileOutputStream::Open(path).ValueOrDie();
    (void)parquet::arrow::WriteTable(*table, arrow::default_memory_pool(),
                                     outfile, photons.size() + 1);
}

}  // namespace

int main() {
    TestContext test;

    const auto base = std::filesystem::temp_directory_path() /
                      "hermes_photon_reader_tests";
    std::filesystem::remove_all(base);
    std::filesystem::create_directories(base);

    // Rows are written out of time order, with a tie at t=1005 whose photon_id
    // order is reversed, so the reader must sort by time then photon_id.
    const auto photon_file =
        (base / "raw-chip-0-photon-events-part-00000.parquet").string();
    writePhotonFile(photon_file, {
                                     PhotonEvent{0, 10.0, 20.0, 1010.0},
                                     PhotonEvent{1, 11.0, 21.0, 1000.0},
                                     PhotonEvent{3, 12.0, 22.0, 1005.0},
                                     PhotonEvent{2, 13.0, 23.0, 1005.0},
                                 });

    std::vector<PhotonEvent> rows;
    std::vector<std::string> errors;
    const bool ok = readPhotonEvents(photon_file, rows, errors);
    test.expect(ok, "reading succeeds");
    test.expect(errors.empty(), "no errors on a clean read");
    test.expectEqual(rows.size(), std::size_t{4}, "four rows read");

    if (rows.size() == 4) {
        // Sorted order: t=1000, then the t=1005 tie by photon_id (2 before 3),
        // then t=1010.
        test.expectEqual(rows[0].timestamp_canonical, 1000.0, "row 0 time");
        test.expectEqual(rows[0].photon_id, std::uint64_t{1}, "row 0 id");
        test.expectEqual(rows[1].timestamp_canonical, 1005.0, "row 1 time");
        test.expectEqual(rows[1].photon_id, std::uint64_t{2},
                         "tie broken by photon_id (lower first)");
        test.expectEqual(rows[2].timestamp_canonical, 1005.0, "row 2 time");
        test.expectEqual(rows[2].photon_id, std::uint64_t{3}, "row 2 id");
        test.expectEqual(rows[3].timestamp_canonical, 1010.0, "row 3 time");

        // Column mapping is correct: the row that sorted first came from the
        // written photon with x=11, y=21.
        test.expectEqual(rows[0].x, 11.0, "row 0 x maps from photon_id 1");
        test.expectEqual(rows[0].y, 21.0, "row 0 y maps from photon_id 1");
    }

    // A missing file is a read failure that reports an error and clears output.
    std::vector<PhotonEvent> missing_rows{PhotonEvent{}};
    std::vector<std::string> missing_errors;
    const bool missing_ok = readPhotonEvents(
        (base / "does-not-exist.parquet").string(), missing_rows,
        missing_errors);
    test.expect(!missing_ok, "reading a missing file fails");
    test.expect(!missing_errors.empty(), "a read failure appends an error");
    test.expect(missing_rows.empty(), "output is cleared on read failure");

    // A file missing a required column is a read failure.
    const auto bad_file = (base / "bad-columns.parquet").string();
    {
        arrow::UInt64Builder only_id;
        (void)only_id.Append(0);
        std::shared_ptr<arrow::Array> id_array;
        (void)only_id.Finish(&id_array);
        auto schema = arrow::schema({arrow::field("photon_id", arrow::uint64())});
        auto table = arrow::Table::Make(schema, {id_array});
        auto outfile = arrow::io::FileOutputStream::Open(bad_file).ValueOrDie();
        (void)parquet::arrow::WriteTable(*table, arrow::default_memory_pool(),
                                         outfile, 2);
    }
    std::vector<PhotonEvent> bad_rows;
    std::vector<std::string> bad_errors;
    const bool bad_ok = readPhotonEvents(bad_file, bad_rows, bad_errors);
    test.expect(!bad_ok, "a file missing a column fails");
    test.expect(!bad_errors.empty(), "the missing column is reported");

    std::filesystem::remove_all(base);
    return test.finish();
}
