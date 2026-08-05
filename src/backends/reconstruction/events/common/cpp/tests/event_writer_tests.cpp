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

#include "event.h"
#include "event_writer.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::CandidateEvent;
using hermes_event_reconstructor::EventFileMetadata;
using hermes_event_reconstructor::EventPhotonRow;
using hermes_event_reconstructor::kEventCandidatesSchemaName;
using hermes_event_reconstructor::kEventPhotonsSchemaName;
using hermes_event_reconstructor::writeEventCandidatesParquet;
using hermes_event_reconstructor::writeEventPhotonsParquet;

// Reads a Parquet file back into an Arrow table, preserving key-value metadata.
std::shared_ptr<arrow::Table> readTable(const std::string& path) {
    auto infile = arrow::io::ReadableFile::Open(path).ValueOrDie();
    auto reader_result =
        parquet::arrow::OpenFile(infile, arrow::default_memory_pool());
    if (!reader_result.ok()) return nullptr;
    std::unique_ptr<parquet::arrow::FileReader> reader =
        std::move(*reader_result);
    std::shared_ptr<arrow::Table> table;
    if (!reader->ReadTable(&table).ok()) return nullptr;
    return table;
}

// Looks up a key in a table schema's key-value metadata; empty if absent.
std::string metaValue(const std::shared_ptr<arrow::Table>& table,
                      const std::string& key) {
    const auto kv = table->schema()->metadata();
    if (!kv) return "";
    const int index = kv->FindKey(key);
    return index < 0 ? "" : kv->value(index);
}

EventFileMetadata sampleMetadata() {
    EventFileMetadata m;
    m.raw_file_stem = "rawCdI_000000";
    m.chip_index = 0;
    m.canonical_tick_seconds = 2.0345052083333334e-12;
    m.event_algorithm = "connected_components";
    m.event_settings_json = "{\"spatial_link_radius_pixels\":10.0}";
    m.position_rule = "arithmetic";
    m.event_time_estimator = "earliest_photon";
    m.save_event_photons = true;
    return m;
}

}  // namespace

