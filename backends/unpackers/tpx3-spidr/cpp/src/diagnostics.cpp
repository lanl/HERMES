#include "diagnostics.h"

#include <ostream>

namespace hermes_tpx3_spidr {

void printSummary(const UnpackSummary& summary, std::ostream& output) {
    output << "bytes=" << summary.bytes_read
           << " chunks=" << summary.chunks_read
           << " packets=" << summary.packets_read << '\n'
           << "integrated_tot=" << summary.integrated_tot_count
           << " pixel_hits=" << summary.pixel_hit_count << '\n'
           << "tdc_hits=" << summary.tdc_hit_count
           << " tdc1_rising=" << summary.tdc1_rising_count
           << " tdc1_falling=" << summary.tdc1_falling_count
           << " tdc2_rising=" << summary.tdc2_rising_count
           << " tdc2_falling=" << summary.tdc2_falling_count
           << " unknown_tdc_edge=" << summary.unknown_tdc_edge_count << '\n'
           << "global_time_low=" << summary.global_time_low_count
           << " global_time_high=" << summary.global_time_high_count
           << " global_timestamps=" << summary.global_timestamp_count << '\n'
           << "spidr_controls=" << summary.spidr_control_count
           << " packet_count=" << summary.packet_count_control_count
           << " shutter_open=" << summary.shutter_open_count
           << " shutter_close=" << summary.shutter_close_count
           << " heartbeat=" << summary.heartbeat_count
           << " unknown_spidr=" << summary.unknown_spidr_control_count << '\n'
           << "tpx3_controls=" << summary.tpx3_control_count
           << " sequential_end="
           << summary.end_of_sequential_readout_count
           << " data_driven_end="
           << summary.end_of_data_driven_readout_count
           << " unknown_tpx3=" << summary.unknown_tpx3_control_count << '\n'
           << "unknown_packets=" << summary.unknown_packet_count << '\n'
           << "malformed_chunks=" << summary.malformed_chunk_count
           << " truncated_chunks=" << summary.truncated_chunk_count
           << " invalid_tdc_fine="
           << summary.invalid_tdc_fine_value_count
           << " warnings=" << summary.warnings.size()
           << " errors=" << summary.errors.size() << '\n';
}

void printMessages(const UnpackSummary& summary, std::ostream& output) {
    for (const auto& warning : summary.warnings) {
        output << "Warning: " << warning << '\n';
    }
    for (const auto& error : summary.errors) {
        output << "Error: " << error << '\n';
    }
}

}  // namespace hermes_tpx3_spidr
