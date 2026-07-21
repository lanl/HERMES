cmake_minimum_required(VERSION 3.20)

project(hermes_tpx3_spidr LANGUAGES CXX)

include(CTest)

if(MSVC)
    add_compile_options(/W4)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_library(hermes_tpx3_spidr_unpacker
    src/chunk_reader.cpp
    src/diagnostics.cpp
    src/unpacker.cpp
)

target_compile_features(hermes_tpx3_spidr_unpacker PUBLIC cxx_std_17)
target_include_directories(hermes_tpx3_spidr_unpacker
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

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
endif()
