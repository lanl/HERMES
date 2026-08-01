#ifndef HERMES_PHOTON_CLUSTERER_TIMEWALK_H
#define HERMES_PHOTON_CLUSTERER_TIMEWALK_H

#include <cstdint>
#include <string>

#include "clustering.h"

namespace hermes_photon_clusterer {

// A validated time-walk correction loaded from a calibration JSON file. The
// correction predicts each pixel's leading-edge delay relative to a high-ToT
// reference (high_tot_anchor) and is subtracted from the raw ToA.
//
//   inverse: delta_t(tot) = a * (1 / (tot + b) - 1 / (anchor + b))
//   linear:  delta_t(tot) = m * (tot - anchor)
//
// Times are in canonical ticks. correctedToa returns float64 because the
// correction is fractional.
struct TimewalkCorrection {
    enum class Model { kLinear, kInverse };

    Model model = Model::kInverse;
    // inverse parameters
    double a = 0.0;
    double b = 0.0;
    // linear parameter
    double m = 0.0;
    double high_tot_anchor = 0.0;
};

// Loads and strictly validates a correction file. Throws std::runtime_error on a
// missing file, malformed JSON, an unknown model, missing model parameters, or a
// time_unit other than "canonical_ticks".
TimewalkCorrection loadTimewalkCorrection(const std::string& path);

// Corrected leading-edge time for a single pixel, in fractional canonical ticks.
double correctedToa(std::uint64_t raw_toa,
                    std::uint16_t tot_raw,
                    const TimewalkCorrection& correction);

// Earliest corrected source-pixel ToA in the cluster (the photon leading edge).
double earliestCorrectedToa(const PixelCluster& cluster,
                            const TimewalkCorrection& correction);

}  // namespace hermes_photon_clusterer

#endif
