#ifndef HERMES_TPX3_SPIDR_DIAGNOSTICS_H
#define HERMES_TPX3_SPIDR_DIAGNOSTICS_H

#include <iosfwd>

#include "unpacker.h"

namespace hermes_tpx3_spidr {

void printSummary(const UnpackSummary& summary, std::ostream& output);
void printMessages(const UnpackSummary& summary, std::ostream& output);

}  // namespace hermes_tpx3_spidr

#endif
