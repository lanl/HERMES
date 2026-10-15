#ifndef HERMES_PHOTON_CLUSTERER_TIMESTAMP_H
#define HERMES_PHOTON_CLUSTERER_TIMESTAMP_H

#include <array>
#include <cmath>
#include <cstdint>
#include <limits>

namespace hermes_photon_clusterer {

// Keep the integer low bits until adding a fractional offset. The anchor is
// exactly representable in float64, including on platforms where long double
// has no extra precision.
inline double timestampWithOffset(std::uint64_t raw, long double offset) {
    constexpr int low_bits = std::numeric_limits<std::uint64_t>::digits -
                             std::numeric_limits<double>::digits;
    constexpr std::uint64_t low_mask = (std::uint64_t{1} << low_bits) - 1;
    const std::uint64_t integer_anchor = raw & ~low_mask;
    // Keep each addition's rounding residual with TwoSum. Up to five terms
    // suffice: anchor, offset, integer low bits, and two terms for comparing
    // with a float64 midpoint. The nonzero parts are ordered by magnitude, so
    // the last part also gives the sign of their exact sum.
    std::array<long double, 5> parts{};
    std::size_t count = 0;
    const auto add = [&](long double term) {
        std::size_t next_count = 0;
        for (std::size_t i = 0; i < count; ++i) {
            const long double sum = term + parts[i];
            const long double recovered = sum - term;
            const long double residual =
                (term - (sum - recovered)) + (parts[i] - recovered);
            if (residual != 0.0L) parts[next_count++] = residual;
            term = sum;
        }
        if (term != 0.0L || next_count == 0) parts[next_count++] = term;
        count = next_count;
    };
    add(static_cast<long double>(integer_anchor));
    add(offset);
    add(static_cast<long double>(raw - integer_anchor));
    const double rounded = static_cast<double>(parts[count - 1]);
    if (!std::isfinite(rounded)) return rounded;

    add(-static_cast<long double>(rounded));
    const long double difference = parts[count - 1];
    if (difference == 0.0L) return rounded;
    const double direction = difference > 0.0L
        ? std::numeric_limits<double>::infinity()
        : -std::numeric_limits<double>::infinity();
    const double neighbor = std::nextafter(rounded, direction);
    if (!std::isfinite(neighbor)) return rounded;
    const long double gap = static_cast<long double>(neighbor) - rounded;
    // Subtract the midpoint in two parts: forming it first can lose the very
    // residual that distinguishes 2^63 + 1024.5 from the midpoint at +1024.
    add(-gap / 2.0L);
    const long double beyond_midpoint = parts[count - 1];
    if (beyond_midpoint == 0.0L) {
        return std::fmod(static_cast<long double>(rounded) / gap, 2.0L) == 0.0L
            ? rounded : neighbor;
    }
    return (beyond_midpoint > 0.0L) == (difference > 0.0L) ? neighbor : rounded;
}

}  // namespace hermes_photon_clusterer

#endif
