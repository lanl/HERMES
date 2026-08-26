cmake_minimum_required(VERSION 3.20)

# Top-level build for the three HERMES C++ backends. scikit-build-core uses this
# file to compile them at install time and place the executables on PATH. Each
# backend keeps its own CMakeLists.txt under src/backends/; this file only
# gathers them and installs the programs.
project(hermes_backends LANGUAGES CXX)

add_subdirectory(src/backends/unpackers/tpx3-spidr/cpp)
add_subdirectory(src/backends/reconstruction/photons/cpp)
add_subdirectory(src/backends/reconstruction/events/connected-components/cpp)

# The programs install to the environment's bin/ and link against the Arrow and
# Parquet C++ libraries that conda places in the sibling lib/. Point each program
# at ../lib relative to its own location so it finds those libraries at run time
# without an absolute path baked in. bin/ and lib/ are always siblings under a
# conda/pixi environment prefix.
if(APPLE)
    set(hermes_install_rpath "@loader_path/../lib")
else()
    set(hermes_install_rpath "$ORIGIN/../lib")
endif()
set_target_properties(
    hermes-tpx3-spidr
    hermes-photon-clusterer
    hermes-event-reconstructor
    PROPERTIES INSTALL_RPATH "${hermes_install_rpath}"
)

# Install the three programs into the environment so configs can name them
# directly (e.g. executable_path: hermes-tpx3-spidr) and HERMES finds them on PATH.
install(
    TARGETS
        hermes-tpx3-spidr
        hermes-photon-clusterer
        hermes-event-reconstructor
    RUNTIME DESTINATION ${SKBUILD_SCRIPTS_DIR}
)

# Ship the bundled calibration data into the environment's share/ so an installed
# HERMES (not just a git checkout) has defaults to fall back on. share/ is a
# sibling of bin/ and lib/ under a conda/pixi environment prefix.
install(
    DIRECTORY calibrations/
    DESTINATION ${SKBUILD_DATA_DIR}/share/hermes/calibrations
)
