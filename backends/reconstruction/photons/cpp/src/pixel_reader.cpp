#include "pixel_reader.h"

#include <algorithm>
#include <filesystem>
#include <regex>

#ifdef HERMES_HAS_ARROW_PARQUET
#include <arrow/array.h>
#include <arrow/io/file.h>
#include <arrow/record_batch.h>
#include <arrow/table.h>
#include <parquet/arrow/reader.h>
#endif

namespace hermes_photon_clusterer {

namespace {

// Matches "<stem>-chip-<chip>-part-<00000>.parquet", the unpacker's pixel_data
// filename convention.
const std::regex& pixelFilePattern() {
    static const std::regex pattern(
        R"(^(.+)-chip-(\d+)-part-(\d{5})\.parquet$)");
    return pattern;
}

}  // namespace

PixelFileGroups discoverPixelFiles(const std::string& pixel_data_directory,
                                   const std::string& raw_file_stem) {
    PixelFileGroups groups;

    // Collect (part_number, path) per chip, then verify contiguity and order.
    std::map<int, std::vector<std::pair<int, std::string>>> parts_by_chip;
    std::error_code ec;
    std::filesystem::directory_iterator it(pixel_data_directory, ec);
    if (ec) {
        groups.errors.push_back("Failed to read pixel_data directory " +
                                pixel_data_directory + ": " + ec.message());
        return groups;
    }

    for (const auto& entry : it) {
        if (!entry.is_regular_file()) {
            continue;
        }
        const std::string name = entry.path().filename().string();
        std::smatch match;
        if (!std::regex_match(name, match, pixelFilePattern())) {
            continue;
        }
        if (match[1].str() != raw_file_stem) {
            continue;
        }
        const int chip = std::stoi(match[2].str());
        const int part = std::stoi(match[3].str());
        parts_by_chip[chip].emplace_back(part, entry.path().string());
    }

    if (parts_by_chip.empty()) {
        groups.errors.push_back(
            "No pixel_data Parquet files found for stem '" + raw_file_stem +
            "' in " + pixel_data_directory);
        return groups;
    }

    for (auto& [chip, parts] : parts_by_chip) {
        std::sort(parts.begin(), parts.end());
        for (std::size_t index = 0; index < parts.size(); ++index) {
            if (parts[index].first != static_cast<int>(index)) {
                groups.errors.push_back(
                    "pixel_data parts are not contiguous for stem '" +
                    raw_file_stem + "' chip " + std::to_string(chip));
                break;
            }
            groups.files_by_chip[chip].push_back(parts[index].second);
        }
    }

    return groups;
}

#ifdef HERMES_HAS_ARROW_PARQUET

namespace {

// Reads one uint16 column value at row index, tolerating either UInt16 storage
// (pixel positions and ToT) as written by the unpacker.
std::uint16_t uint16At(const std::shared_ptr<arrow::Array>& array,
                       std::int64_t row) {
    const auto& typed = static_cast<const arrow::UInt16Array&>(*array);
    return typed.Value(row);
}

std::uint64_t uint64At(const std::shared_ptr<arrow::Array>& array,
                       std::int64_t row) {
    const auto& typed = static_cast<const arrow::UInt64Array&>(*array);
    return typed.Value(row);
}

}  // namespace

bool readPixelHits(const std::vector<std::string>& files,
                   const std::function<void(const PixelHit&)>& on_hit,
                   std::vector<std::string>& errors) {
    const std::vector<std::string> columns = {"local_x", "local_y", "tot_raw",
                                              "timestamp_canonical"};

    // Zero-based source-row counter across the chip's ordered parts. Assigned
    // before any filtering so it references the true input row.
    std::uint64_t pixel_event_id = 0;
    for (const std::string& path : files) {
        auto input_result = arrow::io::ReadableFile::Open(path);
        if (!input_result.ok()) {
            errors.push_back("Failed to open pixel_data file " + path + ": " +
                             input_result.status().ToString());
            return false;
        }

        auto reader_result = parquet::arrow::OpenFile(
            *input_result, arrow::default_memory_pool());
        if (!reader_result.ok()) {
            errors.push_back("Failed to read pixel_data file " + path + ": " +
                             reader_result.status().ToString());
            return false;
        }
        std::unique_ptr<parquet::arrow::FileReader> reader =
            std::move(*reader_result);

        std::shared_ptr<arrow::Schema> schema;
        auto schema_status = reader->GetSchema(&schema);
        if (!schema_status.ok()) {
            errors.push_back("Failed to read schema of " + path + ": " +
                             schema_status.ToString());
            return false;
        }

        std::vector<int> column_indices;
        for (const std::string& column : columns) {
            const int index = schema->GetFieldIndex(column);
            if (index < 0) {
                errors.push_back("pixel_data file " + path +
                                 " is missing column '" + column + "'");
                return false;
            }
            column_indices.push_back(index);
        }

        std::vector<int> row_group_indices;
        for (int group = 0; group < reader->num_row_groups(); ++group) {
            row_group_indices.push_back(group);
        }

        auto batch_reader_result =
            reader->GetRecordBatchReader(row_group_indices, column_indices);
        if (!batch_reader_result.ok()) {
            errors.push_back("Failed to scan pixel_data file " + path + ": " +
                             batch_reader_result.status().ToString());
            return false;
        }
        std::unique_ptr<arrow::RecordBatchReader> batch_reader =
            std::move(*batch_reader_result);

        std::shared_ptr<arrow::RecordBatch> batch;
        while (true) {
            auto read_status = batch_reader->ReadNext(&batch);
            if (!read_status.ok()) {
                errors.push_back("Failed to read a batch from " + path + ": " +
                                 read_status.ToString());
                return false;
            }
            if (batch == nullptr) {
                break;
            }
            // GetRecordBatchReader projects columns in the requested order.
            const auto x_array = batch->column(0);
            const auto y_array = batch->column(1);
            const auto tot_array = batch->column(2);
            const auto time_array = batch->column(3);
            for (std::int64_t row = 0; row < batch->num_rows(); ++row) {
                PixelHit hit;
                hit.x = uint16At(x_array, row);
                hit.y = uint16At(y_array, row);
                hit.tot_raw = uint16At(tot_array, row);
                hit.timestamp_canonical = uint64At(time_array, row);
                hit.pixel_event_id = pixel_event_id++;
                on_hit(hit);
            }
        }
    }

    return true;
}

#else  // HERMES_HAS_ARROW_PARQUET

bool readPixelHits(const std::vector<std::string>& /*files*/,
                   const std::function<void(const PixelHit&)>& /*on_hit*/,
                   std::vector<std::string>& errors) {
    errors.push_back("pixel_data reading requires Arrow/Parquet support");
    return false;
}

#endif  // HERMES_HAS_ARROW_PARQUET

bool readPixelHitsFiltered(const std::vector<std::string>& files,
                           std::uint16_t min_pixel_tot_raw,
                           const std::function<void(const PixelHit&)>& on_hit,
                           std::uint64_t& rejected_count,
                           std::vector<std::string>& errors) {
    return readPixelHits(
        files,
        [&](const PixelHit& hit) {
            if (hit.tot_raw < min_pixel_tot_raw) {
                ++rejected_count;
                return;
            }
            on_hit(hit);
        },
        errors);
}

}  // namespace hermes_photon_clusterer
