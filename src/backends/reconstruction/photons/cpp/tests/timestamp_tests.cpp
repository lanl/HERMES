#include <cmath>
#include <cstdint>
#include <limits>

#include "test_helpers.h"
#include "timestamp.h"

int main() {
    TestContext test;
    using hermes_photon_clusterer::timestampWithOffset;
    // These values have hand-calculated nearest float64 results. Exact checks
    // distinguish adjacent float64 values at each timestamp magnitude.
    for (const int exponent : {53, 54, 63}) {
        const std::uint64_t base = std::uint64_t{1} << exponent;
        const std::uint64_t spacing = std::uint64_t{1} << (exponent - 52);
        const double rounded_base = static_cast<double>(base);
        const long double half = static_cast<long double>(spacing) / 2;
        test.expectEqual(timestampWithOffset(base + 1, half - 0.5L) - rounded_base,
                         static_cast<double>(spacing), "above midpoint rounds up");
        test.expectEqual(timestampWithOffset(base, half - 0.5L) - rounded_base,
                         0.0, "below midpoint rounds down");
        test.expectEqual(timestampWithOffset(base, half) - rounded_base,
                         0.0, "exact midpoint rounds to even lower value");
        test.expectEqual(timestampWithOffset(base + spacing, half) - rounded_base,
                         2.0 * spacing, "exact midpoint rounds to even upper value");
        test.expectEqual(timestampWithOffset(base + spacing / 2 + 1, -0.5L) - rounded_base,
                         static_cast<double>(spacing), "fractional correction above midpoint");
        test.expectEqual(timestampWithOffset(base + 3 * spacing / 2, -0.5L) - rounded_base,
                         static_cast<double>(spacing), "fractional correction below midpoint");
    }
    test.expectEqual(timestampWithOffset((std::uint64_t{1} << 53) + 1, -1.0L),
                     std::ldexp(1.0, 53), "integer correction retains odd raw tick");
    test.expectEqual(timestampWithOffset(1, -1.5L), -0.5, "negative corrected time");
    const std::uint64_t base = std::uint64_t{1} << 63;
    test.expectEqual(timestampWithOffset(base + 1025, -static_cast<long double>(base)),
                     1025.0, "large correction cancellation retains integer low bits");
    test.expectEqual(timestampWithOffset(base + 1, static_cast<long double>(base) + 2048),
                     std::ldexp(1.0, 64) + 4096,
                     "large negative correction retains low bits across a midpoint");
    test.expectEqual(timestampWithOffset(std::numeric_limits<std::uint64_t>::max(), 0),
                     std::ldexp(1.0, 64), "uint64 maximum rounds without integer overflow");
    return test.finish();
}
