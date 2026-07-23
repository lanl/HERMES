#ifndef HERMES_TPX3_SPIDR_UNPACKER_H
#define HERMES_TPX3_SPIDR_UNPACKER_H

#include "packet_types.h"
#include "output_rows.h"
#include "summary_json.h"

#include <cstddef>
#include <cstdint>
#include <istream>
#include <string>
#include <vector>

namespace hermes_tpx3_spidr {

void unpackPacket(std::uint64_t raw_word,
                  std::uint8_t chip_index,
                  std::size_t chunk_index,
                  std::size_t packet_index,
                  UnpackResult& result);

UnpackResult unpack(std::istream& input);

struct WorkflowResult {
    bool success = false;
    std::string analysis_directory;
    SummaryJsonContent summary;
    std::vector<std::string> errors;
};

WorkflowResult runTwoPassWorkflow(std::istream& input,
                                  const std::string& source_file_path,
                                  const std::string& analysis_directory);

}  // namespace hermes_tpx3_spidr

#endif
