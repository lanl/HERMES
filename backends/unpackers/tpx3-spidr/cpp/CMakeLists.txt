cmake_minimum_required(VERSION 3.20)

project(hermes_tpx3_spidr LANGUAGES CXX)

include(CTest)

# Arrow and JSON dependencies are optional for now
# They will be used in Stages 11-12 for Parquet and JSON output
find_package(Arrow QUIET)
find_package(Parquet QUIET)
find_package(nlohmann_json QUIET)

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

add_library(hermes_tpx3_spidr_unpacker
    src/chunk_reader.cpp
    src/diagnostics.cpp
    src/parquet_schemas.cpp
    src/parquet_writer.cpp
    src/time_sort.cpp
    src/timestamp_calculator.cpp
    src/unpacker.cpp
)

target_compile_features(hermes_tpx3_spidr_unpacker PUBLIC cxx_std_17)
target_include_directories(hermes_tpx3_spidr_unpacker
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

if(Arrow_FOUND AND Parquet_FOUND)
    target_link_libraries(hermes_tpx3_spidr_unpacker
        PUBLIC
            Arrow::arrow_shared
            Parquet::parquet_shared
    )
    target_compile_definitions(hermes_tpx3_spidr_unpacker
        PUBLIC
            HERMES_HAS_ARROW_PARQUET
    )
endif()

add_executable(hermes-tpx3-spidr
    src/tpx3SpidrUnpacker.cpp
)
target_link_libraries(hermes-tpx3-spidr PRIVATE hermes_tpx3_spidr_unpacker)

if(BUILD_TESTING)
    add_executable(packet_tests tests/packet_tests.cpp)
    target_link_libraries(packet_tests PRIVATE hermes_tpx3_spidr_unpacker)
    add_test(NAME packet_tests COMMAND packet_tests)

    add_executable(stream_tests tests/stream_tests.cpp)
    target_link_libraries(stream_tests PRIVATE hermes_tpx3_spidr_unpacker)
    add_test(NAME stream_tests COMMAND stream_tests)

    add_executable(diagnostics_tests tests/diagnostics_tests.cpp)
    target_link_libraries(diagnostics_tests PRIVATE hermes_tpx3_spidr_unpacker)
    add_test(NAME diagnostics_tests COMMAND diagnostics_tests)

    add_executable(timestamp_tests tests/timestamp_tests.cpp)
    target_link_libraries(timestamp_tests PRIVATE hermes_tpx3_spidr_unpacker)
    add_test(NAME timestamp_tests COMMAND timestamp_tests)

    add_executable(time_sort_tests tests/time_sort_tests.cpp)
    target_link_libraries(time_sort_tests PRIVATE hermes_tpx3_spidr_unpacker)
    add_test(NAME time_sort_tests COMMAND time_sort_tests)
endif()
