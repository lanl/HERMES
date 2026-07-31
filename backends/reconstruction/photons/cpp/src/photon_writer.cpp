#include "photon_writer.h"

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

namespace hermes_photon_clusterer {

#ifdef HERMES_HAS_ARROW_PARQUET

namespace {

// Builds the key-value metadata shared by both photon file groups.
std::shared_ptr<arrow::KeyValueMetadata> buildFileMetadata(
    const PhotonFileMetadata& metadata,
    const std::string& schema_name) {
    std::ostringstream tick;
    tick << std::setprecision(17) << metadata.canonical_tick_seconds;
    std::ostringstream anchor;
    anchor << std::setprecision(17) << metadata.high_tot_anchor;

    std::vector<std::string> keys = {
        "schema_name",
        "schema_version",
        "canonical_tick_seconds",
        "raw_file_stem",
        "chip_index",
        "clustering_algorithm",
        "clustering_settings",
        "position_averaging",
        "photon_time_estimator",
        "correction_model",
    };
    std::vector<std::string> values = {
        schema_name,
        kPhotonSchemaVersion,
        tick.str(),
        metadata.raw_file_stem,
        std::to_string(metadata.chip_index),
        metadata.clustering_algorithm,
        metadata.clustering_settings_json,
        metadata.position_averaging,
        metadata.photon_time_estimator,
        metadata.correction_model,
    };
    if (metadata.correction_model != "none") {
        keys.emplace_back("correction_parameters");
        values.push_back(metadata.correction_parameters_json);
        keys.emplace_back("high_tot_anchor");
        values.push_back(anchor.str());
    }
    keys.emplace_back("save_photon_pixels");
    values.emplace_back(metadata.save_photon_pixels ? "true" : "false");
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
        errors.push_back("Failed to create photon output directory " +
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
        errors.push_back("Refusing to overwrite existing photon file " +
                         full_path);
        return false;
    }
    auto out_result = arrow::io::FileOutputStream::Open(full_path);
    if (!out_result.ok()) {
        errors.push_back("Failed to open photon output file " + full_path +
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
        errors.push_back("Failed to write photon file " + full_path + ": " +
                         status.ToString());
        return false;
    }
    return true;
}

std::shared_ptr<arrow::Table> buildEventsTable(
    const std::vector<Photon>& photons,
    std::uint64_t start,
    std::uint64_t count,
    const std::shared_ptr<arrow::KeyValueMetadata>& kv) {
    arrow::UInt64Builder id_builder;
    arrow::DoubleBuilder x_builder;
    arrow::DoubleBuilder y_builder;
    arrow::DoubleBuilder time_builder;
    arrow::UInt64Builder tot_builder;
    arrow::UInt16Builder flags_builder;

    for (std::uint64_t i = start; i < start + count; ++i) {
        const auto& photon = photons[i];
        (void)id_builder.Append(i);
        (void)x_builder.Append(photon.x);
        (void)y_builder.Append(photon.y);
        (void)time_builder.Append(photon.timestamp_canonical);
        (void)tot_builder.Append(photon.tot);
        (void)flags_builder.Append(photon.quality_flags);
    }

    std::shared_ptr<arrow::Array> id_array, x_array, y_array, time_array,
        tot_array, flags_array;
    (void)id_builder.Finish(&id_array);
    (void)x_builder.Finish(&x_array);
    (void)y_builder.Finish(&y_array);
    (void)time_builder.Finish(&time_array);
    (void)tot_builder.Finish(&tot_array);
    (void)flags_builder.Finish(&flags_array);

    auto schema = arrow::schema(
        {
            arrow::field("photon_id", arrow::uint64()),
            arrow::field("x", arrow::float64()),
            arrow::field("y", arrow::float64()),
            arrow::field("timestamp_canonical", arrow::float64()),
            arrow::field("tot", arrow::uint64()),
            arrow::field("quality_flags", arrow::uint16()),
        },
        kv);
    return arrow::Table::Make(
        schema, {id_array, x_array, y_array, time_array, tot_array, flags_array});
}

std::shared_ptr<arrow::Table> buildPixelsTable(
    const std::vector<PhotonPixelRow>& rows,
    std::uint64_t start,
    std::uint64_t count,
    const std::shared_ptr<arrow::KeyValueMetadata>& kv) {
    arrow::UInt64Builder photon_builder;
    arrow::UInt64Builder event_builder;
    arrow::UInt16Builder x_builder;
    arrow::UInt16Builder y_builder;
    arrow::UInt16Builder tot_builder;
    arrow::UInt64Builder time_builder;

    for (std::uint64_t i = start; i < start + count; ++i) {
        const auto& row = rows[i];
        (void)photon_builder.Append(row.photon_id);
        (void)event_builder.Append(row.pixel_event_id);
        (void)x_builder.Append(row.x);
        (void)y_builder.Append(row.y);
        (void)tot_builder.Append(row.tot_raw);
        (void)time_builder.Append(row.timestamp_canonical);
    }

    std::shared_ptr<arrow::Array> photon_array, event_array, x_array, y_array,
        tot_array, time_array;
    (void)photon_builder.Finish(&photon_array);
    (void)event_builder.Finish(&event_array);
    (void)x_builder.Finish(&x_array);
    (void)y_builder.Finish(&y_array);
    (void)tot_builder.Finish(&tot_array);
    (void)time_builder.Finish(&time_array);

    auto schema = arrow::schema(
        {
            arrow::field("photon_id", arrow::uint64()),
            arrow::field("pixel_event_id", arrow::uint64()),
            arrow::field("x", arrow::uint16()),
            arrow::field("y", arrow::uint16()),
            arrow::field("tot_raw", arrow::uint16()),
            arrow::field("timestamp_canonical", arrow::uint64()),
        },
        kv);
    return arrow::Table::Make(schema, {photon_array, event_array, x_array,
                                       y_array, tot_array, time_array});
}

}  // namespace

PhotonWriteResult writePhotonEventsParquet(
    const std::vector<Photon>& photons,
    const std::string& output_file_path,
    const PhotonFileMetadata& metadata,
    bool overwrite,
    std::vector<std::string>& errors) {
    PhotonWriteResult result;
    if (photons.empty()) {
        return result;
    }
    if (!ensureParentDirectory(output_file_path, errors)) {
        return {};
    }

    const auto kv = buildFileMetadata(metadata, kPhotonEventsSchemaName);
    auto table = buildEventsTable(photons, 0, photons.size(), kv);
    if (!writeTable(table, output_file_path, overwrite, errors)) {
        return {};
    }
    result.file = output_file_path;
    result.row_count = photons.size();
    return result;
}

PhotonWriteResult writePhotonPixelsParquet(
    const std::vector<PhotonPixelRow>& rows,
    const std::string& output_file_path,
    const PhotonFileMetadata& metadata,
    bool overwrite,
    std::vector<std::string>& errors) {
    PhotonWriteResult result;
    if (rows.empty()) {
        return result;
    }
    if (!ensureParentDirectory(output_file_path, errors)) {
        return {};
    }

    const auto kv = buildFileMetadata(metadata, kPhotonPixelsSchemaName);
    auto table = buildPixelsTable(rows, 0, rows.size(), kv);
    if (!writeTable(table, output_file_path, overwrite, errors)) {
        return {};
    }
    result.file = output_file_path;
    result.row_count = rows.size();
    return result;
}

#else  // HERMES_HAS_ARROW_PARQUET

PhotonWriteResult writePhotonEventsParquet(
    const std::vector<Photon>& /*photons*/,
    const std::string& /*output_file_path*/,
    const PhotonFileMetadata& /*metadata*/,
    bool /*overwrite*/,
    std::vector<std::string>& errors) {
    errors.push_back("photon_events writing requires Arrow/Parquet support");
    return {};
}

PhotonWriteResult writePhotonPixelsParquet(
    const std::vector<PhotonPixelRow>& /*rows*/,
    const std::string& /*output_file_path*/,
    const PhotonFileMetadata& /*metadata*/,
    bool /*overwrite*/,
    std::vector<std::string>& errors) {
    errors.push_back("photon_pixels writing requires Arrow/Parquet support");
    return {};
}

#endif  // HERMES_HAS_ARROW_PARQUET

}  // namespace hermes_photon_clusterer
