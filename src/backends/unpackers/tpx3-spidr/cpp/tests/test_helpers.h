#ifndef HERMES_TPX3_SPIDR_TEST_HELPERS_H
#define HERMES_TPX3_SPIDR_TEST_HELPERS_H

#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>

class TestContext {
  public:
    void expect(const bool condition, const std::string& message) {
        if (!condition) {
            std::cerr << "FAIL: " << message << '\n';
            ++failures_;
        }
    }

    template <typename Actual, typename Expected>
    void expectEqual(const Actual& actual,
                     const Expected& expected,
                     const std::string& message) {
        if (actual != expected) {
            std::cerr << "FAIL: " << message << " (actual=" << actual
                      << ", expected=" << expected << ")\n";
            ++failures_;
        }
    }

    int finish() const {
        if (failures_ == 0) {
            return 0;
        }
        std::cerr << failures_ << " assertion(s) failed\n";
        return 1;
    }

  private:
    int failures_ = 0;
};

inline void appendLittleEndianWord(std::string& bytes,
                                   const std::uint64_t word) {
    for (unsigned int index = 0; index < 8U; ++index) {
        bytes.push_back(static_cast<char>((word >> (index * 8U)) & 0xFFU));
    }
}

inline std::uint64_t makeChunkHeader(const std::uint8_t chip_index,
                                     const std::uint8_t mode_or_reserved,
                                     const std::uint16_t chunk_size_bytes) {
    return (static_cast<std::uint64_t>(chunk_size_bytes) << 48U) |
           (static_cast<std::uint64_t>(mode_or_reserved) << 40U) |
           (static_cast<std::uint64_t>(chip_index) << 32U) |
           0x33585054U;
}

inline std::istringstream makeInput(const std::string& bytes) {
    return std::istringstream(bytes, std::ios::in | std::ios::binary);
}

#endif
