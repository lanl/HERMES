#ifndef HERMES_EVENT_RECONSTRUCTOR_SETTINGS_H
#define HERMES_EVENT_RECONSTRUCTOR_SETTINGS_H

#include <cstdint>
#include <string>

namespace hermes_event_reconstructor {

// Complete event-reconstruction settings with built-in defaults. Every field has
// a value, so the binary runs with no settings file; an optional JSON file
// overrides only the fields it names. Field names and meanings mirror the
// Settings table in docs/architecture/event_reconstruction.md.
//
// spatial_link_radius_pixels is a physics parameter. spatial_cells_per_axis is
// an implementation parameter that sets how finely the field of view is divided
// for the neighbor-lookup grid; the cell width in pixels is derived from it (see
// deriveCellWidth). Both are chosen by the user because event size depends on the
// optical setup, from sub-centimeter microscope fields to ~10 cm single-lens
// fields.
struct ReconParams {
    // Physics linking radius in pixels: two photons are neighbors when their
    // squared separation is at most spatial_link_radius_pixels^2. The default of
    // 10 was chosen from a 9 mm microscope-FoV TaAtScraper run by inspecting
    // cluster-colored movies of single beam pulses: 10 px keeps one neutron's
    // scintillation light linked as a single event without merging neighboring
    // neutrons. Setups with different optics will need a different value.
    double spatial_link_radius_pixels = 10.0;

    // Number of spatial grid cells along each detector axis, giving an
    // n x n grid over the 256 x 256 field of view. Larger values make finer
    // cells (fewer photons per cell, more distance tests); smaller values make
    // coarser cells. This only accelerates neighbor lookup and never changes
    // which events form, provided the derived cell width stays at least the
    // linking radius (enforced by validateReconParams).
    std::uint32_t spatial_cells_per_axis = 5;

    // Maximum time difference between two linked photons, in canonical ticks.
    // The default of 4915200 ticks is 10000 ns / 10 us (1 tick = 25 ns / 12288).
    // Chosen from the same TaAtScraper run: at shorter windows a single neutron
    // event visibly fragmented into several separately colored clusters in the
    // pulse movies, and 10 us was the smallest window that kept each event linked
    // as one cluster while still separating distinct neutrons.
    double max_time_difference_ticks = 4915200.0;

    // Duration above which an event is flagged duration_exceeded, in canonical
    // ticks. The default of 14745600 ticks is 30000 ns / 30 us. Chosen from the
    // same TaAtScraper run: multi-photon event durations there run to ~56 us with
    // a median near 6 us, so a 30 us threshold flags only the long tail (~1 %) of
    // events that are unusually long-lived and may be two neutrons chained
    // together, without flagging typical events. The flag never discards.
    double max_event_duration_ticks = 14745600.0;

    // Optional analysis threshold recorded for downstream use. It is NOT applied
    // during clustering; the reconstruction stage never discards events.
    std::uint32_t min_photon_count = 1;
};

// Loads settings starting from the defaults and overriding any field present in
// the JSON file at path. Unknown keys, wrong value types, or out-of-range values
// throw std::runtime_error. An empty path is not accepted here; the caller
// decides whether to load a file at all.
ReconParams loadReconParams(const std::string& path);

// Validates a settings struct, throwing std::runtime_error on any violation.
// Applied by loadReconParams and reusable for the built-in defaults.
void validateReconParams(const ReconParams& settings);

// Derives the spatial-grid cell width in pixels from the number of cells per
// axis over the fixed 256-pixel field of view:
//
//   cell_width = ceil(256 / spatial_cells_per_axis)
//
// Rounding up guarantees exactly spatial_cells_per_axis cells span the chip
// (the last cell may be narrower). validateReconParams requires this width to
// be at least the linking radius so the fixed 3x3 neighborhood search stays
// exact; cell width is a lookup accelerator only and never changes which events
// form.
int deriveCellWidth(std::uint32_t spatial_cells_per_axis);

}  // namespace hermes_event_reconstructor

#endif
