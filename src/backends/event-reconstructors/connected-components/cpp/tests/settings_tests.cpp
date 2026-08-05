#include <fstream>
#include <string>

#include "settings.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::deriveCellWidth;
using hermes_event_reconstructor::ReconParams;
using hermes_event_reconstructor::loadReconParams;
using hermes_event_reconstructor::validateReconParams;

std::string writeTemp(const std::string& name, const std::string& contents) {
    const std::string path = std::string("settings_test_") + name;
    std::ofstream out(path);
    out << contents;
    out.close();
    return path;
}

bool loadThrows(const std::string& name, const std::string& contents) {
    try {
        loadReconParams(writeTemp(name, contents));
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

bool validates(const ReconParams& settings) {
    try {
        validateReconParams(settings);
    } catch (const std::runtime_error&) {
        return false;
    }
    return true;
}

}  // namespace

int main() {
    TestContext test;

    // Built-in defaults are self-consistent.
    {
        ReconParams defaults;
        test.expect(validates(defaults), "built-in defaults validate");
        test.expectEqual(defaults.spatial_link_radius_pixels, 4.0,
                         "default link radius is 4");
        test.expectEqual(defaults.spatial_cells_per_axis, 5u,
                         "default is 5 cells per axis");
        test.expectEqual(defaults.min_photon_count, 1u,
                         "default min_photon_count is 1");
    }

    // A partial file overrides only the named fields; the rest keep defaults.
    {
        const ReconParams s = loadReconParams(writeTemp(
            "partial.json",
            "{\"spatial_link_radius_pixels\": 8.0}"));
        test.expectEqual(s.spatial_link_radius_pixels, 8.0,
                         "override applied to link radius");
        test.expectEqual(s.min_photon_count, 1u,
                         "unnamed field keeps its default");
    }

    // Each field can be overridden.
    {
        const ReconParams s = loadReconParams(writeTemp(
            "full.json",
            "{\"spatial_link_radius_pixels\": 6.0,"
            " \"spatial_cells_per_axis\": 8,"
            " \"max_time_difference_ticks\": 1000.0,"
            " \"max_event_duration_ticks\": 5000.0,"
            " \"min_photon_count\": 3}"));
        test.expectEqual(s.spatial_link_radius_pixels, 6.0, "link radius set");
        test.expectEqual(s.spatial_cells_per_axis, 8u, "cells per axis set");
        test.expectEqual(s.max_time_difference_ticks, 1000.0, "dt set");
        test.expectEqual(s.max_event_duration_ticks, 5000.0, "duration set");
        test.expectEqual(s.min_photon_count, 3u, "min_photon_count set");
    }

    // Rejection: unknown key.
    test.expect(loadThrows("unknown.json", "{\"not_a_field\": 1}"),
                "unknown key is rejected");

    // Rejection: wrong type for a numeric field.
    test.expect(
        loadThrows("bad_type.json",
                   "{\"spatial_link_radius_pixels\": \"four\"}"),
        "non-numeric link radius is rejected");

    // Rejection: min_photon_count must be a non-negative integer.
    test.expect(
        loadThrows("bad_count.json", "{\"min_photon_count\": -1}"),
        "negative min_photon_count is rejected");
    test.expect(
        loadThrows("frac_count.json", "{\"min_photon_count\": 1.5}"),
        "fractional min_photon_count is rejected");

    // Rejection: out-of-range values.
    test.expect(loadThrows("zero_radius.json",
                           "{\"spatial_link_radius_pixels\": 0.0}"),
                "zero link radius is rejected");
    test.expect(loadThrows("neg_dt.json",
                           "{\"max_time_difference_ticks\": -1.0}"),
                "negative dt is rejected");
    test.expect(loadThrows("zero_duration.json",
                           "{\"max_event_duration_ticks\": 0.0}"),
                "zero duration is rejected");
    test.expect(loadThrows("zero_count.json", "{\"min_photon_count\": 0}"),
                "zero min_photon_count is rejected");

    // Rejection: not a JSON object.
    test.expect(loadThrows("array.json", "[1, 2, 3]"),
                "top-level array is rejected");
    test.expect(loadThrows("garbage.json", "{not json"),
                "malformed JSON is rejected");

    // Cell width is the number of pixels per cell for n cells over 256 pixels,
    // rounded up so exactly n cells span the field of view.
    test.expectEqual(deriveCellWidth(1), 256, "1 cell spans the whole chip");
    test.expectEqual(deriveCellWidth(2), 128, "2 cells -> width 128");
    test.expectEqual(deriveCellWidth(4), 64, "4 cells -> width 64");
    test.expectEqual(deriveCellWidth(5), 52, "5 cells -> width 52 (rounded up)");
    test.expectEqual(deriveCellWidth(3), 86, "3 cells -> width 86 (rounded up)");
    test.expectEqual(deriveCellWidth(256), 1, "256 cells -> one pixel each");

    // The correctness guard: a grid too fine for the linking radius, so the
    // derived cell width would fall below the radius, is rejected.
    {
        ReconParams s;
        s.spatial_link_radius_pixels = 4.0;
        s.spatial_cells_per_axis = 100;  // 256/100 -> width 3 < 4
        test.expect(!validates(s), "too-fine grid for the radius is rejected");
    }
    // A grid whose cell width exactly meets the radius is accepted.
    {
        ReconParams s;
        s.spatial_link_radius_pixels = 52.0;
        s.spatial_cells_per_axis = 5;  // width 52 == radius
        test.expect(validates(s), "cell width equal to radius is accepted");
    }
    // Range checks on the cell count itself.
    test.expect(loadThrows("zero_cells.json", "{\"spatial_cells_per_axis\": 0}"),
                "zero cells per axis is rejected");
    test.expect(
        loadThrows("too_many_cells.json",
                   "{\"spatial_cells_per_axis\": 300}"),
        "more cells than pixels is rejected");

    return test.finish();
}
