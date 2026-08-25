#include <stdexcept>
#include <string>

#include "sensor_layout.h"
#include "test_helpers.h"

int main() {
    TestContext test;

    using hermes_event_reconstructor::sensorWidth;

    test.expectEqual(sensorWidth("single_chip"), 256,
                     "single_chip sensor is 256 wide");
    test.expectEqual(sensorWidth("quad"), 516, "quad sensor is 516 wide");

    bool threw = false;
    try {
        sensorWidth("triple");
    } catch (const std::runtime_error&) {
        threw = true;
    }
    test.expect(threw, "an unknown layout throws");

    return test.finish();
}
