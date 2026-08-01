#include <fstream>
#include <string>

#include "settings.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::ClusteringSettings;
using hermes_photon_clusterer::loadClusteringSettings;
using hermes_photon_clusterer::validateClusteringSettings;

std::string writeTemp(const std::string& name, const std::string& contents) {
    const std::string path = std::string("settings_test_") + name;
    std::ofstream out(path);
    out << contents;
    out.close();
    return path;
}

bool loadThrows(const std::string& name, const std::string& contents) {
    try {
        loadClusteringSettings(writeTemp(name, contents));
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

}  // namespace

int main() {
    TestContext test;

    // Built-in defaults are self-consistent.
    {
        ClusteringSettings defaults;
        bool ok = true;
        try {
            validateClusteringSettings(defaults);
        } catch (const std::runtime_error&) {
            ok = false;
        }
        test.expect(ok, "built-in defaults validate");
        test.expectEqual(defaults.adjacency, 8, "default adjacency is 8");
        test.expect(defaults.timewalk_calibration_file.empty(),
                    "default has no calibration file");
    }

    // A partial file overrides only the named fields; the rest keep defaults.
    {
        auto settings = loadClusteringSettings(writeTemp("partial.json", R"({
            "adjacency": 4,
            "min_pixel_tot_raw": 5,
            "timewalk_calibration_file": "calibrations/tpx3/time-walk_example.json"
        })"));
        test.expectEqual(settings.adjacency, 4, "adjacency overridden");
        test.expectEqual(settings.min_pixel_tot_raw, std::uint16_t{5},
                         "min_pixel_tot_raw overridden");
        test.expect(settings.timewalk_calibration_file ==
                        "calibrations/tpx3/time-walk_example.json",
                    "calibration file overridden");
        // Untouched fields keep defaults.
        test.expectEqual(settings.max_cluster_size, std::uint32_t{64},
                         "unset field keeps default");
        test.expect(!settings.save_photon_pixels,
                    "unset boolean keeps default");
    }

    // An empty object keeps every default.
    {
        auto settings = loadClusteringSettings(writeTemp("empty.json", "{}"));
        test.expectEqual(settings.max_time_spread_ticks,
                         std::uint64_t{491520}, "empty object keeps defaults");
    }

    // Rejections.
    test.expect(loadThrows("unknown.json", R"({"bogus": 1})"),
                "unknown field rejected");
    test.expect(loadThrows("bad_adjacency.json", R"({"adjacency": 6})"),
                "adjacency other than 4 or 8 rejected");
    test.expect(loadThrows("reserved_estimator.json",
                           R"({"photon_time_estimator": "brightest"})"),
                "reserved time estimator rejected");
    test.expect(loadThrows("reserved_position.json",
                           R"({"position_averaging": "tot_weighted"})"),
                "reserved position rule rejected");
    test.expect(loadThrows("bad_order.json",
                           R"({"min_cluster_size": 10, "max_cluster_size": 5})"),
                "min greater than max cluster size rejected");
    test.expect(loadThrows("bad_tot.json", R"({"min_pixel_tot_raw": 2000})"),
                "min_pixel_tot_raw above 1023 rejected");
    test.expect(loadThrows("bad_filled.json",
                           R"({"min_filled_fraction": 1.5})"),
                "filled fraction above 1 rejected");
    test.expect(loadThrows("bad_aspect.json", R"({"max_aspect_ratio": 0.5})"),
                "aspect ratio below 1 rejected");
    test.expect(loadThrows("negative.json", R"({"min_cluster_size": -1})"),
                "negative integer rejected");
    test.expect(loadThrows("garbage.json", "not json"),
                "malformed JSON rejected");

    return test.finish();
}
