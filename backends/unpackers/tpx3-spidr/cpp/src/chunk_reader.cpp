#include "chunk_reader.h"

#include <string>

namespace hermes_tpx3_spidr {
namespace {

constexpr std::uint32_t tpx3_signature = 0x33585054U;

}  // namespace

std::uint64_t littleEndianWord(const std::array<unsigned char, 8>& bytes) {
    std::uint64_t word = 0;
    for (std::size_t index = 0; index < bytes.size(); ++index) {
        word |= static_cast<std::uint64_t>(bytes[index]) << (index * 8U);
    }
    return word;
}

ChunkReadResult readChunkHeader(std::istream& input,
                                const std::size_t chunk_index) {
    ChunkReadResult result;
    std::array<unsigned char, 8> header_bytes{};
    input.read(reinterpret_cast<char*>(header_bytes.data()),
               static_cast<std::streamsize>(header_bytes.size()));
    const auto header_bytes_read = input.gcount();

    if (header_bytes_read == 0) {
        result.end_of_stream = true;
        return result;
    }

    result.bytes_read = static_cast<std::size_t>(header_bytes_read);

    if (header_bytes_read !=
        static_cast<std::streamsize>(header_bytes.size())) {
        result.error = "Truncated chunk header at chunk " +
                       std::to_string(chunk_index);
        return result;
    }

    result.raw_header = littleEndianWord(header_bytes);
    if (static_cast<std::uint32_t>(result.raw_header) != tpx3_signature) {
        result.error = "Invalid TPX3 signature at chunk " +
                       std::to_string(chunk_index);
        return result;
    }

    result.chip_index =
        static_cast<std::uint8_t>((result.raw_header >> 32U) & 0xFFU);
    result.mode_or_reserved =
        static_cast<std::uint8_t>((result.raw_header >> 40U) & 0xFFU);
    result.chunk_size_bytes =
        static_cast<std::uint16_t>((result.raw_header >> 48U) & 0xFFFFU);

    result.success = true;
    return result;
}

PacketReadResult readPacketWord(std::istream& input,
                                const std::size_t chunk_index,
                                const std::size_t packet_index) {
    PacketReadResult result;
    std::array<unsigned char, 8> packet_bytes{};
    input.read(reinterpret_cast<char*>(packet_bytes.data()),
               static_cast<std::streamsize>(packet_bytes.size()));
    const auto packet_bytes_read = input.gcount();

    result.bytes_read = static_cast<std::size_t>(packet_bytes_read);

    if (packet_bytes_read !=
        static_cast<std::streamsize>(packet_bytes.size())) {
        result.error = "Truncated chunk content at chunk " +
                       std::to_string(chunk_index) + ", packet " +
                       std::to_string(packet_index);
        return result;
    }

    result.raw_word = littleEndianWord(packet_bytes);
    result.success = true;
    return result;
}

}  // namespace hermes_tpx3_spidr
