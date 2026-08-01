#ifndef HERMES_TPX3_SPIDR_CHUNK_READER_H
#define HERMES_TPX3_SPIDR_CHUNK_READER_H

#include <array>
#include <cstdint>
#include <istream>
#include <optional>
#include <string>
namespace hermes_tpx3_spidr {

std::uint64_t littleEndianWord(const std::array<unsigned char, 8>& bytes);

struct ChunkReadResult {
    bool success = false;
    bool end_of_stream = false;
    std::uint64_t raw_header = 0;
    std::uint8_t chip_index = 0;
    std::uint8_t mode_or_reserved = 0;
    std::uint16_t chunk_size_bytes = 0;
    std::size_t bytes_read = 0;
    std::optional<std::string> error;
};

ChunkReadResult readChunkHeader(std::istream& input, std::size_t chunk_index);

struct PacketReadResult {
    bool success = false;
    std::uint64_t raw_word = 0;
    std::size_t bytes_read = 0;
    std::optional<std::string> error;
};

PacketReadResult readPacketWord(std::istream& input,
                                std::size_t chunk_index,
                                std::size_t packet_index);

}  // namespace hermes_tpx3_spidr

#endif
