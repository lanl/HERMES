#ifndef HERMES_TPX3_SPIDR_TIMESTAMP_CALCULATOR_H
#define HERMES_TPX3_SPIDR_TIMESTAMP_CALCULATOR_H

#include "packet_types.h"
#include "output_rows.h"

#include <optional>

namespace hermes_tpx3_spidr {

std::uint64_t calculatePixelTimestamp(const PixelHit& pixel);

std::optional<std::uint64_t> calculateTdcTimestamp(const TdcHit& tdc);

std::uint8_t getTdcTriggerType(const TdcHit& tdc);

std::uint64_t calculateGlobalTimestamp(const GlobalTimestamp& global);

std::optional<std::uint64_t> calculateControlTimestamp(const SpidrControl& control);

std::optional<PixelOutputRow> convertPixelToOutputRow(const PixelHit& pixel);

std::optional<TdcOutputRow> convertTdcToOutputRow(const TdcHit& tdc);

GlobalOutputRow convertGlobalToOutputRow(const GlobalTimestamp& global);

ControlOutputRow convertSpidrControlToOutputRow(const SpidrControl& control);

ControlOutputRow convertTpx3ControlToOutputRow(const Tpx3Control& control);

UnknownOutputRow convertUnknownToOutputRow(const UnknownPacket& unknown);

}  // namespace hermes_tpx3_spidr

#endif
