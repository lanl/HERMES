#include <cstddef>
#include <cstdint>
#include <vector>

#include "photon_reader.h"
#include "reconstruction.h"
#include "settings.h"
#include "test_helpers.h"

namespace {

using hermes_event_reconstructor::EventReconstruction;
using hermes_event_reconstructor::kDurationExceeded;
using hermes_event_reconstructor::kSinglePhoton;
using hermes_event_reconstructor::PhotonEvent;
using hermes_event_reconstructor::ReconParams;
using hermes_event_reconstructor::reconstructEvents;

// Small settings for the synthetic scenes: a 4-pixel radius, a 100-tick link
// window, and a 150-tick duration threshold so a spread-out event trips the
// duration flag. min_photon_count of 2 lets us exercise the below-threshold
// tally without dropping anything.
ReconParams testSettings() {
    ReconParams s;
    s.spatial_link_radius_pixels = 4.0;
    s.spatial_cells_per_axis = 5;  // derived width 52, >= radius
    s.max_time_difference_ticks = 100.0;
    s.max_event_duration_ticks = 150.0;
    s.min_photon_count = 2;
    return s;
}

}  // namespace

int main() {
    TestContext test;
    const ReconParams settings = testSettings();
    // The synthetic scenes sit well inside a single 256-pixel chip.
    const int sensor_width = 256;

    // A scene with three well-separated events, in time order:
    //   A: a compact two-photon event (photons 0,1) -> multi-photon, short
    //   B: a lone photon (photon 2)                 -> single_photon + below min
    //   C: a three-photon transitive chain (3,4,5) spread over 200 ticks
    //      -> multi-photon, duration 200 > 150 -> duration_exceeded
    const std::vector<PhotonEvent> photons = {
        PhotonEvent{0, 10.0, 10.0, 0.0},
        PhotonEvent{1, 12.0, 10.0, 20.0},
        PhotonEvent{2, 100.0, 100.0, 300.0},
        PhotonEvent{3, 40.0, 40.0, 500.0},
        PhotonEvent{4, 43.0, 40.0, 600.0},
        PhotonEvent{5, 46.0, 40.0, 700.0},  // chain: 0<->3<->6 px, dt 100 each
    };

    // Without collecting membership rows.
    {
        const EventReconstruction result =
            reconstructEvents(photons, settings, sensor_width, false);

        test.expectEqual(result.counts.photons_read, std::uint64_t{6},
                         "photons_read counts all input photons");
        test.expectEqual(result.counts.components_formed, std::uint64_t{3},
                         "three photon clusters formed");
        test.expectEqual(result.counts.event_count, std::uint64_t{3},
                         "three events built");
        test.expectEqual(result.counts.single_photon_count, std::uint64_t{1},
                         "one single-photon event");
        test.expectEqual(result.counts.duration_exceeded_count,
                         std::uint64_t{1}, "one duration-exceeded event");
        test.expectEqual(result.counts.min_photon_count_below,
                         std::uint64_t{1},
                         "one event below min_photon_count of 2");

        test.expectEqual(result.events.size(), std::size_t{3},
                         "three events returned");
        // event_id counts up in cluster-close (time) order.
        if (result.events.size() == 3) {
            test.expectEqual(result.events[0].event_id, std::uint64_t{0},
                             "first event id 0");
            test.expectEqual(result.events[1].event_id, std::uint64_t{1},
                             "second event id 1");
            test.expectEqual(result.events[2].event_id, std::uint64_t{2},
                             "third event id 2");

            // Event A: two photons, earliest time 0, not flagged.
            test.expectEqual(result.events[0].photon_count, std::uint64_t{2},
                             "event A has two photons");
            test.expectEqual(result.events[0].timestamp_canonical, 0.0,
                             "event A time is earliest member");
            test.expect(result.events[0].quality_flags == 0,
                        "event A has no flags");

            // Event B: single photon flag set.
            test.expectEqual(result.events[1].photon_count, std::uint64_t{1},
                             "event B is a single photon");
            test.expect(result.events[1].quality_flags & kSinglePhoton,
                        "event B flagged single_photon");

            // Event C: three photons, duration 200 -> duration_exceeded.
            test.expectEqual(result.events[2].photon_count, std::uint64_t{3},
                             "event C has three photons");
            test.expectEqual(result.events[2].duration_ticks, 200.0,
                             "event C duration is 200 ticks");
            test.expect(result.events[2].quality_flags & kDurationExceeded,
                        "event C flagged duration_exceeded");
        }

        // Membership rows are not collected when the flag is off.
        test.expect(result.event_photons.empty(),
                    "no event_photons rows when collection is off");
    }

    // With membership rows collected.
    {
        const EventReconstruction result =
            reconstructEvents(photons, settings, sensor_width, true);

        // One row per member photon: 2 + 1 + 3 = 6 rows.
        test.expectEqual(result.event_photons.size(), std::size_t{6},
                         "one membership row per member photon");

        // Every row carries the event_id of an event it belongs to, and copies
        // the source photon's coordinates.
        bool rows_consistent = true;
        for (const auto& row : result.event_photons) {
            if (row.event_id >= result.events.size()) {
                rows_consistent = false;
                break;
            }
            // photon_id must be a real source photon and the coordinates match.
            const PhotonEvent& source = photons[row.photon_id];
            if (row.x != source.x || row.y != source.y ||
                row.timestamp_canonical != source.timestamp_canonical) {
                rows_consistent = false;
                break;
            }
        }
        test.expect(rows_consistent,
                    "membership rows reference valid events and copy source "
                    "photon fields");

        // The lone photon (photon_id 2) appears exactly once, tied to the
        // single-photon event.
        int lone_rows = 0;
        for (const auto& row : result.event_photons) {
            if (row.photon_id == 2) {
                ++lone_rows;
            }
        }
        test.expectEqual(lone_rows, 1, "the lone photon has one membership row");
    }

    // Photons pooled from two chips into one whole-sensor stream get one
    // contiguous run of event_ids. Chip 0's light lands left of the dead cross
    // (x < 256) and chip 1's lands right of it (x > 259); on a 516-pixel quad
    // sensor they form three well-separated events whose ids count 0, 1, 2.
    {
        ReconParams quad_settings = testSettings();
        quad_settings.min_photon_count = 1;
        const std::vector<PhotonEvent> pooled = {
            PhotonEvent{0, 20.0, 20.0, 0.0},     // chip 0, event 0
            PhotonEvent{1, 22.0, 20.0, 20.0},    // chip 0, event 0
            PhotonEvent{2, 300.0, 300.0, 400.0},  // chip 1, event 1
            PhotonEvent{3, 302.0, 300.0, 420.0},  // chip 1, event 1
            PhotonEvent{4, 400.0, 100.0, 800.0},  // chip 1, event 2
        };
        const EventReconstruction result =
            reconstructEvents(pooled, quad_settings, 516, false);
        test.expectEqual(result.events.size(), std::size_t{3},
                         "pooled two-chip stream forms three events");
        if (result.events.size() == 3) {
            test.expectEqual(result.events[0].event_id, std::uint64_t{0},
                             "pooled event ids start at 0");
            test.expectEqual(result.events[1].event_id, std::uint64_t{1},
                             "pooled event ids are contiguous (1)");
            test.expectEqual(result.events[2].event_id, std::uint64_t{2},
                             "pooled event ids are contiguous (2)");
        }
    }

    // Empty input yields no events, no rows, and zero counts.
    {
        const EventReconstruction result =
            reconstructEvents({}, settings, sensor_width, true);
        test.expectEqual(result.counts.photons_read, std::uint64_t{0},
                         "empty input reads no photons");
        test.expectEqual(result.counts.event_count, std::uint64_t{0},
                         "empty input builds no events");
        test.expect(result.events.empty(), "empty input has no events");
        test.expect(result.event_photons.empty(),
                    "empty input has no membership rows");
    }

    return test.finish();
}
