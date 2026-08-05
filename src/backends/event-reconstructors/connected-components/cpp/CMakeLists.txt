cmake_minimum_required(VERSION 3.20)

project(hermes_event_reconstructor LANGUAGES CXX)

include(CTest)

# Arrow/Parquet read the photon_events inputs and write event_candidates output;
# JSON writes the reconstruction summary. They are discovered the same way as the
# photon clusterer.
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

add_library(hermes_event_reconstructor
    src/clustering.cpp
    src/photon_reader.cpp
    src/settings.cpp
    src/version.cpp
)

target_compile_features(hermes_event_reconstructor PUBLIC cxx_std_17)
target_include_directories(hermes_event_reconstructor
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

if(Arrow_FOUND AND Parquet_FOUND)
    target_link_libraries(hermes_event_reconstructor
        PUBLIC
            Arrow::arrow_shared
            Parquet::parquet_shared
    )
    target_compile_definitions(hermes_event_reconstructor
        PUBLIC
            HERMES_HAS_ARROW_PARQUET
    )
endif()

if(nlohmann_json_FOUND)
    target_link_libraries(hermes_event_reconstructor
        PUBLIC
            nlohmann_json::nlohmann_json
    )
    target_compile_definitions(hermes_event_reconstructor
        PUBLIC
            HERMES_HAS_JSON
    )
endif()

add_executable(hermes-event-reconstructor
    src/eventReconstructor.cpp
)
target_link_libraries(hermes-event-reconstructor PRIVATE hermes_event_reconstructor)

if(BUILD_TESTING)
    add_executable(settings_tests tests/settings_tests.cpp)
    target_link_libraries(settings_tests PRIVATE hermes_event_reconstructor)
    add_test(NAME settings_tests COMMAND settings_tests)

    add_executable(clustering_tests tests/clustering_tests.cpp)
    target_link_libraries(clustering_tests PRIVATE hermes_event_reconstructor)
    add_test(NAME clustering_tests COMMAND clustering_tests)

    if(Arrow_FOUND AND Parquet_FOUND)
        add_executable(photon_reader_tests tests/photon_reader_tests.cpp)
        target_link_libraries(photon_reader_tests PRIVATE hermes_event_reconstructor)
        add_test(NAME photon_reader_tests COMMAND photon_reader_tests)
    endif()
endif()
