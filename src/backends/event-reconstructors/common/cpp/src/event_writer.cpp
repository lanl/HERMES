#include "event_writer.h"

#include <algorithm>
#include <filesystem>
#include <iomanip>
#include <sstream>

#ifdef HERMES_HAS_ARROW_PARQUET
#include <arrow/array.h>
#include <arrow/builder.h>
#include <arrow/io/file.h>
#include <arrow/table.h>
#include <arrow/util/key_value_metadata.h>
#include <parquet/arrow/writer.h>
#endif

namespace hermes_event_reconstructor {

#ifdef HERMES_HAS_ARROW_PARQUET

namespace {

// Builds the key-value metadata shared by both event file groups.
std::shared_ptr<arrow::KeyValueMetadata> buildFileMetadata(
    const EventFileMetadata& metadata,
    const std::string& schema_name) {
    std::ostringstream tick;
    tick << std::setprecision(17) << metadata.canonical_tick_seconds;

    std::vector<std::string> keys = {
        "schema_name",
        "schema_version",
        "canonical_tick_seconds",
        "raw_file_stem",
        "chip_index",
        "event_algorithm",
        "event_settings",
        "position_rule",
        "event_time_estimator",
        "save_event_photons",
    };
    std::vector<std::string> values = {
        schema_name,
        kEventSchemaVersion,
        tick.str(),
        metadata.raw_file_stem,
        std::to_string(metadata.chip_index),
        metadata.event_algorithm,
        metadata.event_settings_json,
        metadata.position_rule,
        metadata.event_time_estimator,
        metadata.save_event_photons ? "true" : "false",
    };
    return std::make_shared<arrow::KeyValueMetadata>(keys, values);
}

// Creates the parent directory of output_file_path if it has one.
bool ensureParentDirectory(const std::string& output_file_path,
                           std::vector<std::string>& errors) {
    const std::filesystem::path parent =
        std::filesystem::path(output_file_path).parent_path();
    if (parent.empty()) {
        return true;
    }
    std::error_code ec;
    std::filesystem::create_directories(parent, ec);
    if (ec) {
        errors.push_back("Failed to create event output directory " +
                         parent.string() + ": " + ec.message());
        return false;
    }
    return true;
}

// Writes one Arrow table to a single Parquet file. When overwrite is false,
// refuses to replace an existing file; when true, replaces it.
bool writeTable(const std::shared_ptr<arrow::Table>& table,
                const std::string& full_path,
                bool overwrite,
                std::vector<std::string>& errors) {
    if (!overwrite && std::filesystem::exists(full_path)) {
        errors.push_back("Refusing to overwrite existing event file " +
                         full_path);
        return false;
    }
    auto out_result = arrow::io::FileOutputStream::Open(full_path);
    if (!out_result.ok()) {
        errors.push_back("Failed to open event output file " + full_path +
                         ": " + out_result.status().ToString());
        return false;
    }
    // store_schema() preserves the Arrow schema, including its key-value
    // metadata, so a reader recovers it; WriteTable drops it otherwise.
    auto arrow_properties =
        parquet::ArrowWriterProperties::Builder().store_schema()->build();
    const std::int64_t chunk_size =
        std::max<std::int64_t>(table->num_rows(), 1);
    auto status = parquet::arrow::WriteTable(
        *table, arrow::default_memory_pool(), *out_result, chunk_size,
        parquet::default_writer_properties(), arrow_properties);
    if (!status.ok()) {
        errors.push_back("Failed to write event file " + full_path + ": " +
                         status.ToString());
        return false;
    }
    return true;
}

std::shared_ptr<arrow::Table> buildCandidatesTable(
    const std::vector<CandidateEvent>& events,
    const std::shared_ptr<arrow::KeyValueMetadata>& kv) {
    arrow::UInt64Builder id_builder;
    arrow::DoubleBuilder x_builder;
    arrow::DoubleBuilder y_builder;
    arrow::DoubleBuilder time_builder;
    arrow::UInt64Builder count_builder;
    arrow::UInt16Builder flags_builder;

    for (const auto& event : events) {
        (void)id_builder.Append(event.event_id);
        (void)x_builder.Append(event.x);
        (void)y_builder.Append(event.y);
        (void)time_builder.Append(event.timestamp_canonical);
        (void)count_builder.Append(event.photon_count);
        (void)flags_builder.Append(event.quality_flags);
    }

    std::shared_ptr<arrow::Array> id_array, x_array, y_array, time_array,
        count_array, flags_array;
    (void)id_builder.Finish(&id_array);
    (void)x_builder.Finish(&x_array);
    (void)y_builder.Finish(&y_array);
    (void)time_builder.Finish(&time_array);
    (void)count_builder.Finish(&count_array);
    (void)flags_builder.Finish(&flags_array);

    auto schema = arrow::schema(
        {
            arrow::field("event_id", arrow::uint64()),
            arrow::field("x", arrow::float64()),
            arrow::field("y", arrow::float64()),
            arrow::field("timestamp_canonical", arrow::float64()),
            arrow::field("photon_count", arrow::uint64()),
            arrow::field("quality_flags", arrow::uint16()),
        },
        kv);
    return arrow::Table::Make(schema, {id_array, x_array, y_array, time_array,
                                       count_array, flags_array});
}

std::shared_ptr<arrow::Table> buildPhotonsTable(
    const std::vector<EventPhotonRow>& rows,
    const std::shared_ptr<arrow::KeyValueMetadata>& kv) {
    arrow::UInt64Builder event_builder;
    arrow::UInt64Builder photon_builder;
    arrow::DoubleBuilder x_builder;
    arrow::DoubleBuilder y_builder;
    arrow::DoubleBuilder time_builder;

    for (const auto& row : rows) {
        (void)event_builder.Append(row.event_id);
        (void)photon_builder.Append(row.photon_id);
        (void)x_builder.Append(row.x);
        (void)y_builder.Append(row.y);
        (void)time_builder.Append(row.timestamp_canonical);
    }

    std::shared_ptr<arrow::Array> event_array, photon_array, x_array, y_array,
        time_array;
    (void)event_builder.Finish(&event_array);
    (void)photon_builder.Finish(&photon_array);
    (void)x_builder.Finish(&x_array);
    (void)y_builder.Finish(&y_array);
    (void)time_builder.Finish(&time_array);

    auto schema = arrow::schema(
        {
            arrow::field("event_id", arrow::uint64()),
            arrow::field("photon_id", arrow::uint64()),
            arrow::field("x", arrow::float64()),
            arrow::field("y", arrow::float64()),
            arrow::field("timestamp_canonical", arrow::float64()),
        },
        kv);
    return arrow::Table::Make(
        schema, {event_array, photon_array, x_array, y_array, time_array});
}

}  // namespace

EventWriteResult writeEventCandidatesParquet(
    const std::vector<CandidateEvent>& events,
    const std::string& output_file_path,
    const EventFileMetadata& metadata,
    bool overwrite,
    std::vector<std::string>& errors) {
    EventWriteResult result;
    if (events.empty()) {
        return result;
    }
    if (!ensureParentDirectory(output_file_path, errors)) {
        return {};
    }

    const auto kv = buildFileMetadata(metadata, kEventCandidatesSchemaName);
    auto table = buildCandidatesTable(events, kv);
    if (!writeTable(table, output_file_path, overwrite, errors)) {
        return {};
    }
    result.file = output_file_path;
    result.row_count = events.size();
    return result;
}

EventWriteResult writeEventPhotonsParquet(
    const std::vector<EventPhotonRow>& rows,
    const std::string& output_file_path,
    const EventFileMetadata& metadata,
    bool overwrite,
    std::vector<std::string>& errors) {
    EventWriteResult result;
    if (rows.empty()) {
        return result;
    }
    if (!ensureParentDirectory(output_file_path, errors)) {
        return {};
    }

    const auto kv = buildFileMetadata(metadata, kEventPhotonsSchemaName);
    auto table = buildPhotonsTable(rows, kv);
    if (!writeTable(table, output_file_path, overwrite, errors)) {
        return {};
    }
    result.file = output_file_path;
    result.row_count = rows.size();
    return result;
}

#else  // HERMES_HAS_ARROW_PARQUET

EventWriteResult writeEventCandidatesParquet(
    const std::vector<CandidateEvent>& /*events*/,
    const std::string& /*output_file_path*/,
    const EventFileMetadata& /*metadata*/,
    bool /*overwrite*/,
    std::vector<std::string>& errors) {
    errors.push_back("event_candidates writing requires Arrow/Parquet support");
    return {};
}

EventWriteResult writeEventPhotonsParquet(
    const std::vector<EventPhotonRow>& /*rows*/,
    const std::string& /*output_file_path*/,
    const EventFileMetadata& /*metadata*/,
    bool /*overwrite*/,
    std::vector<std::string>& errors) {
    errors.push_back("event_photons writing requires Arrow/Parquet support");
    return {};
}

#endif  // HERMES_HAS_ARROW_PARQUET

}  // namespace hermes_event_reconstructor
