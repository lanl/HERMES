#include "test_helpers.h"

#include <cstdint>
#include <string>

#include "unpacker.h"

namespace {

std::uint64_t makePixel(const std::uint16_t spidr_time) {
    return (0xBULL << 60U) | spidr_time;
}

std::uint64_t makeGlobalLow(const std::uint8_t reserved,
                            const std::uint32_t low,
                            const std::uint16_t spidr_time) {
    return (0x44ULL << 56U) |
           (static_cast<std::uint64_t>(reserved) << 48U) |
           (static_cast<std::uint64_t>(low) << 16U) | spidr_time;
}

std::uint64_t makeGlobalHigh(const std::uint32_t reserved,
                             const std::uint16_t high,
                             const std::uint16_t spidr_time) {
    return (0x45ULL << 56U) |
           (static_cast<std::uint64_t>(reserved & 0x00FFFFFFU) << 32U) |
           (static_cast<std::uint64_t>(high) << 16U) | spidr_time;
}

void testChunkHeaderAndZeroLength(TestContext& test) {
    std::string bytes;
    const auto header = makeChunkHeader(3U, 0x5AU, 0U);
    appendLittleEndianWord(bytes, header);
    auto input = makeInput(bytes);
    const auto result = hermes_tpx3_spidr::unpack(input);

    test.expectEqual(result.summary.bytes_read, std::uint64_t{8},
                     "zero chunk bytes read");
    test.expectEqual(result.summary.chunks_read, std::uint64_t{1},
                     "zero chunk count");
    test.expectEqual(result.summary.packets_read, std::uint64_t{0},
                     "zero chunk packet count");
    test.expect(result.summary.errors.empty(), "zero chunk has no error");
    test.expectEqual(result.chunk_headers[0].raw_header, header,
                     "raw chunk header");
    test.expectEqual(result.chunk_headers[0].chip_index, std::uint8_t{3},
                     "chunk chip index");
    test.expectEqual(result.chunk_headers[0].mode_or_reserved,
                     std::uint8_t{0x5A}, "chunk mode/reserved byte");
    test.expectEqual(result.chunk_headers[0].chunk_size_bytes,
                     std::uint16_t{0}, "zero chunk size");
    test.expectEqual(result.chunk_headers[0].chunk_index, std::size_t{0},
                     "zero-based chunk index");
}

void testMalformedAndTruncatedInput(TestContext& test) {
    {
        std::string bytes("TPX3", 4);
        auto input = makeInput(bytes);
        const auto result = hermes_tpx3_spidr::unpack(input);
        test.expectEqual(result.summary.truncated_chunk_count,
                         std::uint64_t{1}, "truncated header count");
        test.expectEqual(result.summary.bytes_read, std::uint64_t{4},
                         "truncated header bytes");
        test.expectEqual(result.summary.errors.size(), std::size_t{1},
                         "truncated header errors");
    }
    {
        std::string bytes;
        appendLittleEndianWord(bytes, 0x0000000033585055ULL);
        auto input = makeInput(bytes);
        const auto result = hermes_tpx3_spidr::unpack(input);
        test.expectEqual(result.summary.malformed_chunk_count,
                         std::uint64_t{1}, "invalid signature count");
        test.expectEqual(result.summary.chunks_read, std::uint64_t{0},
                         "invalid signature not counted as chunk");
    }
    {
        std::string bytes;
        appendLittleEndianWord(bytes, makeChunkHeader(0U, 0U, 10U));
        auto input = makeInput(bytes);
        const auto result = hermes_tpx3_spidr::unpack(input);
        test.expectEqual(result.summary.malformed_chunk_count,
                         std::uint64_t{1}, "invalid chunk length count");
        test.expectEqual(result.summary.chunks_read, std::uint64_t{1},
                         "complete malformed header counted");
        test.expectEqual(result.summary.packets_read, std::uint64_t{0},
                         "invalid chunk length reads no packet");
    }
    {
        std::string bytes;
        appendLittleEndianWord(bytes, makeChunkHeader(0U, 0U, 16U));
        appendLittleEndianWord(bytes, makePixel(1U));
        bytes.append("abcd", 4);
        auto input = makeInput(bytes);
        const auto result = hermes_tpx3_spidr::unpack(input);
        test.expectEqual(result.summary.truncated_chunk_count,
                         std::uint64_t{1}, "truncated content count");
        test.expectEqual(result.summary.packets_read, std::uint64_t{1},
                         "only complete packet decoded");
        test.expectEqual(result.summary.bytes_read, std::uint64_t{20},
                         "truncated content actual bytes");
    }
}

void testMultipleChunksAndChips(TestContext& test) {
    std::string bytes;
    appendLittleEndianWord(bytes, makeChunkHeader(1U, 0U, 8U));
    appendLittleEndianWord(bytes, makePixel(0x1111U));
    appendLittleEndianWord(bytes, makeChunkHeader(2U, 1U, 8U));
    appendLittleEndianWord(bytes, 0x8123456789ABCDEFULL);
    auto input = makeInput(bytes);
    const auto result = hermes_tpx3_spidr::unpack(input);

    test.expectEqual(result.summary.chunks_read, std::uint64_t{2},
                     "multiple chunk count");
    test.expectEqual(result.summary.packets_read, std::uint64_t{2},
                     "multiple chunk packet count");
    test.expectEqual(result.pixel_hits[0].position.chip_index,
                     std::uint8_t{1}, "first chunk chip");
    test.expectEqual(result.pixel_hits[0].position.chunk_index,
                     std::size_t{0}, "first chunk index");
    test.expectEqual(result.unknown_packets[0].position.chip_index,
                     std::uint8_t{2}, "second chunk chip");
    test.expectEqual(result.unknown_packets[0].position.chunk_index,
                     std::size_t{1}, "second chunk index");
}

void testGlobalTimePairing(TestContext& test) {
    std::string bytes;
    appendLittleEndianWord(bytes, makeChunkHeader(1U, 0U, 8U));
    appendLittleEndianWord(
        bytes, makeGlobalLow(0xAAU, 0xFFFFFFFFU, 0x1234U));
    appendLittleEndianWord(bytes, makeChunkHeader(2U, 0U, 8U));
    appendLittleEndianWord(
        bytes, makeGlobalHigh(0x654321U, 0x1111U, 0x2345U));
    appendLittleEndianWord(bytes, makeChunkHeader(1U, 0U, 8U));
    appendLittleEndianWord(
        bytes, makeGlobalHigh(0x123456U, 0xFFFFU, 0x3456U));
    auto input = makeInput(bytes);
    const auto result = hermes_tpx3_spidr::unpack(input);

    test.expectEqual(result.summary.global_time_low_count, std::uint64_t{1},
                     "global low count");
    test.expectEqual(result.summary.global_time_high_count, std::uint64_t{2},
                     "global high count");
    test.expectEqual(result.summary.global_timestamp_count,
                     std::uint64_t{1}, "paired global count");
    test.expectEqual(result.summary.packets_read, std::uint64_t{3},
                     "global stream packet count");
    test.expectEqual(result.global_time_lows[0].reserved, std::uint8_t{0xAA},
                     "global low reserved byte");
    test.expectEqual(result.global_time_lows[0].spidr_time_raw,
                     std::uint16_t{0x1234}, "global low SPIDR time");
    test.expectEqual(result.global_time_highs[1].reserved,
                     std::uint32_t{0x123456},
                     "global high reserved bits");
    test.expectEqual(result.global_timestamps[0].global_time_raw,
                     std::uint64_t{0xFFFFFFFFFFFF},
                     "48-bit global rollover boundary");
    test.expectEqual(result.global_timestamps[0].low_packet.chunk_index,
                     std::size_t{0}, "paired low chunk position");
    test.expectEqual(result.global_timestamps[0].high_packet.chunk_index,
                     std::size_t{2}, "paired high chunk position");
}

}  // namespace

int main() {
    TestContext test;
    testChunkHeaderAndZeroLength(test);
    testMalformedAndTruncatedInput(test);
    testMultipleChunksAndChips(test);
    testGlobalTimePairing(test);
    return test.finish();
}
