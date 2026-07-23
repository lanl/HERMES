#include "unpacker.h"

#include "chunk_reader.h"
#include "timestamp_calculator.h"
#include "time_sort.h"
#include "parquet_writer.h"
#include "summary_json.h"

#include <array>
#include <optional>
#include <sstream>
#include <filesystem>
#include <chrono>

namespace hermes_tpx3_spidr {
namespace {

constexpr std::uint64_t lower_48_bits = 0x0000FFFFFFFFFFFFULL;
constexpr std::uint64_t tdc_timestamp_mask = 0x7FFFFFFFFULL;
constexpr std::uint64_t spidr_timestamp_mask = 0x3FFFFFFFFULL;
constexpr std::uint64_t canonical_ticks_per_tdc_timestamp = 1536;
constexpr std::uint64_t canonical_ticks_per_tdc_fine_step = 128;

PacketPosition makePosition(const std::uint64_t raw_word,
                            const std::uint8_t chip_index,
                            const std::size_t chunk_index,
                            const std::size_t packet_index) {
    return {raw_word, chip_index, chunk_index, packet_index};
}

std::string packetLocation(const PacketPosition& position) {
    std::ostringstream message;
    message << "chip " << static_cast<unsigned int>(position.chip_index)
            << ", chunk " << position.chunk_index
            << ", packet " << position.packet_index;
    return message.str();
}

void unpackIntegratedTot(const PacketPosition& position, UnpackResult& result) {
    const auto raw_word = position.raw_word;
    result.integrated_tot_pixels.push_back({
        position,
        static_cast<std::uint16_t>((raw_word >> 44U) & 0xFFFFU),
        static_cast<std::uint16_t>((raw_word >> 30U) & 0x3FFFU),
        static_cast<std::uint16_t>((raw_word >> 20U) & 0x03FFU),
        static_cast<std::uint8_t>((raw_word >> 16U) & 0x0FU),
        static_cast<std::uint16_t>(raw_word & 0xFFFFU),
    });
    ++result.summary.integrated_tot_count;
}

void unpackPixelHit(const PacketPosition& position, UnpackResult& result) {
    const auto raw_word = position.raw_word;
    const auto pixel_address =
        static_cast<std::uint16_t>((raw_word >> 44U) & 0xFFFFU);
    const auto double_column =
        static_cast<std::uint16_t>((pixel_address & 0xFE00U) >> 8U);
    const auto super_pixel =
        static_cast<std::uint16_t>((pixel_address & 0x01F8U) >> 1U);
    const auto pixel_index = static_cast<std::uint16_t>(pixel_address & 0x0007U);
    const auto toa_raw =
        static_cast<std::uint16_t>((raw_word >> 30U) & 0x3FFFU);
    const auto tot_raw =
        static_cast<std::uint16_t>((raw_word >> 20U) & 0x03FFU);
    const auto ftoa_raw =
        static_cast<std::uint8_t>((raw_word >> 16U) & 0x0FU);
    const auto spidr_time_raw = static_cast<std::uint16_t>(raw_word & 0xFFFFU);
    const auto coarse_time_25ns =
        (static_cast<std::uint64_t>(spidr_time_raw) << 14U) + toa_raw;
    const auto fine_time_1p5625ns =
        static_cast<std::int64_t>(coarse_time_25ns << 4U) - ftoa_raw;

    result.pixel_hits.push_back({
        position,
        pixel_address,
        static_cast<std::uint16_t>(double_column + (pixel_index >> 2U)),
        static_cast<std::uint16_t>(super_pixel + (pixel_index & 0x0003U)),
        toa_raw,
        ftoa_raw,
        tot_raw,
        spidr_time_raw,
        coarse_time_25ns,
        fine_time_1p5625ns,
    });
    ++result.summary.pixel_hit_count;
}

void unpackTdcHit(const PacketPosition& position, UnpackResult& result) {
    const auto raw_word = position.raw_word;
    const auto edge_code =
        static_cast<std::uint8_t>((raw_word >> 56U) & 0x0FU);
    const auto fine_raw =
        static_cast<std::uint8_t>((raw_word >> 5U) & 0x0FU);

    TdcChannel channel = TdcChannel::unknown;
    TdcEdge edge = TdcEdge::unknown;
    switch (edge_code) {
        case 0x0F:
            channel = TdcChannel::tdc1;
            edge = TdcEdge::rising;
            ++result.summary.tdc1_rising_count;
            break;
        case 0x0A:
            channel = TdcChannel::tdc1;
            edge = TdcEdge::falling;
            ++result.summary.tdc1_falling_count;
            break;
        case 0x0E:
            channel = TdcChannel::tdc2;
            edge = TdcEdge::rising;
            ++result.summary.tdc2_rising_count;
            break;
        case 0x0B:
            channel = TdcChannel::tdc2;
            edge = TdcEdge::falling;
            ++result.summary.tdc2_falling_count;
            break;
        default:
            ++result.summary.unknown_tdc_edge_count;
            result.summary.warnings.push_back(
                "Unknown TDC edge code " + std::to_string(edge_code) +
                " at " + packetLocation(position));
            break;
    }

    const auto fine_value_valid = fine_raw >= 1U && fine_raw <= 12U;
    const auto timestamp_raw = (raw_word >> 9U) & tdc_timestamp_mask;
    auto time_canonical_ticks =
        timestamp_raw * canonical_ticks_per_tdc_timestamp;
    if (fine_value_valid) {
        time_canonical_ticks +=
            static_cast<std::uint64_t>(fine_raw - 1U) *
            canonical_ticks_per_tdc_fine_step;
    } else {
        ++result.summary.invalid_tdc_fine_value_count;
        result.summary.errors.push_back(
            "Invalid TDC fine value " + std::to_string(fine_raw) +
            " at " + packetLocation(position));
    }

    result.tdc_hits.push_back({
        position,
        edge_code,
        channel,
        edge,
        static_cast<std::uint16_t>((raw_word >> 44U) & 0x0FFFU),
        timestamp_raw,
        fine_raw,
        static_cast<std::uint8_t>(raw_word & 0x001FU),
        fine_value_valid,
        time_canonical_ticks,
    });
    ++result.summary.tdc_hit_count;
}

void unpackGlobalTime(const PacketPosition& position, UnpackResult& result) {
    const auto raw_word = position.raw_word;
    const auto packet_id = static_cast<std::uint8_t>(raw_word >> 56U);
    if (packet_id == 0x44U) {
        result.global_time_lows.push_back({
            position,
            static_cast<std::uint8_t>((raw_word >> 48U) & 0x00FFU),
            static_cast<std::uint32_t>((raw_word >> 16U) & 0xFFFFFFFFU),
            static_cast<std::uint16_t>(raw_word & 0xFFFFU),
        });
        ++result.summary.global_time_low_count;
        return;
    }
    if (packet_id == 0x45U) {
        result.global_time_highs.push_back({
            position,
            static_cast<std::uint32_t>((raw_word >> 32U) & 0x00FFFFFFU),
            static_cast<std::uint16_t>((raw_word >> 16U) & 0xFFFFU),
            static_cast<std::uint16_t>(raw_word & 0xFFFFU),
        });
        ++result.summary.global_time_high_count;
        return;
    }

    result.unknown_packets.push_back({
        position,
        packet_id,
    });
    ++result.summary.unknown_packet_count;
    result.summary.warnings.push_back(
        "Unknown global-time packet at " + packetLocation(position));
}

void unpackSpidrControl(const PacketPosition& position, UnpackResult& result) {
    const auto raw_word = position.raw_word;
    const auto packet_id = static_cast<std::uint8_t>(raw_word >> 56U);
    const auto subtype =
        static_cast<std::uint8_t>((raw_word >> 56U) & 0x0FU);
    SpidrControl control;
    control.position = position;
    control.packet_id = packet_id;
    control.subtype = subtype;

    if (packet_id == 0x50U) {
        control.type = SpidrControlType::packet_count;
        control.packet_count = raw_word & lower_48_bits;
        control.reserved_high =
            static_cast<std::uint16_t>((raw_word >> 48U) & 0x00FFU);
        ++result.summary.packet_count_control_count;
    } else {
        control.timestamp_raw = (raw_word >> 12U) & spidr_timestamp_mask;
        control.reserved_high =
            static_cast<std::uint16_t>((raw_word >> 46U) & 0x03FFU);
        control.reserved_low = static_cast<std::uint16_t>(raw_word & 0x0FFFU);
        switch (packet_id) {
            case 0x5F:
                control.type = SpidrControlType::shutter_open;
                ++result.summary.shutter_open_count;
                break;
            case 0x5A:
                control.type = SpidrControlType::shutter_close;
                ++result.summary.shutter_close_count;
                break;
            case 0x5C:
                control.type = SpidrControlType::heartbeat;
                ++result.summary.heartbeat_count;
                break;
            default:
                ++result.summary.unknown_spidr_control_count;
                result.summary.warnings.push_back(
                    "Unknown SPIDR control at " + packetLocation(position));
                break;
        }
    }

    result.spidr_controls.push_back(control);
    ++result.summary.spidr_control_count;
}

void unpackTpx3Control(const PacketPosition& position, UnpackResult& result) {
    const auto raw_word = position.raw_word;
    const auto control_value =
        static_cast<std::uint16_t>(raw_word >> 48U);
    Tpx3ControlType type = Tpx3ControlType::unknown;
    if (control_value == 0x71A0U) {
        type = Tpx3ControlType::end_of_sequential_readout;
        ++result.summary.end_of_sequential_readout_count;
    } else if (control_value == 0x71B0U) {
        type = Tpx3ControlType::end_of_data_driven_readout;
        ++result.summary.end_of_data_driven_readout_count;
    } else if (control_value == 0x7144U) {
        type = Tpx3ControlType::request_time_low;
        ++result.summary.request_time_low_count;
    } else if (control_value == 0x7145U) {
        type = Tpx3ControlType::request_time_high;
        ++result.summary.request_time_high_count;
    } else if (control_value == 0x7200U) {
        type = Tpx3ControlType::other_chip_command;
        ++result.summary.other_chip_command_count;
    } else {
        ++result.summary.unknown_tpx3_control_count;
        std::ostringstream message;
        message << "Unknown TPX3 control 0x" << std::hex << control_value
                << " at " << packetLocation(position);
        result.summary.warnings.push_back(message.str());
    }

    result.tpx3_controls.push_back({
        position,
        type,
        control_value,
        raw_word & lower_48_bits,
    });
    ++result.summary.tpx3_control_count;
}

void unpackUnknown(const PacketPosition& position, UnpackResult& result) {
    result.unknown_packets.push_back({
        position,
        static_cast<std::uint8_t>(position.raw_word >> 56U),
    });
    ++result.summary.unknown_packet_count;
    result.summary.warnings.push_back(
        "Unknown packet at " + packetLocation(position));
}

constexpr std::array<const char*, 6> analysis_directories = {
    "pixelHits",
    "tdcTriggers",
    "globalTimestamps",
    "controlPackets",
    "unknownPackets",
    "logs",
};

constexpr std::array<const char*, 5> parquet_directories = {
    "pixelHits",
    "tdcTriggers",
    "globalTimestamps",
    "controlPackets",
    "unknownPackets",
};

void findExistingOutputFiles(const std::filesystem::path& analysis_directory,
                             const std::string& raw_file_stem,
                             const std::filesystem::path& summary_path,
                             std::vector<std::string>& errors) {
    if (std::filesystem::exists(summary_path)) {
        errors.push_back("Refusing to overwrite existing summary JSON file " +
                         summary_path.string());
    }

    const std::string parquet_prefix = raw_file_stem + "-chip-";
    for (const char* directory_name : parquet_directories) {
        const auto directory = analysis_directory / directory_name;
        if (!std::filesystem::exists(directory)) {
            continue;
        }

        for (const auto& entry : std::filesystem::directory_iterator(directory)) {
            if (!entry.is_regular_file()) {
                continue;
            }
            const auto filename = entry.path().filename().string();
            if (filename.rfind(parquet_prefix, 0) == 0 &&
                entry.path().extension() == ".parquet") {
                errors.push_back("Refusing to overwrite existing Parquet file " +
                                 entry.path().string());
            }
        }
    }
}

bool createAnalysisDirectories(const std::filesystem::path& analysis_directory,
                               std::vector<std::string>& errors) {
    try {
        for (const char* directory_name : analysis_directories) {
            std::filesystem::create_directories(
                analysis_directory / directory_name);
        }
        return true;
    } catch (const std::exception& error) {
        errors.push_back("Failed to create analysis directories: " +
                         std::string(error.what()));
        return false;
    }
}

}  // namespace

void unpackPacket(const std::uint64_t raw_word,
                  const std::uint8_t chip_index,
                  const std::size_t chunk_index,
                  const std::size_t packet_index,
                  UnpackResult& result) {
    ++result.summary.packets_read;
    const auto position =
        makePosition(raw_word, chip_index, chunk_index, packet_index);
    const auto packet_type =
        static_cast<std::uint8_t>((raw_word >> 60U) & 0x0FU);

    switch (packet_type) {
        case 0x0A:
            unpackIntegratedTot(position, result);
            break;
        case 0x0B:
            unpackPixelHit(position, result);
            break;
        case 0x06:
            unpackTdcHit(position, result);
            break;
        case 0x04:
            unpackGlobalTime(position, result);
            break;
        case 0x05:
            unpackSpidrControl(position, result);
            break;
        case 0x07:
            unpackTpx3Control(position, result);
            break;
        default:
            unpackUnknown(position, result);
            break;
    }
}

UnpackResult unpack(std::istream& input) {
    UnpackResult result;
    std::array<std::optional<GlobalTimeLow>, 256> pending_global_time_lows;
    std::size_t chunk_index = 0;

    while (true) {
        const auto chunk_read = readChunkHeader(input, chunk_index);
        if (chunk_read.end_of_stream) {
            break;
        }

        result.summary.bytes_read += chunk_read.bytes_read;

        if (!chunk_read.success) {
            if (chunk_read.error) {
                result.summary.errors.push_back(*chunk_read.error);
            }
            if (chunk_read.error &&
                chunk_read.error->find("Truncated") != std::string::npos) {
                ++result.summary.truncated_chunk_count;
            } else {
                ++result.summary.malformed_chunk_count;
            }
            break;
        }

        result.chunk_headers.push_back({
            chunk_read.raw_header,
            chunk_read.chunk_size_bytes,
            chunk_read.mode_or_reserved,
            chunk_read.chip_index,
            chunk_index,
        });
        ++result.summary.chunks_read;

        if (chunk_read.chunk_size_bytes % 8U != 0U) {
            ++result.summary.malformed_chunk_count;
            result.summary.errors.push_back(
                "Chunk size is not divisible by 8 at chunk " +
                std::to_string(chunk_index));
            break;
        }

        const auto packet_count =
            static_cast<std::size_t>(chunk_read.chunk_size_bytes / 8U);
        bool chunk_truncated = false;
        for (std::size_t packet_index = 0;
             packet_index < packet_count;
             ++packet_index) {
            const auto packet_read =
                readPacketWord(input, chunk_index, packet_index);
            result.summary.bytes_read += packet_read.bytes_read;

            if (!packet_read.success) {
                ++result.summary.truncated_chunk_count;
                if (packet_read.error) {
                    result.summary.errors.push_back(*packet_read.error);
                }
                chunk_truncated = true;
                break;
            }

            const auto low_count_before = result.global_time_lows.size();
            const auto high_count_before = result.global_time_highs.size();
            unpackPacket(packet_read.raw_word,
                         chunk_read.chip_index,
                         chunk_index,
                         packet_index,
                         result);

            if (result.global_time_lows.size() > low_count_before) {
                pending_global_time_lows[chunk_read.chip_index] =
                    result.global_time_lows.back();
            }
            if (result.global_time_highs.size() > high_count_before &&
                pending_global_time_lows[chunk_read.chip_index].has_value()) {
                const auto& low =
                    pending_global_time_lows[chunk_read.chip_index].value();
                const auto& high = result.global_time_highs.back();
                result.global_timestamps.push_back({
                    low.position,
                    high.position,
                    high.global_time_high_raw,
                    low.global_time_low_raw,
                    (static_cast<std::uint64_t>(
                         high.global_time_high_raw)
                     << 32U) |
                        low.global_time_low_raw,
                });
                ++result.summary.global_timestamp_count;
                pending_global_time_lows[chunk_read.chip_index].reset();
            }
        }

        if (chunk_truncated) {
            break;
        }
        ++chunk_index;
    }

    return result;
}

WorkflowResult runTwoPassWorkflow(std::istream& input,
                                  const std::string& source_file_path,
                                  const std::string& analysis_directory) {
    using Clock = std::chrono::high_resolution_clock;
    using Duration = std::chrono::duration<double>;

    auto workflow_start = Clock::now();

    WorkflowResult workflow_result;
    workflow_result.analysis_directory = analysis_directory;
    workflow_result.summary.source_file_path = source_file_path;
    workflow_result.summary.analysis_directory = analysis_directory;

    const std::string raw_file_stem =
        std::filesystem::path(source_file_path).stem().string();
    if (raw_file_stem.empty()) {
        workflow_result.errors.push_back(
            "Cannot derive an output filename from the raw TPX3 file path");
        workflow_result.summary.status = "failed";
        return workflow_result;
    }

    workflow_result.summary.summary_json_file =
        "logs/" + raw_file_stem + "-unpacker-summary.json";
    const auto summary_path = std::filesystem::path(analysis_directory) /
                              workflow_result.summary.summary_json_file;

    try {
        findExistingOutputFiles(analysis_directory, raw_file_stem,
                                summary_path, workflow_result.errors);
    } catch (const std::exception& error) {
        workflow_result.errors.push_back(
            "Failed to check existing analysis files: " +
            std::string(error.what()));
    }
    if (!workflow_result.errors.empty()) {
        workflow_result.summary.status = "failed";
        return workflow_result;
    }

    // Pass 1: Unpack and decode all packets
    auto unpack_start = Clock::now();
    auto unpack_result = unpack(input);
    auto unpack_end = Clock::now();
    workflow_result.summary.timing_diagnostics.unpacking_seconds =
        Duration(unpack_end - unpack_start).count();
    workflow_result.summary.unpack_summary = unpack_result.summary;
    workflow_result.summary.source_file_bytes = unpack_result.summary.bytes_read;

    if (!unpack_result.summary.errors.empty()) {
        workflow_result.success = false;
        workflow_result.errors = unpack_result.summary.errors;
        workflow_result.summary.status = "failed";
        return workflow_result;
    }

    // Assign source packet order (needed for sorting)
    assignSourcePacketOrder(unpack_result);

    // Build anchor indices per chip (from paired global timestamps)
    // For now, assume single chip (chip 0)
    auto epoch_start = Clock::now();
    AnchorIndexDiagnostics anchor_diag;
    ChipAnchorIndex chip0_anchors = buildChipAnchorIndex(
        unpack_result.global_timestamps, 0, anchor_diag);
    workflow_result.summary.anchor_diagnostics = anchor_diag;

    // Assign epochs to unwrap timestamps for chip 0
    EpochAssignmentDiagnostics epoch_diag;
    assignEpochsToPixels(unpack_result.pixel_hits, chip0_anchors, 0, epoch_diag);
    assignEpochsToTdcs(unpack_result.tdc_hits, chip0_anchors, 0, epoch_diag);
    assignEpochsToControls(unpack_result.spidr_controls, chip0_anchors, 0, epoch_diag);
    auto epoch_end = Clock::now();
    workflow_result.summary.timing_diagnostics.epoch_assignment_seconds =
        Duration(epoch_end - epoch_start).count();
    workflow_result.summary.epoch_diagnostics = epoch_diag;

    // Convert decoded packets to the rows written to Parquet.
    auto conversion_start = Clock::now();
    OutputRows output_rows;

    for (const auto& pixel : unpack_result.pixel_hits) {
        if (auto row = convertPixelToOutputRow(pixel)) {
            output_rows.pixels.push_back(*row);
        }
    }

    for (const auto& tdc : unpack_result.tdc_hits) {
        if (auto row = convertTdcToOutputRow(tdc)) {
            output_rows.tdcs.push_back(*row);
        }
    }

    for (const auto& global : unpack_result.global_timestamps) {
        output_rows.globals.push_back(convertGlobalToOutputRow(global));
    }

    for (const auto& control : unpack_result.spidr_controls) {
        output_rows.controls.push_back(convertSpidrControlToOutputRow(control));
    }

    for (const auto& control : unpack_result.tpx3_controls) {
        output_rows.controls.push_back(convertTpx3ControlToOutputRow(control));
    }

    for (const auto& unknown : unpack_result.unknown_packets) {
        output_rows.unknowns.push_back(convertUnknownToOutputRow(unknown));
    }

    auto conversion_end = Clock::now();
    workflow_result.summary.timing_diagnostics.conversion_seconds =
        Duration(conversion_end - conversion_start).count();

    // Sort the exact rows that will be split into Parquet part files.
    auto sort_start = Clock::now();
    SortingDiagnostics sort_diag;
    sortAllOutputRows(output_rows, sort_diag);
    auto sort_end = Clock::now();
    workflow_result.summary.timing_diagnostics.sorting_seconds =
        Duration(sort_end - sort_start).count();
    workflow_result.summary.sorting_diagnostics = sort_diag;

    // Create the shared category and diagnostic directories.
    if (!createAnalysisDirectories(analysis_directory,
                                   workflow_result.errors)) {
        workflow_result.success = false;
        workflow_result.summary.status = "failed";
        return workflow_result;
    }

    // Write Parquet files per chip
    auto writing_start = Clock::now();
    ParquetWriterDiagnostics writer_diag;
    ParquetWriterConfig writer_config;
    writer_config.analysis_directory = analysis_directory;
    writer_config.raw_file_stem = raw_file_stem;
    writer_config.chip_index = 0;  // Single chip for now

    writePixelHitsParquet(output_rows.pixels, writer_config, writer_diag);
    writeTdcTriggersParquet(output_rows.tdcs, writer_config, writer_diag);
    writeGlobalTimestampsParquet(output_rows.globals, writer_config, writer_diag);
    writeControlPacketsParquet(output_rows.controls, writer_config, writer_diag);
    writeUnknownPacketsParquet(output_rows.unknowns, writer_config, writer_diag);
    auto writing_end = Clock::now();
    workflow_result.summary.timing_diagnostics.parquet_writing_seconds =
        Duration(writing_end - writing_start).count();

    workflow_result.summary.writer_diagnostics = writer_diag;

    // Calculate total time (before writing JSON so it's included)
    auto workflow_end = Clock::now();
    workflow_result.summary.timing_diagnostics.total_seconds =
        Duration(workflow_end - workflow_start).count();

    workflow_result.summary.status = writer_diag.errors.empty() ? "complete" : "partial";

    try {
        writeSummaryJsonFile(summary_path.string(), workflow_result.summary);
    } catch (const std::exception& error) {
        workflow_result.errors.push_back(
            "Failed to write summary JSON file " + summary_path.string() +
            ": " + error.what());
    }

    workflow_result.success = writer_diag.errors.empty() &&
                              workflow_result.errors.empty();
    workflow_result.errors.insert(workflow_result.errors.end(),
                                 writer_diag.errors.begin(),
                                 writer_diag.errors.end());

    return workflow_result;
}

}  // namespace hermes_tpx3_spidr
