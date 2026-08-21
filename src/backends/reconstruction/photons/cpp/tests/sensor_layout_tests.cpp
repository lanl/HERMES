#include <string>

#include "sensor_layout.h"
#include "test_helpers.h"

namespace {

using hermes_photon_clusterer::sensorTransform;
using hermes_photon_clusterer::SensorPoint;

bool transformThrows(const std::string& layout, int chip_index) {
    try {
        sensorTransform(layout, chip_index, 10.0, 20.0);
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

}  // namespace

int main() {
    TestContext test;

    // single_chip leaves the chip-local coordinates unchanged for any chip.
    {
        const SensorPoint p = sensorTransform("single_chip", 0, 10.0, 20.0);
        test.expectEqual(p.x, 10.0, "single_chip keeps x");
        test.expectEqual(p.y, 20.0, "single_chip keeps y");
    }

    // quad tiles the four chips 2x2 with a four-pixel dead gap (offset 260).
    {
        const SensorPoint c0 = sensorTransform("quad", 0, 10.0, 20.0);
        test.expectEqual(c0.x, 270.0, "quad chip 0 shifts x by 260");
        test.expectEqual(c0.y, 20.0, "quad chip 0 keeps y");

        const SensorPoint c1 = sensorTransform("quad", 1, 10.0, 20.0);
        test.expectEqual(c1.x, 505.0, "quad chip 1 flips x to 515 - x");
        test.expectEqual(c1.y, 495.0, "quad chip 1 flips y to 515 - y");

        const SensorPoint c2 = sensorTransform("quad", 2, 10.0, 20.0);
        test.expectEqual(c2.x, 245.0, "quad chip 2 flips x to 255 - x");
        test.expectEqual(c2.y, 495.0, "quad chip 2 flips y to 515 - y");

        const SensorPoint c3 = sensorTransform("quad", 3, 10.0, 20.0);
        test.expectEqual(c3.x, 10.0, "quad chip 3 keeps x");
        test.expectEqual(c3.y, 20.0, "quad chip 3 keeps y");
    }

    // The quad map stays within the assembled 516x516 sensor (0..515) for the
    // extreme chip-local corners.
    {
        const SensorPoint c0_max = sensorTransform("quad", 0, 255.0, 255.0);
        test.expectEqual(c0_max.x, 515.0, "quad chip 0 max x is 515");
        const SensorPoint c1_min = sensorTransform("quad", 1, 255.0, 255.0);
        test.expectEqual(c1_min.x, 260.0, "quad chip 1 min x is 260");
        test.expectEqual(c1_min.y, 260.0, "quad chip 1 min y is 260");
    }

    // A quad chip index outside 0-3 is an error, as is an unknown layout.
    test.expect(transformThrows("quad", 4), "quad rejects chip index 4");
    test.expect(transformThrows("quad", -1), "quad rejects negative chip index");
    test.expect(transformThrows("triple", 0), "unknown layout rejected");

    return test.finish();
}
