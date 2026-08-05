cmake_minimum_required(VERSION 3.20)

project(hermes_event_recon_common LANGUAGES CXX)

include(CTest)

# Algorithm-neutral event-reconstruction pieces shared by every clustering
# program: reading photon_events, building a candidate event from a cluster of
# member photons, writing the event Parquet files, and writing the summary JSON.
# None of these know any clustering algorithm's settings; each program passes its
# own settings in as a JSON string. Arrow/Parquet handle the Parquet I/O and
# nlohmann_json the summary, discovered the same way as the clustering programs.
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

add_library(hermes_event_recon_common
    src/event.cpp
    src/event_writer.cpp
    src/photon_reader.cpp
    src/summary_writer.cpp
)

target_compile_features(hermes_event_recon_common PUBLIC cxx_std_17)
target_include_directories(hermes_event_recon_common
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

if(Arrow_FOUND AND Parquet_FOUND)
    target_link_libraries(hermes_event_recon_common
        PUBLIC
            Arrow::arrow_shared
            Parquet::parquet_shared
    )
    target_compile_definitions(hermes_event_recon_common
        PUBLIC
            HERMES_HAS_ARROW_PARQUET
    )
endif()

if(nlohmann_json_FOUND)
    target_link_libraries(hermes_event_recon_common
        PUBLIC
            nlohmann_json::nlohmann_json
    )
    target_compile_definitions(hermes_event_recon_common
        PUBLIC
            HERMES_HAS_JSON
    )
endif()

if(BUILD_TESTING)
    add_executable(event_tests tests/event_tests.cpp)
    target_link_libraries(event_tests PRIVATE hermes_event_recon_common)
    add_test(NAME event_tests COMMAND event_tests)

    add_executable(summary_writer_tests tests/summary_writer_tests.cpp)
    target_link_libraries(summary_writer_tests PRIVATE hermes_event_recon_common)
    add_test(NAME summary_writer_tests COMMAND summary_writer_tests)

    if(Arrow_FOUND AND Parquet_FOUND)
        add_executable(photon_reader_tests tests/photon_reader_tests.cpp)
        target_link_libraries(photon_reader_tests PRIVATE hermes_event_recon_common)
        add_test(NAME photon_reader_tests COMMAND photon_reader_tests)

        add_executable(event_writer_tests tests/event_writer_tests.cpp)
        target_link_libraries(event_writer_tests PRIVATE hermes_event_recon_common)
        add_test(NAME event_writer_tests COMMAND event_writer_tests)
    endif()
endif()
