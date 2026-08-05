#include "photon_reader.h"

#include <algorithm>

#ifdef HERMES_HAS_ARROW_PARQUET
#include <arrow/array.h>
#include <arrow/io/file.h>
#include <arrow/record_batch.h>
#include <arrow/table.h>
#include <parquet/arrow/reader.h>
#endif

namespace hermes_event_reconstructor {

#ifdef HERMES_HAS_ARROW_PARQUET

namespace {

std::uint64_t uint64At(const std::shared_ptr<arrow::Array>& array,
                       std::int64_t row) {
    const auto& typed = static_cast<const arrow::UInt64Array&>(*array);
    return typed.Value(row);
}

double doubleAt(const std::shared_ptr<arrow::Array>& array, std::int64_t row) {
    const auto& typed = static_cast<const arrow::DoubleArray&>(*array);
    return typed.Value(row);
}

}  // namespace

bool readPhotonEvents(const std::string& file,
                      std::vector<PhotonEvent>& out_rows,
                      std::vector<std::string>& errors) {
    out_rows.clear();

    const std::vector<std::string> columns = {"photon_id", "x", "y",
                                              "timestamp_canonical"};

    auto input_result = arrow::io::ReadableFile::Open(file);
    if (!input_result.ok()) {
        errors.push_back("Failed to open photon_events file " + file + ": " +
                         input_result.status().ToString());
        return false;
    }

    auto reader_result =
        parquet::arrow::OpenFile(*input_result, arrow::default_memory_pool());
    if (!reader_result.ok()) {
        errors.push_back("Failed to read photon_events file " + file + ": " +
                         reader_result.status().ToString());
        return false;
    }
    std::unique_ptr<parquet::arrow::FileReader> reader =
        std::move(*reader_result);

    std::shared_ptr<arrow::Schema> schema;
    auto schema_status = reader->GetSchema(&schema);
    if (!schema_status.ok()) {
        errors.push_back("Failed to read schema of " + file + ": " +
                         schema_status.ToString());
        return false;
    }

    std::vector<int> column_indices;
    for (const std::string& column : columns) {
        const int index = schema->GetFieldIndex(column);
        if (index < 0) {
            errors.push_back("photon_events file " + file +
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
        errors.push_back("Failed to scan photon_events file " + file + ": " +
                         batch_reader_result.status().ToString());
        return false;
    }
    std::unique_ptr<arrow::RecordBatchReader> batch_reader =
        std::move(*batch_reader_result);

    std::shared_ptr<arrow::RecordBatch> batch;
    while (true) {
        auto read_status = batch_reader->ReadNext(&batch);
        if (!read_status.ok()) {
            errors.push_back("Failed to read a batch from " + file + ": " +
                             read_status.ToString());
            out_rows.clear();
            return false;
        }
        if (batch == nullptr) {
            break;
        }
        // GetRecordBatchReader projects columns in the requested order.
        const auto photon_id_array = batch->column(0);
        const auto x_array = batch->column(1);
        const auto y_array = batch->column(2);
        const auto time_array = batch->column(3);
        for (std::int64_t row = 0; row < batch->num_rows(); ++row) {
            PhotonEvent photon;
            photon.photon_id = uint64At(photon_id_array, row);
            photon.x = doubleAt(x_array, row);
            photon.y = doubleAt(y_array, row);
            photon.timestamp_canonical = doubleAt(time_array, row);
            out_rows.push_back(photon);
        }
    }

    // Photon files are written in reconstruction order, not guaranteed strictly
    // increasing in time. Sort into time order, breaking ties by photon_id, so
    // the clustering stage sees a monotonic stream.
    std::stable_sort(out_rows.begin(), out_rows.end(),
                     [](const PhotonEvent& a, const PhotonEvent& b) {
                         if (a.timestamp_canonical != b.timestamp_canonical) {
                             return a.timestamp_canonical < b.timestamp_canonical;
                         }
                         return a.photon_id < b.photon_id;
                     });

    return true;
}

#else  // HERMES_HAS_ARROW_PARQUET

bool readPhotonEvents(const std::string& /*file*/,
                      std::vector<PhotonEvent>& out_rows,
                      std::vector<std::string>& errors) {
    out_rows.clear();
    errors.push_back("photon_events reading requires Arrow/Parquet support");
    return false;
}

#endif  // HERMES_HAS_ARROW_PARQUET

}  // namespace hermes_event_reconstructor