int main() {
    TestContext test;

    const auto base = std::filesystem::temp_directory_path() /
                      "hermes_event_writer_tests";
    std::filesystem::remove_all(base);
    std::filesystem::create_directories(base);

    // A small event set: one multi-photon event and one single-photon event.
    std::vector<CandidateEvent> events(2);
    events[0].event_id = 0;
    events[0].x = 12.0;
    events[0].y = 22.0;
    events[0].timestamp_canonical = 50.0;
    events[0].photon_count = 3;
    events[0].quality_flags = 0;
    events[1].event_id = 1;
    events[1].x = 100.0;
    events[1].y = 100.0;
    events[1].timestamp_canonical = 500.0;
    events[1].photon_count = 1;
    events[1].quality_flags = 0x0001;

    const auto candidates_file =
        (base / "raw-chip-0-event-candidates-part-00000.parquet").string();
    std::vector<std::string> errors;
    const auto result = writeEventCandidatesParquet(
        events, candidates_file, sampleMetadata(), false, errors);
    test.expect(errors.empty(), "no errors writing event_candidates");
    test.expectEqual(result.row_count, std::uint64_t{2}, "two events written");

    // Round-trip: columns and values survive.
    {
        const auto table = readTable(candidates_file);
        test.expect(table != nullptr, "event_candidates file reads back");
        if (table) {
            test.expectEqual(table->num_rows(), std::int64_t{2}, "two rows back");
            test.expectEqual(table->num_columns(), 6, "six columns");
            const auto names = table->ColumnNames();
            const std::vector<std::string> expected = {
                "event_id", "x", "y", "timestamp_canonical",
                "photon_count", "quality_flags"};
            bool cols_match = names.size() == expected.size();
            for (std::size_t i = 0; cols_match && i < expected.size(); ++i) {
                cols_match = names[i] == expected[i];
            }
            test.expect(cols_match, "column names and order match the spec");

            auto ids = std::static_pointer_cast<arrow::UInt64Array>(
                table->column(0)->chunk(0));
            auto counts = std::static_pointer_cast<arrow::UInt64Array>(
                table->column(4)->chunk(0));
            auto flags = std::static_pointer_cast<arrow::UInt16Array>(
                table->column(5)->chunk(0));
            test.expectEqual(ids->Value(1), std::uint64_t{1}, "event_id round-trips");
            test.expectEqual(counts->Value(0), std::uint64_t{3},
                             "photon_count round-trips");
            test.expectEqual(flags->Value(1), std::uint16_t{0x0001},
                             "quality_flags round-trips");

            // Metadata keys are present and self-describing.
            test.expectEqual(metaValue(table, "schema_name"),
                             std::string(kEventCandidatesSchemaName),
                             "schema_name metadata");
            test.expectEqual(metaValue(table, "event_algorithm"),
                             std::string("connected_components"),
                             "event_algorithm metadata");
            test.expectEqual(metaValue(table, "position_rule"),
                             std::string("arithmetic"), "position_rule metadata");
            test.expectEqual(metaValue(table, "event_time_estimator"),
                             std::string("earliest_photon"),
                             "event_time_estimator metadata");
        }
    }

    // Overwrite refusal without the flag; replacement with it.
    {
        std::vector<std::string> refuse_errors;
        const auto refuse = writeEventCandidatesParquet(
            events, candidates_file, sampleMetadata(), false, refuse_errors);
        test.expect(refuse.file.empty(), "refuses to overwrite without the flag");
        test.expect(!refuse_errors.empty(), "refusal reports an error");

        std::vector<std::string> replace_errors;
        const auto replace = writeEventCandidatesParquet(
            events, candidates_file, sampleMetadata(), true, replace_errors);
        test.expect(replace_errors.empty(), "overwrite with the flag succeeds");
        test.expectEqual(replace.row_count, std::uint64_t{2}, "replaced rows");
    }

    // The event_photons file round-trips with its five columns.
    {
        std::vector<EventPhotonRow> rows = {
            EventPhotonRow{0, 0, 10.0, 20.0, 100.0},
            EventPhotonRow{0, 1, 14.0, 20.0, 50.0},
            EventPhotonRow{0, 2, 12.0, 26.0, 200.0},
            EventPhotonRow{1, 3, 100.0, 100.0, 500.0},
        };
        const auto photons_file =
            (base / "raw-chip-0-event-photons-part-00000.parquet").string();
        std::vector<std::string> photon_errors;
        const auto pr = writeEventPhotonsParquet(
            rows, photons_file, sampleMetadata(), false, photon_errors);
        test.expect(photon_errors.empty(), "no errors writing event_photons");
        test.expectEqual(pr.row_count, std::uint64_t{4}, "four member rows");

        const auto table = readTable(photons_file);
        test.expect(table != nullptr, "event_photons file reads back");
        if (table) {
            test.expectEqual(table->num_columns(), 5, "five event_photons columns");
            const auto names = table->ColumnNames();
            const std::vector<std::string> expected = {
                "event_id", "photon_id", "x", "y", "timestamp_canonical"};
            bool cols_match = names.size() == expected.size();
            for (std::size_t i = 0; cols_match && i < expected.size(); ++i) {
                cols_match = names[i] == expected[i];
            }
            test.expect(cols_match, "event_photons column names and order match");

            auto event_ids = std::static_pointer_cast<arrow::UInt64Array>(
                table->column(0)->chunk(0));
            auto photon_ids = std::static_pointer_cast<arrow::UInt64Array>(
                table->column(1)->chunk(0));
            test.expectEqual(event_ids->Value(3), std::uint64_t{1},
                             "event_photons event_id maps the single-photon event");
            test.expectEqual(photon_ids->Value(3), std::uint64_t{3},
                             "event_photons photon_id round-trips");
            test.expectEqual(metaValue(table, "schema_name"),
                             std::string(kEventPhotonsSchemaName),
                             "event_photons schema_name metadata");
        }
    }

    // Empty input writes nothing and reports no error.
    {
        std::vector<std::string> empty_errors;
        const auto empty = writeEventCandidatesParquet(
            {}, (base / "empty.parquet").string(), sampleMetadata(), false,
            empty_errors);
        test.expect(empty.file.empty(), "empty event set writes no file");
        test.expect(empty_errors.empty(), "empty event set is not an error");
        test.expect(
            !std::filesystem::exists((base / "empty.parquet").string()),
            "no file is created for an empty event set");
    }

    std::filesystem::remove_all(base);
    return test.finish();
}
