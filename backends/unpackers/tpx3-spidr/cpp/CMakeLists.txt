cmake_minimum_required(VERSION 3.20)

project(hermes_tpx3_spidr LANGUAGES CXX)

add_library(hermes_tpx3_spidr_unpacker
    src/diagnostics.cpp
    src/unpacker.cpp
)

target_compile_features(hermes_tpx3_spidr_unpacker PUBLIC cxx_std_17)
target_include_directories(hermes_tpx3_spidr_unpacker
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

if(MSVC)
    target_compile_options(hermes_tpx3_spidr_unpacker PRIVATE /W4)
else()
    target_compile_options(
        hermes_tpx3_spidr_unpacker
        PRIVATE -Wall -Wextra -Wpedantic
    )
endif()

add_executable(hermes-tpx3-spidr
    src/tpx3SpidrUnpacker.cpp
)
target_link_libraries(hermes-tpx3-spidr PRIVATE hermes_tpx3_spidr_unpacker)
