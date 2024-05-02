cmake_minimum_required(VERSION 3.10)
project(cxl)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Include custom cmake modules
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake")

# Add global settings and dependencies
include(svk_global)
include(gtest)


# Set coverage flags for GCC/Clang
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    if(WITH_COVERAGE)
        message(STATUS "Building with coverage")
        set(COVERAGE_FLAGS "--coverage -fprofile-arcs -ftest-coverage")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${COVERAGE_FLAGS}")
        set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${COVERAGE_FLAGS}")
    endif()
endif()

# Add subdirectories
add_subdirectory(src)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()

