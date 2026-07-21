#include "parquet_writer.h"
#include "parquet_schemas.h"

#include <sstream>
#include <iomanip>
#include <filesystem>

#ifdef HERMES_HAS_ARROW_PARQUET
#include <arrow/io/file.h>
#include <parquet/arrow/writer.h>
#include <arrow/table.h>
#include <arrow/array.h>
#include <arrow/builder.h>
#endif

namespace hermes_tpx3_spidr {

#ifdef HERMES_HAS_ARROW_PARQUET

namespace {

std::string makePartFileName(std::uint8_t chip_index,
                              std::uint64_t part_number) {
    std::ostringstream oss;
    oss << "chip_" << static_cast<int>(chip_index) << "-"
        << std::setw(5) << std::setfill('0') << part_number << ".parquet";
    return oss.str();
}

bool ensureDirectory(const std::string& path, std::vector<std::string>& errors) {
    try {
        std::filesystem::create_directories(path);
        return true;
    } catch (const std::exception& e) {
        errors.push_back("Failed to create directory " + path + ": " + e.what());
        return false;
    }
}

std::shared_ptr<arrow::Table> buildPixelTable(
    const std::vector<PixelOutputRow>& rows,
    std::size_t start_idx,
    std::size_t count) {

    arrow::UInt64Builder chunk_builder;
    arrow::UInt64Builder packet_builder;
    arrow::UInt16Builder x_builder;
    arrow::UInt16Builder y_builder;
    arrow::UInt16Builder tot_builder;
    arrow::UInt64Builder time_builder;

    for (std::size_t i = start_idx; i < start_idx + count; ++i) {
        const auto& row = rows[i];
        (void)chunk_builder.Append(row.chunk_index);
        (void)packet_builder.Append(row.packet_index);
        (void)x_builder.Append(row.local_x);
        (void)y_builder.Append(row.local_y);
        (void)tot_builder.Append(row.tot_raw);
        (void)time_builder.Append(row.timestamp_canonical);
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

    auto schema = createPixelHitsSchema();
    return arrow::Table::Make(schema, {chunk_array, packet_array, x_array,
                                       y_array, tot_array, time_array});
}

std::shared_ptr<arrow::Table> buildTdcTable(
    const std::vector<TdcOutputRow>& rows,
    std::size_t start_idx,
    std::size_t count) {

    arrow::UInt64Builder chunk_builder;
    arrow::UInt64Builder packet_builder;
    arrow::UInt8Builder type_builder;
    arrow::UInt64Builder time_builder;

    for (std::size_t i = start_idx; i < start_idx + count; ++i) {
        const auto& row = rows[i];
        (void)chunk_builder.Append(row.chunk_index);
        (void)packet_builder.Append(row.packet_index);
        (void)type_builder.Append(row.trigger_type);
        (void)time_builder.Append(row.timestamp_canonical);
    }

    std::shared_ptr<arrow::Array> chunk_array;
    std::shared_ptr<arrow::Array> packet_array;
    std::shared_ptr<arrow::Array> type_array;
    std::shared_ptr<arrow::Array> time_array;

    (void)chunk_builder.Finish(&chunk_array);
    (void)packet_builder.Finish(&packet_array);
    (void)type_builder.Finish(&type_array);
    (void)time_builder.Finish(&time_array);

    auto schema = createTdcTriggersSchema();
    return arrow::Table::Make(schema, {chunk_array, packet_array, type_array, time_array});
}

std::shared_ptr<arrow::Table> buildGlobalTable(
    const std::vector<GlobalOutputRow>& rows,
    std::size_t start_idx,
    std::size_t count) {

    arrow::UInt64Builder chunk_builder;
    arrow::UInt64Builder packet_builder;
    arrow::UInt64Builder time_builder;

    for (std::size_t i = start_idx; i < start_idx + count; ++i) {
        const auto& row = rows[i];
        (void)chunk_builder.Append(row.chunk_index);
        (void)packet_builder.Append(row.packet_index);
        (void)time_builder.Append(row.timestamp_canonical);
    }

    std::shared_ptr<arrow::Array> chunk_array;
    std::shared_ptr<arrow::Array> packet_array;
    std::shared_ptr<arrow::Array> time_array;

    (void)chunk_builder.Finish(&chunk_array);
    (void)packet_builder.Finish(&packet_array);
    (void)time_builder.Finish(&time_array);

    auto schema = createGlobalTimestampsSchema();
    return arrow::Table::Make(schema, {chunk_array, packet_array, time_array});
}

std::shared_ptr<arrow::Table> buildControlTable(
    const std::vector<ControlOutputRow>& rows,
    std::size_t start_idx,
    std::size_t count) {

    arrow::UInt64Builder chunk_builder;
    arrow::UInt64Builder packet_builder;
    arrow::UInt8Builder source_builder;
    arrow::UInt16Builder type_builder;
    arrow::UInt8Builder packet_id_builder;
    arrow::BooleanBuilder packet_id_present_builder;
    arrow::UInt8Builder subtype_builder;
    arrow::BooleanBuilder subtype_present_builder;
    arrow::UInt64Builder count_builder;
    arrow::BooleanBuilder count_present_builder;
    arrow::UInt16Builder res_high_builder;
    arrow::BooleanBuilder res_high_present_builder;
    arrow::UInt16Builder res_low_builder;
    arrow::BooleanBuilder res_low_present_builder;
    arrow::UInt16Builder ctrl_val_builder;
    arrow::BooleanBuilder ctrl_val_present_builder;
    arrow::UInt64Builder ctrl_payload_builder;
    arrow::BooleanBuilder ctrl_payload_present_builder;
    arrow::UInt64Builder time_builder;
    arrow::BooleanBuilder time_present_builder;

    for (std::size_t i = start_idx; i < start_idx + count; ++i) {
        const auto& row = rows[i];
        (void)chunk_builder.Append(row.chunk_index);
        (void)packet_builder.Append(row.packet_index);
        (void)source_builder.Append(row.source);
        (void)type_builder.Append(row.control_type);

        if (row.packet_id_present) {
            (void)packet_id_builder.Append(row.packet_id);
        } else {
            (void)packet_id_builder.AppendNull();
        }
        (void)packet_id_present_builder.Append(row.packet_id_present);

        if (row.subtype_present) {
            (void)subtype_builder.Append(row.subtype);
        } else {
            (void)subtype_builder.AppendNull();
        }
        (void)subtype_present_builder.Append(row.subtype_present);

        if (row.packet_count_present) {
            (void)count_builder.Append(row.packet_count);
        } else {
            (void)count_builder.AppendNull();
        }
        (void)count_present_builder.Append(row.packet_count_present);

        if (row.reserved_high_present) {
            (void)res_high_builder.Append(row.reserved_high);
        } else {
            (void)res_high_builder.AppendNull();
        }
        (void)res_high_present_builder.Append(row.reserved_high_present);

        if (row.reserved_low_present) {
            (void)res_low_builder.Append(row.reserved_low);
        } else {
            (void)res_low_builder.AppendNull();
        }
        (void)res_low_present_builder.Append(row.reserved_low_present);

        if (row.control_value_raw_present) {
            (void)ctrl_val_builder.Append(row.control_value_raw);
        } else {
            (void)ctrl_val_builder.AppendNull();
        }
        (void)ctrl_val_present_builder.Append(row.control_value_raw_present);

        if (row.control_payload_raw_present) {
            (void)ctrl_payload_builder.Append(row.control_payload_raw);
        } else {
            (void)ctrl_payload_builder.AppendNull();
        }
        (void)ctrl_payload_present_builder.Append(row.control_payload_raw_present);

        if (row.timestamp_canonical_present) {
            (void)time_builder.Append(row.timestamp_canonical);
        } else {
            (void)time_builder.AppendNull();
        }
        (void)time_present_builder.Append(row.timestamp_canonical_present);
    }

    std::shared_ptr<arrow::Array> chunk_array, packet_array, source_array, type_array;
    std::shared_ptr<arrow::Array> packet_id_array, packet_id_present_array;
    std::shared_ptr<arrow::Array> subtype_array, subtype_present_array;
    std::shared_ptr<arrow::Array> count_array, count_present_array;
    std::shared_ptr<arrow::Array> res_high_array, res_high_present_array;
    std::shared_ptr<arrow::Array> res_low_array, res_low_present_array;
    std::shared_ptr<arrow::Array> ctrl_val_array, ctrl_val_present_array;
    std::shared_ptr<arrow::Array> ctrl_payload_array, ctrl_payload_present_array;
    std::shared_ptr<arrow::Array> time_array, time_present_array;

    (void)chunk_builder.Finish(&chunk_array);
    (void)packet_builder.Finish(&packet_array);
    (void)source_builder.Finish(&source_array);
    (void)type_builder.Finish(&type_array);
    (void)packet_id_builder.Finish(&packet_id_array);
    (void)packet_id_present_builder.Finish(&packet_id_present_array);
    (void)subtype_builder.Finish(&subtype_array);
    (void)subtype_present_builder.Finish(&subtype_present_array);
    (void)count_builder.Finish(&count_array);
    (void)count_present_builder.Finish(&count_present_array);
    (void)res_high_builder.Finish(&res_high_array);
    (void)res_high_present_builder.Finish(&res_high_present_array);
    (void)res_low_builder.Finish(&res_low_array);
    (void)res_low_present_builder.Finish(&res_low_present_array);
    (void)ctrl_val_builder.Finish(&ctrl_val_array);
    (void)ctrl_val_present_builder.Finish(&ctrl_val_present_array);
    (void)ctrl_payload_builder.Finish(&ctrl_payload_array);
    (void)ctrl_payload_present_builder.Finish(&ctrl_payload_present_array);
    (void)time_builder.Finish(&time_array);
    (void)time_present_builder.Finish(&time_present_array);

    auto schema = createControlPacketsSchema();
    return arrow::Table::Make(schema, {chunk_array, packet_array, source_array, type_array,
                                       packet_id_array, packet_id_present_array,
                                       subtype_array, subtype_present_array,
                                       count_array, count_present_array,
                                       res_high_array, res_high_present_array,
                                       res_low_array, res_low_present_array,
                                       ctrl_val_array, ctrl_val_present_array,
                                       ctrl_payload_array, ctrl_payload_present_array,
                                       time_array, time_present_array});
}

std::shared_ptr<arrow::Table> buildUnknownTable(
    const std::vector<UnknownOutputRow>& rows,
    std::size_t start_idx,
    std::size_t count) {

    arrow::UInt64Builder chunk_builder;
    arrow::UInt64Builder packet_builder;
    arrow::UInt64Builder word_builder;
    arrow::UInt8Builder byte_builder;

    for (std::size_t i = start_idx; i < start_idx + count; ++i) {
        const auto& row = rows[i];
        (void)chunk_builder.Append(row.chunk_index);
        (void)packet_builder.Append(row.packet_index);
        (void)word_builder.Append(row.raw_word);
        (void)byte_builder.Append(row.most_significant_byte);
    }

    std::shared_ptr<arrow::Array> chunk_array;
    std::shared_ptr<arrow::Array> packet_array;
    std::shared_ptr<arrow::Array> word_array;
    std::shared_ptr<arrow::Array> byte_array;

    (void)chunk_builder.Finish(&chunk_array);
    (void)packet_builder.Finish(&packet_array);
    (void)word_builder.Finish(&word_array);
    (void)byte_builder.Finish(&byte_array);

    auto schema = createUnknownPacketsSchema();
    return arrow::Table::Make(schema, {chunk_array, packet_array, word_array, byte_array});
}

template <typename Row, typename TableBuilder>
void writeRowsToParquet(
    const std::vector<Row>& rows,
    const ParquetWriterConfig& config,
    const std::string& dataset_name,
    std::uint64_t& files_written,
    std::vector<std::string>& errors,
    TableBuilder table_builder) {

    if (rows.empty()) {
        return;
    }

    std::string dataset_dir = config.output_directory + "/" + dataset_name;
    if (!ensureDirectory(dataset_dir, errors)) {
        return;
    }

    std::size_t num_parts = (rows.size() + config.rows_per_part - 1) / config.rows_per_part;

    for (std::size_t part = 0; part < num_parts; ++part) {
        std::size_t start_idx = part * config.rows_per_part;
        std::size_t count = std::min(static_cast<std::size_t>(config.rows_per_part),
                                     rows.size() - start_idx);

        auto table = table_builder(rows, start_idx, count);

        std::string filename = makePartFileName(config.chip_index, part);
        std::string full_path = dataset_dir + "/" + filename;

        std::shared_ptr<arrow::io::FileOutputStream> outfile;
        auto result = arrow::io::FileOutputStream::Open(full_path);
        if (!result.ok()) {
            errors.push_back("Failed to open output file " + full_path + ": " +
                           result.status().ToString());
            continue;
        }
        outfile = *result;

        auto status = parquet::arrow::WriteTable(*table, arrow::default_memory_pool(),
                                                 outfile, config.rows_per_part);
        if (!status.ok()) {
            errors.push_back("Failed to write Parquet file " + full_path + ": " +
                           status.ToString());
            continue;
        }

        ++files_written;
    }
}

}  // anonymous namespace

void writePixelHitsParquet(const std::vector<PixelOutputRow>& rows,
                           const ParquetWriterConfig& config,
                           ParquetWriterDiagnostics& diagnostics) {
    writeRowsToParquet(rows, config, "pixel_hits",
                      diagnostics.pixel_files_written,
                      diagnostics.errors, buildPixelTable);
}

void writeTdcTriggersParquet(const std::vector<TdcOutputRow>& rows,
                             const ParquetWriterConfig& config,
                             ParquetWriterDiagnostics& diagnostics) {
    writeRowsToParquet(rows, config, "tdc_triggers",
                      diagnostics.tdc_files_written,
                      diagnostics.errors, buildTdcTable);
}

void writeGlobalTimestampsParquet(const std::vector<GlobalOutputRow>& rows,
                                   const ParquetWriterConfig& config,
                                   ParquetWriterDiagnostics& diagnostics) {
    writeRowsToParquet(rows, config, "global_timestamps",
                      diagnostics.global_files_written,
                      diagnostics.errors, buildGlobalTable);
}

void writeControlPacketsParquet(const std::vector<ControlOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics) {
    writeRowsToParquet(rows, config, "control_packets",
                      diagnostics.control_files_written,
                      diagnostics.errors, buildControlTable);
}

void writeUnknownPacketsParquet(const std::vector<UnknownOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics) {
    writeRowsToParquet(rows, config, "unknown_packets",
                      diagnostics.unknown_files_written,
                      diagnostics.errors, buildUnknownTable);
}

#else

void writePixelHitsParquet(const std::vector<PixelOutputRow>& rows,
                           const ParquetWriterConfig& config,
                           ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    diagnostics.errors.push_back("Arrow/Parquet support not compiled in");
}

void writeTdcTriggersParquet(const std::vector<TdcOutputRow>& rows,
                             const ParquetWriterConfig& config,
                             ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    diagnostics.errors.push_back("Arrow/Parquet support not compiled in");
}

void writeGlobalTimestampsParquet(const std::vector<GlobalOutputRow>& rows,
                                   const ParquetWriterConfig& config,
                                   ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    diagnostics.errors.push_back("Arrow/Parquet support not compiled in");
}

void writeControlPacketsParquet(const std::vector<ControlOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    diagnostics.errors.push_back("Arrow/Parquet support not compiled in");
}

void writeUnknownPacketsParquet(const std::vector<UnknownOutputRow>& rows,
                                const ParquetWriterConfig& config,
                                ParquetWriterDiagnostics& diagnostics) {
    (void)rows;
    (void)config;
    diagnostics.errors.push_back("Arrow/Parquet support not compiled in");
}

#endif

}  // namespace hermes_tpx3_spidr
