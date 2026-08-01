#ifndef HERMES_PHOTON_CLUSTERER_RECONSTRUCTION_H
#define HERMES_PHOTON_CLUSTERER_RECONSTRUCTION_H

#include <cstdint>
#include <functional>
#include <vector>

#include "cluster_filter.h"
#include "photon.h"
#include "photon_writer.h"
#include "pixel_reader.h"
#include "settings.h"
#include "timewalk.h"

namespace hermes_photon_clusterer {

// Tallies gathered while reconstructing one chip, mapping directly onto the
// reconstruction summary counts.
struct ReconstructionCounts {
    std::uint64_t pixel_rows_read = 0;
    std::uint64_t pixel_rows_below_min_tot = 0;
    std::uint64_t components_formed = 0;
    std::uint64_t photon_count = 0;
    std::uint64_t rejected_component_count = 0;
    RejectionCounts rejection_counts;
    std::uint64_t saturated_pixel_count = 0;
    std::uint64_t bridged_components_count = 0;
};

// Reconstructed photons and optional source-pixel rows for one chip.
struct PhotonReconstruction {
    std::vector<Photon> photons;
    std::vector<PhotonPixelRow> photon_pixels;
    ReconstructionCounts counts;
};

// Reconstructs photons for one chip from a raw pixel stream.
//
// next_hit yields source pixels in non-decreasing timestamp order (as the reader
// guarantees per chip). This applies the per-pixel min-ToT filter (counting
// dropped rows), streams the survivors through connected-components clustering on
// integer ticks, evaluates each closed cluster against the shape/ToT filters, and
// builds a photon for every accepted cluster. When correction is non-null the
// photon time is the earliest time-walk-corrected ToA; otherwise it is the
// earliest raw ToA. When collect_pixels is true, photon_pixels rows are emitted
// for accepted photons, each tagged with its photon_id (the photon's index in
// the photons vector).
PhotonReconstruction reconstructPhotons(
    const std::function<bool(PixelHit&)>& next_hit,
    const ClusteringSettings& settings,
    const TimewalkCorrection* correction,
    bool collect_pixels);

}  // namespace hermes_photon_clusterer

#endif
