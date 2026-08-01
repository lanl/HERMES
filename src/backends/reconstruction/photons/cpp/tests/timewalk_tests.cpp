#include <cmath>
#include <cstdint>
#include <fstream>
#include <string>

#include "clustering.h"
#include "test_helpers.h"
#include "timewalk.h"

namespace {

using hermes_photon_clusterer::PixelCluster;
using hermes_photon_clusterer::PixelHit;
using hermes_photon_clusterer::TimewalkCorrection;
using hermes_photon_clusterer::correctedToa;
using hermes_photon_clusterer::earliestCorrectedToa;
using hermes_photon_clusterer::loadTimewalkCorrection;

// Writes text to a temporary file and returns its path.
std::string writeTemp(const std::string& name, const std::string& contents) {
    const std::string path = std::string("timewalk_test_") + name;
    std::ofstream out(path);
    out << contents;
    out.close();
    return path;
}

bool nearlyEqual(double lhs, double rhs) { return std::fabs(lhs - rhs) < 1e-6; }

}  // namespace

int main() {
    TestContext test;

    // A valid inverse correction loads its parameters and anchor.
    {
        const std::string path = writeTemp("inverse.json", R"({
            "model": "inverse",
            "parameters": {"a": 1000.0, "b": 5.0},
            "high_tot_anchor": 20.0,
            "time_unit": "canonical_ticks"
        })");
        auto correction = loadTimewalkCorrection(path);
        test.expect(correction.model == TimewalkCorrection::Model::kInverse,
                    "inverse model parsed");
        test.expect(correction.a == 1000.0, "inverse a parsed");
        test.expect(correction.b == 5.0, "inverse b parsed");
        test.expect(correction.high_tot_anchor == 20.0, "anchor parsed");

        // A pixel at the anchor ToT has zero delay; its corrected time equals raw.
        test.expect(nearlyEqual(correctedToa(1000, 20, correction), 1000.0),
                    "anchor-ToT pixel is uncorrected");

        // A low-ToT pixel is shifted earlier by a positive delay.
        const double low = correctedToa(1000, 5, correction);
        const double expected =
            1000.0 - 1000.0 * (1.0 / (5.0 + 5.0) - 1.0 / (20.0 + 5.0));
        test.expect(nearlyEqual(low, expected), "low-ToT pixel shifted earlier");
        test.expect(low < 1000.0, "low-ToT correction moves time earlier");
    }

    // A valid linear correction loads its slope.
    {
        const std::string path = writeTemp("linear.json", R"({
            "model": "linear",
            "parameters": {"m": 2.0},
            "high_tot_anchor": 20.0,
            "time_unit": "canonical_ticks"
        })");
        auto correction = loadTimewalkCorrection(path);
        test.expect(correction.model == TimewalkCorrection::Model::kLinear,
                    "linear model parsed");
        test.expect(nearlyEqual(correctedToa(1000, 10, correction),
                                1000.0 - 2.0 * (10.0 - 20.0)),
                    "linear correction applied");
    }

    // Time-walk correction reorders pixels: a low-ToT pixel read later in raw
    // time becomes the earliest corrected ToA and sets the photon leading edge.
    {
        const std::string path = writeTemp("reorder.json", R"({
            "model": "inverse",
            "parameters": {"a": 100000.0, "b": 10.0},
            "high_tot_anchor": 20.0,
            "time_unit": "canonical_ticks"
        })");
        auto correction = loadTimewalkCorrection(path);
        PixelCluster cluster;
        cluster.hits = {
            PixelHit{0, 0, 20, 1000},  // high ToT, raw-earliest
            PixelHit{1, 0, 5, 1200},   // low ToT, raw-later
        };
        const double earliest = earliestCorrectedToa(cluster, correction);
        const double corrected_low = correctedToa(1200, 5, correction);
        const double corrected_high = correctedToa(1000, 20, correction);
        test.expect(corrected_low < corrected_high,
                    "low-ToT later pixel corrects earlier than high-ToT pixel");
        test.expect(nearlyEqual(earliest, corrected_low),
                    "earliest corrected ToA comes from the low-ToT pixel");
    }

    // Malformed and invalid files are rejected.
    {
        bool threw = false;
        try {
            loadTimewalkCorrection(writeTemp("bad_unit.json", R"({
                "model": "inverse",
                "parameters": {"a": 1.0, "b": 1.0},
                "high_tot_anchor": 20.0,
                "time_unit": "nanoseconds"
            })"));
        } catch (const std::runtime_error&) {
            threw = true;
        }
        test.expect(threw, "wrong time_unit rejected");
    }
    {
        bool threw = false;
        try {
            loadTimewalkCorrection(writeTemp("bad_model.json", R"({
                "model": "quadratic",
                "parameters": {"a": 1.0},
                "high_tot_anchor": 20.0,
                "time_unit": "canonical_ticks"
            })"));
        } catch (const std::runtime_error&) {
            threw = true;
        }
        test.expect(threw, "unknown model rejected");
    }
    {
        bool threw = false;
        try {
            loadTimewalkCorrection(writeTemp("missing_param.json", R"({
                "model": "inverse",
                "parameters": {"a": 1.0},
                "high_tot_anchor": 20.0,
                "time_unit": "canonical_ticks"
            })"));
        } catch (const std::runtime_error&) {
            threw = true;
        }
        test.expect(threw, "missing inverse parameter rejected");
    }
    {
        bool threw = false;
        try {
            loadTimewalkCorrection(writeTemp("garbage.json", "not json"));
        } catch (const std::runtime_error&) {
            threw = true;
        }
        test.expect(threw, "malformed JSON rejected");
    }

    return test.finish();
}
