cmake_minimum_required(VERSION 3.7)

include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

add_subdirectory(unit)
add_subdirectory(unit/adapter)

add_subdirectory(tools/ras_err_inject)
