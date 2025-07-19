cmake_minimum_required(VERSION 3.7)

if(BUILD_TESTING)
include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

add_subdirectory(unit)
add_subdirectory(unit/adapter)
endif()

add_subdirectory(tools/ras_err_inject)
add_subdirectory(tools/mock_adapter_demo)
