#include <cmath>
#include <cstddef>
#include <vector>

#include "event.h"
#include "photon_reader.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::buildEvent;
using hermes_event_reconstructor::kDurationExceeded;
using hermes_event_reconstructor::kSinglePhoton;
using hermes_event_reconstructor::PhotonEvent;

bool near(const double a, const double b) { return std::fabs(a - b) < 1e-9; }

}  // namespace

int main() {
    TestContext test;

    const double max_duration = 1000.0;

    // A multi-photon event: centroid is the arithmetic mean, time is the
    // earliest member, count and bounding box are exact, no flags set.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 20.0, 100.0},
            PhotonEvent{1, 14.0, 20.0, 50.0},   // earliest in time
            PhotonEvent{2, 12.0, 26.0, 200.0},  // latest in time
        };
        const std::vector<std::size_t> members = {0, 1, 2};
        const auto e = buildEvent(photons, members, 7, max_duration);
        test.expectEqual(e.event_id, std::uint64_t{7}, "event_id assigned as given");
        test.expectEqual(e.photon_count, std::uint64_t{3}, "photon_count is member count");
        test.expect(near(e.x, 12.0), "centroid x is arithmetic mean");
        test.expect(near(e.y, 22.0), "centroid y is arithmetic mean");
        test.expect(near(e.timestamp_canonical, 50.0), "time is earliest member");
        test.expect(near(e.latest_time_canonical, 200.0), "latest member time recorded");
        test.expect(near(e.duration_ticks, 150.0), "duration is latest - earliest");
        test.expect(near(e.min_x, 10.0), "bounding box min_x");
        test.expect(near(e.max_x, 14.0), "bounding box max_x");
        test.expect(near(e.min_y, 20.0), "bounding box min_y");
        test.expect(near(e.max_y, 26.0), "bounding box max_y");
        test.expectEqual(e.quality_flags, std::uint16_t{0}, "no flags on a normal event");
    }

    // Spatial RMS: two photons symmetric about the centroid, each 3 px away.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 7.0, 10.0, 0.0},
            PhotonEvent{1, 13.0, 10.0, 10.0},
        };
        const auto e = buildEvent(photons, {0, 1}, 0, max_duration);
        test.expect(near(e.x, 10.0), "centroid between the pair");
        // Each is 3 px from the centroid, so RMS = sqrt((9 + 9) / 2) = 3.
        test.expect(near(e.spatial_rms, 3.0), "spatial RMS about the centroid");
    }

    // A single photon: flagged single_photon, zero duration, zero RMS.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 100.0, 100.0, 500.0},
        };
        const auto e = buildEvent(photons, {0}, 0, max_duration);
        test.expectEqual(e.photon_count, std::uint64_t{1}, "single member");
        test.expect((e.quality_flags & kSinglePhoton) != 0, "single_photon flag set");
        test.expect((e.quality_flags & kDurationExceeded) == 0,
                    "no duration flag on a single photon");
        test.expect(near(e.duration_ticks, 0.0), "single photon has zero duration");
        test.expect(near(e.spatial_rms, 0.0), "single photon has zero RMS");
        test.expect(near(e.x, 100.0), "single photon centroid is its position");
    }

    // Duration just over the threshold sets duration_exceeded.
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 11.0, 10.0, 1000.5},  // duration 1000.5 > 1000
        };
        const auto e = buildEvent(photons, {0, 1}, 0, max_duration);
        test.expect((e.quality_flags & kDurationExceeded) != 0,
                    "duration over threshold is flagged");
        test.expect((e.quality_flags & kSinglePhoton) == 0,
                    "multi-photon event is not single_photon");
    }

    // Duration exactly at the threshold is NOT flagged (flag is strictly greater).
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 10.0, 0.0},
            PhotonEvent{1, 11.0, 10.0, 1000.0},  // duration exactly 1000
        };
        const auto e = buildEvent(photons, {0, 1}, 0, max_duration);
        test.expect((e.quality_flags & kDurationExceeded) == 0,
                    "duration equal to threshold is not flagged");
    }

    // Member order does not matter: the same members in a different order build
    // an identical event (centroid, time, and box are order-independent).
    {
        const std::vector<PhotonEvent> photons = {
            PhotonEvent{0, 10.0, 20.0, 100.0},
            PhotonEvent{1, 14.0, 20.0, 50.0},
            PhotonEvent{2, 12.0, 26.0, 200.0},
        };
        const auto a = buildEvent(photons, {0, 1, 2}, 0, max_duration);
        const auto b = buildEvent(photons, {2, 0, 1}, 0, max_duration);
        test.expect(near(a.x, b.x) && near(a.y, b.y),
                    "centroid independent of member order");
        test.expect(near(a.timestamp_canonical, b.timestamp_canonical),
                    "event time independent of member order");
        test.expect(near(a.duration_ticks, b.duration_ticks),
                    "duration independent of member order");
    }

    return test.finish();
}
