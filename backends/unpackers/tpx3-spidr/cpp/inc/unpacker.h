#ifndef HERMES_TPX3_SPIDR_UNPACKER_H
#define HERMES_TPX3_SPIDR_UNPACKER_H

#include "packet_types.h"

#include <cstddef>
#include <cstdint>
#include <istream>

namespace hermes_tpx3_spidr {

void unpackPacket(std::uint64_t raw_word,
                  std::uint8_t chip_index,
                  std::size_t chunk_index,
                  std::size_t packet_index,
                  UnpackResult& result);

UnpackResult unpack(std::istream& input);

}  // namespace hermes_tpx3_spidr

#endif
