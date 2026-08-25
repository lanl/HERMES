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
    // n x n grid over the sensor width (256 for a single chip, 516 for a quad).
    // Larger values make finer cells (fewer photons per cell, more distance
    // tests); smaller values make coarser cells. This only accelerates neighbor
    // lookup and never changes which events form, provided the derived cell
    // width stays at least the linking radius (enforced by validateGridForSensor
    // once the sensor width is known from the photon files).
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

    // When true, also write an event_photons Parquet file mapping each member
    // photon to its event (event_id, photon_id, x, y, timestamp_canonical). It is
    // a diagnostic for inspecting how photons were grouped into events; it is off
    // by default because it is larger than event_candidates and not needed for
    // routine analysis. Mirrors the photon stage's save_photon_pixels.
    bool save_event_photons = false;
};

// Loads settings starting from the defaults and overriding any field present in
// the JSON file at path. Unknown keys, wrong value types, or out-of-range values
// throw std::runtime_error. An empty path is not accepted here; the caller
// decides whether to load a file at all.
ReconParams loadReconParams(const std::string& path);

// Validates the layout-independent settings, throwing std::runtime_error on any
// violation (radius > 0, cells >= 1, times > 0, min_photon_count >= 1). Applied
// by loadReconParams at load time, before the sensor width is known.
void validateReconParams(const ReconParams& settings);

// Validates the two grid checks that depend on the sensor width: the number of
// cells per axis must not exceed the sensor width, and the derived cell width
// must be at least the linking radius so the fixed 3x3 neighborhood search stays
// exact. Called once the layout (and therefore the sensor width) is read from
// the photon files. Throws std::runtime_error on a violation.
void validateGridForSensor(const ReconParams& settings, int sensor_width);

// Derives the spatial-grid cell width in pixels from the number of cells per
// axis over the sensor width:
//
//   cell_width = ceil(sensor_width / spatial_cells_per_axis)
//
// Rounding up guarantees exactly spatial_cells_per_axis cells span the sensor
// (the last cell may be narrower). validateGridForSensor requires this width to
// be at least the linking radius so the fixed 3x3 neighborhood search stays
// exact; cell width is a lookup accelerator only and never changes which events
// form.
int deriveCellWidth(std::uint32_t spatial_cells_per_axis, int sensor_width);

// Serializes the settings to a JSON object string for provenance: the same
// fields shown in the Settings table, plus the derived cell width for
// diagnostics. The algorithm-neutral summary writer renders this string verbatim
// under clustering.settings, and the event-file metadata carries it as
// event_settings_json, so this one function is the single source of the
// connected-components settings shape. Other algorithms provide their own.
std::string clusteringSettingsJson(const ReconParams& settings,
                                   int derived_cell_width);

}  // namespace hermes_event_reconstructor

#endif
