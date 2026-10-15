#include <algorithm>
#include <cstddef>
#include <cmath>
#include <limits>
#include <string>
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

    // A fixed inverse curve, constructed directly so the regression is self-contained.
    TimewalkCorrection correction;
    correction.model = TimewalkCorrection::Model::kInverse;
    correction.a = 1254855.5798924663;
    correction.b = 10.69863711765447;
    correction.high_tot_anchor = 23.0;

    // Built-in defaults: min_pixel_tot_raw=1, cluster size 2..64, aspect<=3,
    // filled>=0.5, 8-connected, generous time gate.
    ClusteringSettings settings;
    settings.photon_time_estimator = "leading_edge";

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
            // Independently evaluated with 60-digit decimal arithmetic from
            // the parameters above, q=8, raw time=3000000. Allow two relative
            // machine epsilons for the double reciprocal calculations.
            constexpr double expected = 2970128.109070225;
            test.expect(std::fabs(walk.timestamp_canonical - expected) <=
                            2 * std::numeric_limits<double>::epsilon() * expected,
                        "explicit leading edge retains its calibrated numerical result");
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

    // Changing timing never changes membership or filtering. This stream
    // includes low-ToT noise, bridged components, a repeated coordinate,
    // saturation, a rejected singleton, and a separate accepted photon.
    {
        const std::vector<PixelHit> source = {
            PixelHit{50, 50, 0, 99, 0},
            PixelHit{0, 0, 10, 100, 1},
            PixelHit{2, 0, 30, 104, 2},
            PixelHit{1, 0, 1023, 106, 3},
            PixelHit{1, 0, 20, 110, 4},
            PixelHit{30, 30, 10, 150, 5},
            PixelHit{10, 10, 10, 200, 6},
            PixelHit{11, 10, 20, 202, 7},
        };
        ClusteringSettings timing_settings;
        timing_settings.max_time_spread_ticks = 20;
        TimewalkCorrection linear;
        linear.model = TimewalkCorrection::Model::kLinear;
        linear.m = 1;
        linear.high_tot_anchor = 30;
        const std::string estimators[] = {"average", "leading_edge", "brightest"};
        // For the first photon, corrected hit times are 120,104,-887,120.
        // For the second they are 220,212. All expected values are exact doubles.
        const double expected_first[2][3] = {{105, 100, 106}, {-135.75, -887, -887}};
        const double expected_second[2][3] = {{201, 200, 202}, {216, 212, 212}};
        for (int calibrated = 0; calibrated < 2; ++calibrated) {
            for (int estimator = 0; estimator < 3; ++estimator) {
                timing_settings.photon_time_estimator = estimators[estimator];
                auto result = run(source, timing_settings,
                                  calibrated ? &linear : nullptr, true);
                test.expect(result.counts.pixel_rows_read == 8 &&
                                result.counts.pixel_rows_below_min_tot == 1 &&
                                result.counts.components_formed == 3 &&
                                result.counts.rejected_component_count == 1 &&
                                result.counts.rejection_counts.below_min_cluster_size == 1,
                            "timing leaves input and rejection counts unchanged");
                test.expect(result.counts.saturated_pixel_count == 1 &&
                                result.counts.bridged_components_count == 1,
                            "timing leaves quality counts unchanged");
                test.expectEqual(result.photons.size(), std::size_t{2},
                                 "timing leaves the accepted photon count unchanged");
                if (result.photons.size() != 2) continue;
                test.expectEqual(result.photons[0].timestamp_canonical,
                                 expected_first[calibrated][estimator],
                                 "first photon has its hand-calculated time");
                test.expectEqual(result.photons[1].timestamp_canonical,
                                 expected_second[calibrated][estimator],
                                 "second photon has its hand-calculated time");
                test.expect(result.photons[0].x == 1 && result.photons[0].y == 0 &&
                                result.photons[0].tot == 1083 &&
                                result.photons[0].quality_flags == 3,
                            "bridged saturated photon keeps position, ToT, and both flags");
                test.expect(result.photons[1].x == 10.5 && result.photons[1].y == 10 &&
                                result.photons[1].tot == 30 &&
                                result.photons[1].quality_flags == 0,
                            "separate photon keeps position, ToT, and flags");
                test.expectEqual(result.photon_pixels.size(), std::size_t{6},
                                 "one row remains for every accepted source hit");
                std::vector<std::uint64_t> source_ids;
                for (const auto& row : result.photon_pixels) {
                    source_ids.push_back(row.pixel_event_id);
                    if (row.pixel_event_id >= source.size()) {
                        test.expect(false, "source hit id is in range");
                        continue;
                    }
                    const auto& input = source[row.pixel_event_id];
                    test.expect(row.x == input.x && row.y == input.y &&
                                    row.tot_raw == input.tot_raw &&
                                    row.timestamp_canonical == input.timestamp_canonical,
                                "accepted source coordinates, ToT, and integer times stay raw");
                    test.expectEqual(row.photon_id,
                                     std::uint64_t{row.pixel_event_id <= 4 ? 0U : 1U},
                                     "accepted source hit keeps the same photon membership");
                }
                std::sort(source_ids.begin(), source_ids.end());
                test.expect(source_ids == std::vector<std::uint64_t>({1, 2, 3, 4, 6, 7}),
                            "timing preserves the exact accepted source hit ids");
            }
        }
    }

    return test.finish();
}
