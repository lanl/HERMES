#include <cstddef>
#include <vector>

#include "reconstruction.h"
#include "settings.h"
#include "test_helpers.h"
#include "timewalk.h"

namespace {

using hermes_photon_clusterer::ClusteringSettings;
using hermes_photon_clusterer::PhotonReconstruction;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::TimewalkCorrection;
using hermes_photon_clusterer::correctedToa;
using hermes_photon_clusterer::reconstructPhotons;

// Runs the reconstruction over a fixed hit list, streamed in order.
PhotonReconstruction run(std::vector<PixelHit> hits,
                         const ClusteringSettings& settings,
                         const TimewalkCorrection* correction,
                         bool collect_pixels) {
    std::size_t cursor = 0;
    auto next_hit = [&](PixelHit& out) {
        if (cursor >= hits.size()) {
            return false;
        }
        out = hits[cursor++];
        return true;
    };
    return reconstructPhotons(next_hit, settings, correction, collect_pixels);
}

}  // namespace

int main() {
    TestContext test;

    // The example inverse time-walk calibration (calibrations/tpx3/
    // time-walk_example.json), constructed directly so the test is self-contained.
    TimewalkCorrection correction;
    correction.model = TimewalkCorrection::Model::kInverse;
    correction.a = 1254855.5798924663;
    correction.b = 10.69863711765447;
    correction.high_tot_anchor = 23.0;

    // Built-in defaults: min_pixel_tot_raw=1, cluster size 2..64, aspect<=3,
    // filled>=0.5, 8-connected, generous time gate.
    ClusteringSettings settings;

    // A synthetic stream, non-decreasing in timestamp, of well-separated clusters:
    //   1. a compact 2x2 photon (accepted)
    //   2. a cosmic-ray-like 5x1 track (rejected: aspect ratio 5 > 3)
    //   3. a single noise pixel at tot 0 (dropped by the per-pixel min-ToT filter)
    //   4. a compact L of three same-ToA, differing-ToT pixels (accepted; drives
    //      the time-walk check)
    //   5. a two-pixel photon with one saturated pixel (accepted; saturated flag)
    const std::uint64_t kToa4 = 3000000;
    std::vector<PixelHit> hits = {
        // 1. compact 2x2
        PixelHit{10, 10, 50, 1000},
        PixelHit{11, 10, 50, 1001},
        PixelHit{10, 11, 50, 1002},
        PixelHit{11, 11, 50, 1003},
        // 2. horizontal cosmic-ray track (5x1)
        PixelHit{20, 30, 50, 1000000},
        PixelHit{21, 30, 50, 1000001},
        PixelHit{22, 30, 50, 1000002},
        PixelHit{23, 30, 50, 1000003},
        PixelHit{24, 30, 50, 1000004},
        // 3. noise pixel below min ToT
        PixelHit{5, 5, 0, 2000000},
        // 4. same-ToA, differing-ToT L (anchor, low, high)
        PixelHit{40, 40, 23, kToa4},
        PixelHit{41, 40, 8, kToa4},
        PixelHit{40, 41, 100, kToa4},
        // 5. two-pixel photon with a saturated pixel
        PixelHit{50, 50, 1023, 4000000},
        PixelHit{51, 50, 30, 4000001},
    };

    // Uncorrected pass: photon time is the earliest raw source ToA.
    {
        auto result = run(hits, settings, nullptr, false);
        test.expectEqual(result.counts.pixel_rows_read, std::uint64_t{15},
                         "every source row is counted");
        test.expectEqual(result.counts.pixel_rows_below_min_tot,
                         std::uint64_t{1}, "the tot=0 noise pixel is dropped");
        test.expectEqual(result.counts.components_formed, std::uint64_t{4},
                         "four clusters form (noise pixel never clusters)");
        test.expectEqual(result.counts.photon_count, std::uint64_t{3},
                         "three clusters are accepted as photons");
        test.expectEqual(result.counts.rejected_component_count,
                         std::uint64_t{1}, "the cosmic-ray track is rejected");
        test.expectEqual(result.counts.rejection_counts.above_max_aspect_ratio,
                         std::uint64_t{1}, "rejection reason is aspect ratio");
        test.expectEqual(result.counts.saturated_pixel_count, std::uint64_t{1},
                         "one accepted photon has a saturated pixel");

        if (result.photons.size() == 3) {
            // Photons are in cluster-close (time) order: 2x2, L, saturated pair.
            const auto& compact = result.photons[0];
            test.expect(compact.x == 10.5 && compact.y == 10.5,
                        "compact photon position is the arithmetic mean");
            test.expectEqual(compact.tot, std::uint64_t{200},
                             "compact photon tot is the summed tot_raw");
            test.expectEqual(compact.timestamp_canonical, 1000.0,
                             "uncorrected time is the earliest raw ToA");

            const auto& walk = result.photons[1];
            test.expectEqual(walk.timestamp_canonical,
                             static_cast<double>(kToa4),
                             "uncorrected same-ToA cluster keeps the raw ToA");
        }
    }

    // Corrected pass: the earliest time-walk-corrected ToA moves the photon time
    // toward the true onset. For the same-ToA cluster, the lowest-ToT pixel gets
    // the largest positive delay, so its corrected time is the earliest.
    {
        auto result = run(hits, settings, &correction, true);
        test.expectEqual(result.counts.photon_count, std::uint64_t{3},
                         "correction does not change acceptance");

        if (result.photons.size() == 3) {
            const auto& walk = result.photons[1];
            // Expected leading edge: the minimum corrected ToA over the cluster.
            const double corrected_anchor = correctedToa(kToa4, 23, correction);
            const double corrected_low = correctedToa(kToa4, 8, correction);
            const double corrected_high = correctedToa(kToa4, 100, correction);
            double expected = corrected_anchor;
            if (corrected_low < expected) expected = corrected_low;
            if (corrected_high < expected) expected = corrected_high;

            test.expect(expected == corrected_low,
                        "the lowest-ToT pixel sets the corrected leading edge");
            test.expectEqual(walk.timestamp_canonical, expected,
                             "photon time is the earliest corrected ToA");
            test.expect(walk.timestamp_canonical < static_cast<double>(kToa4),
                        "correction moves the photon time earlier (toward onset)");
        }

        // photon_pixels were collected for every accepted photon.
        std::uint64_t accepted_pixels = 4 + 3 + 2;  // 2x2 + L + saturated pair
        test.expectEqual(result.photon_pixels.size(),
                         static_cast<std::size_t>(accepted_pixels),
                         "photon_pixels holds one row per accepted source pixel");
        // Every row references a photon id in range and carries its source row.
        bool ids_in_range = true;
        for (const auto& row : result.photon_pixels) {
            if (row.photon_id >= result.photons.size()) ids_in_range = false;
        }
        test.expect(ids_in_range, "photon_pixels ids reference real photons");
    }

    return test.finish();
}
