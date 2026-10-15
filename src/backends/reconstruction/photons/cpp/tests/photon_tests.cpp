#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>

#include "cluster_filter.h"
#include "clustering.h"
#include "photon.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::ClusterEvaluation;
using hermes_photon_clusterer::PixelCluster;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::TimewalkCorrection;
using hermes_photon_clusterer::buildPhoton;

void expectTime(TestContext& test, double actual, double expected,
                const std::string& label) {
    // These small examples use at most a few divisions and additions. Allow
    // four relative machine epsilons for that rounding, not instrument error.
    const double tolerance = 4 * std::numeric_limits<double>::epsilon() *
                             std::max(1.0, std::fabs(expected));
    test.expect(std::isfinite(actual) && std::fabs(actual - expected) <= tolerance,
                label + ": actual=" + std::to_string(actual) +
                    ", expected=" + std::to_string(expected));
}

}  // namespace

int main() {
    TestContext test;

    // A 2x2 block centers between its pixels, sums ToT, and averages source
    // timestamps by default. Explicit leading-edge timing keeps its old result.
    {
        PixelCluster cluster;
        cluster.hits = {
            PixelHit{2, 4, 10, 205},
            PixelHit{3, 4, 20, 200},
            PixelHit{2, 5, 30, 210},
            PixelHit{3, 5, 40, 208},
        };
        ClusterEvaluation evaluation;
        evaluation.integrated_tot = 100;
        evaluation.quality_flags = 0;

        auto photon = buildPhoton(cluster, evaluation, nullptr);
        test.expect(photon.x == 2.5, "x is the arithmetic mean");
        test.expect(photon.y == 4.5, "y is the arithmetic mean");
        test.expectEqual(photon.tot, std::uint64_t{100},
                         "tot comes from the evaluation's summed tot_raw");
        test.expect(photon.timestamp_canonical == 205.75,
                    "default timestamp is the fractional arithmetic mean");
        test.expect(buildPhoton(cluster, evaluation, nullptr, "leading_edge")
                            .timestamp_canonical == 200.0,
                    "explicit leading edge keeps the earliest source-pixel time");
    }

    // Hand-calculated times for all estimators, with correction disabled and
    // with both supported global models. The repeated coordinate still counts
    // as a separate hit; the mean is neither coordinate- nor ToT-weighted.
    {
        PixelCluster cluster;
        cluster.hits = {
            PixelHit{0, 0, 10, 100},
            PixelHit{1, 0, 30, 106},
            PixelHit{1, 0, 20, 110},
        };
        ClusterEvaluation evaluation;
        evaluation.integrated_tot = 60;
        evaluation.quality_flags = 3;
        TimewalkCorrection linear;
        linear.model = TimewalkCorrection::Model::kLinear;
        linear.m = 1.0;
        linear.high_tot_anchor = 30;
        TimewalkCorrection inverse;
        inverse.model = TimewalkCorrection::Model::kInverse;
        inverse.a = 240;
        inverse.b = 10;
        inverse.high_tot_anchor = 30;

        const std::array<std::string, 3> estimators = {
            "average", "leading_edge", "brightest"};
        // Raw times: 100,106,110. Linear delays: -20,0,-10, giving
        // 120,106,120 (the earliest hit changes). Inverse delays: 6,0,2,
        // giving 94,106,108 (the brightest hit is not the leading edge).
        const std::array<const TimewalkCorrection*, 3> corrections = {
            nullptr, &linear, &inverse};
        const double expected[3][3] = {
            {316.0 / 3.0, 100, 106},
            {346.0 / 3.0, 106, 106},
            {308.0 / 3.0, 94, 106},
        };
        for (std::size_t model = 0; model < corrections.size(); ++model) {
            for (std::size_t estimator = 0; estimator < estimators.size(); ++estimator) {
                const auto photon = buildPhoton(
                    cluster, evaluation, corrections[model], estimators[estimator]);
                expectTime(test, photon.timestamp_canonical, expected[model][estimator],
                           estimators[estimator] + " correction " + std::to_string(model));
                test.expect(photon.x == 2.0 / 3.0 && photon.y == 0.0,
                            "timing leaves the position unchanged");
                test.expect(photon.tot == 60 && photon.quality_flags == 3,
                            "timing leaves summed ToT and flags unchanged");
            }
        }
    }

    // A single pixel maps straight through and carries its quality flags.
    {
        PixelCluster cluster;
        cluster.hits = {PixelHit{7, 9, 15, 500}};
        ClusterEvaluation evaluation;
        evaluation.integrated_tot = 15;
        evaluation.quality_flags = 0b11;

        auto photon = buildPhoton(cluster, evaluation, nullptr);
        test.expect(photon.x == 7.0, "single-pixel x");
        test.expect(photon.y == 9.0, "single-pixel y");
        test.expect(photon.timestamp_canonical == 500.0, "single-pixel time");
        test.expectEqual(photon.quality_flags, std::uint16_t{0b11},
                         "quality flags carried from the evaluation");
        TimewalkCorrection correction;
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = 0.5;
        correction.high_tot_anchor = 20;
        for (const auto& estimator : {"average", "leading_edge", "brightest"}) {
            test.expectEqual(
                buildPhoton(cluster, evaluation, nullptr, estimator).timestamp_canonical,
                500.0, "one uncorrected hit agrees for every estimator");
            test.expectEqual(
                buildPhoton(cluster, evaluation, &correction, estimator).timestamp_canonical,
                502.5, "one corrected hit retains its fractional time for every estimator");
        }
    }

    // Brightest is chosen by raw ToT, then earliest RAW time, regardless of
    // vector order. Equal ToT and equal time also give the same timestamp with
    // a shared curve, so the final source-order tie has no numerical difference.
    {
        PixelCluster cluster;
        cluster.hits = {
            PixelHit{0, 0, 30, 110}, PixelHit{1, 0, 10, 100},
            PixelHit{1, 1, 30, 106}, PixelHit{2, 1, 30, 106},
        };
        ClusterEvaluation evaluation;
        TimewalkCorrection correction;
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = 0.5;
        correction.high_tot_anchor = 40;
        for (int order = 0; order < 2; ++order) {
            test.expectEqual(
                buildPhoton(cluster, evaluation, nullptr, "brightest").timestamp_canonical,
                106.0, "brightest ToT ties use earliest raw time");
            test.expectEqual(
                buildPhoton(cluster, evaluation, &correction, "brightest").timestamp_canonical,
                111.0, "brightest selects by raw ToT and corrects the selected time");
            std::reverse(cluster.hits.begin(), cluster.hits.end());
        }
    }

    // Exact comparisons at large times are deliberate: a relative tolerance
    // there would accept the loss of several ticks or integer-sum overflow.
    {
        PixelCluster cluster;
        ClusterEvaluation evaluation;
        const std::uint64_t fractional_base = std::uint64_t{1} << 50;
        cluster.hits = {PixelHit{0, 0, 10, fractional_base + 1},
                        PixelHit{1, 0, 10, fractional_base + 2}};
        test.expectEqual(buildPhoton(cluster, evaluation, nullptr).timestamp_canonical,
                         static_cast<double>(fractional_base) + 1.5,
                         "large representable fractional average is retained");

        const std::uint64_t precision_base = std::uint64_t{1} << 53;
        cluster.hits = {PixelHit{0, 0, 10, precision_base + 1},
                        PixelHit{1, 0, 10, precision_base + 2}};
        test.expectEqual(buildPhoton(cluster, evaluation, nullptr).timestamp_canonical -
                             static_cast<double>(precision_base),
                         2.0,
                         "integer offsets are averaged before float64 rounding");
        TimewalkCorrection correction;
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = -0.25;
        correction.high_tot_anchor = 11;
        // Mean is base+1.25 after subtracting 0.25 from each hit. It rounds to
        // base+2; correcting already-rounded hit times would instead give base.
        test.expectEqual(buildPhoton(cluster, evaluation, &correction).timestamp_canonical -
                             static_cast<double>(precision_base),
                         2.0,
                         "correction is averaged before rounding large timestamps");

        cluster.hits = {PixelHit{0, 0, 10, precision_base},
                        PixelHit{1, 0, 10, precision_base + 2}};
        test.expectEqual(buildPhoton(cluster, evaluation, nullptr).timestamp_canonical -
                             static_cast<double>(precision_base),
                         0.0, "final float64 midpoint rounds to the even lower value");
        cluster.hits = {PixelHit{0, 0, 10, precision_base + 2},
                        PixelHit{1, 0, 10, precision_base + 4}};
        test.expectEqual(buildPhoton(cluster, evaluation, nullptr).timestamp_canonical -
                             static_cast<double>(precision_base),
                         4.0, "final float64 midpoint rounds to the even upper value");

        for (const int exponent : {54, 63}) {
            const std::uint64_t base = std::uint64_t{1} << exponent;
            const std::uint64_t spacing = std::uint64_t{1} << (exponent - 52);
            cluster.hits = {PixelHit{0, 0, 10, base + 1},
                            PixelHit{1, 0, 10, base + spacing}};
            // Mean is base+spacing/2+0.5, just above the rounding midpoint.
            test.expectEqual(buildPhoton(cluster, evaluation, nullptr).timestamp_canonical -
                                 static_cast<double>(base),
                             static_cast<double>(spacing),
                             "average keeps low bits as float64 spacing grows");
        }

        const auto largest = std::numeric_limits<std::uint64_t>::max();
        cluster.hits = {PixelHit{0, 0, 10, largest - 9},
                        PixelHit{1, 0, 10, largest - 7}};
        test.expectEqual(buildPhoton(cluster, evaluation, nullptr).timestamp_canonical,
                         std::ldexp(1.0, 64),
                         "averaging near uint64 maximum does not overflow");
    }

    // Correct the selected integer time before the final float64 rounding.
    // At 2^63, even a long-double intermediate can land on a false midpoint.
    {
        PixelCluster cluster;
        ClusterEvaluation evaluation;
        TimewalkCorrection correction;
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = 1.0;
        correction.high_tot_anchor = 30;
        const std::uint64_t base = std::uint64_t{1} << 53;
        cluster.hits = {PixelHit{0, 0, 31, base + 1}};
        for (const auto& estimator : {"average", "brightest", "leading_edge"}) {
            test.expectEqual(
                buildPhoton(cluster, evaluation, &correction, estimator).timestamp_canonical,
                static_cast<double>(base),
                "calibrated single-hit timing retains odd raw ticks");
        }
        const std::uint64_t large_base = std::uint64_t{1} << 63;
        correction.m = 0.5;
        cluster.hits = {PixelHit{0, 0, 31, large_base + 1025}};
        for (const auto& estimator : {"average", "brightest", "leading_edge"}) {
            test.expectEqual(
                buildPhoton(cluster, evaluation, &correction, estimator).timestamp_canonical -
                    static_cast<double>(large_base),
                2048.0, "calibrated time above a midpoint rounds upward only once");
        }
        cluster.hits = {PixelHit{0, 0, 31, large_base + 3072}};
        for (const auto& estimator : {"average", "brightest", "leading_edge"}) {
            test.expectEqual(
                buildPhoton(cluster, evaluation, &correction, estimator).timestamp_canonical -
                    static_cast<double>(large_base),
                2048.0, "calibrated time below a midpoint rounds downward only once");
        }
        correction.m = static_cast<double>(large_base);
        cluster.hits = {PixelHit{0, 0, 31, large_base + 1025}};
        for (const auto& estimator : {"average", "brightest", "leading_edge"}) {
            test.expectEqual(
                buildPhoton(cluster, evaluation, &correction, estimator).timestamp_canonical,
                1025.0, "large correction cancellation retains the selected integer time");
        }
    }

    // The native-range correction is finite at every ToT, but two saturated
    // hits overflow an unscaled float64 sum. Their mean remains finite.
    {
        PixelCluster cluster;
        cluster.hits = {PixelHit{0, 0, 1023, 100}, PixelHit{1, 0, 1023, 102}};
        ClusterEvaluation evaluation;
        TimewalkCorrection correction;
        correction.model = TimewalkCorrection::Model::kLinear;
        correction.m = 1e305;
        correction.high_tot_anchor = 0;
        expectTime(test, buildPhoton(cluster, evaluation, &correction).timestamp_canonical,
                   -1.023e308, "finite average survives correction-sum overflow");
    }

    return test.finish();
}
