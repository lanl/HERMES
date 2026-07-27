cmake_minimum_required(VERSION 3.20)

project(hermes_photon_clusterer LANGUAGES CXX)

include(CTest)

# Arrow/Parquet read the pixel_data inputs and write photon output; JSON writes
# the reconstruction summary. They are discovered the same way as the unpacker.
find_package(Arrow QUIET)
find_package(Parquet QUIET)
find_package(nlohmann_json REQUIRED)
if(Arrow_FOUND)
    message(STATUS "Found Arrow: ${Arrow_VERSION}")
endif()

if(Parquet_FOUND)
    message(STATUS "Found Parquet: ${Parquet_VERSION}")
endif()

if(nlohmann_json_FOUND)
    message(STATUS "Found nlohmann_json: ${nlohmann_json_VERSION}")
endif()

if(MSVC)
    add_compile_options(/W4)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(hermes_photon_clusterer
    src/clusterer.cpp
)

target_compile_features(hermes_photon_clusterer PUBLIC cxx_std_17)
target_include_directories(hermes_photon_clusterer
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

if(Arrow_FOUND AND Parquet_FOUND)
    target_link_libraries(hermes_photon_clusterer
        PUBLIC
            Arrow::arrow_shared
            Parquet::parquet_shared
    )
    target_compile_definitions(hermes_photon_clusterer
        PUBLIC
            HERMES_HAS_ARROW_PARQUET
    )
endif()

if(nlohmann_json_FOUND)
    target_link_libraries(hermes_photon_clusterer
        PUBLIC
            nlohmann_json::nlohmann_json
    )
    target_compile_definitions(hermes_photon_clusterer
        PUBLIC
            HERMES_HAS_JSON
    )
endif()

add_executable(hermes-photon-clusterer
    src/photonClusterer.cpp
)
target_link_libraries(hermes-photon-clusterer PRIVATE hermes_photon_clusterer)

if(BUILD_TESTING)
    add_executable(clusterer_tests tests/clusterer_tests.cpp)
    target_link_libraries(clusterer_tests PRIVATE hermes_photon_clusterer)
    add_test(NAME clusterer_tests COMMAND clusterer_tests)
endif()
