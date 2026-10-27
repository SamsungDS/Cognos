# Set the minimum required version of CMake for this project.
cmake_minimum_required(VERSION 3.7)

set(GET_VERSION_SCRIPT ${CMAKE_SOURCE_DIR}/scripts/get_version.sh)

# Get full version from get_version.sh
execute_process(
  COMMAND ${GET_VERSION_SCRIPT}
  OUTPUT_VARIABLE GIT_DESCRIBE_VERSION
  RESULT_VARIABLE GIT_DESCRIBE_ERROR_CODE
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

if(NOT GIT_DESCRIBE_ERROR_CODE EQUAL 0)
  message(FATAL_ERROR "Failed to retreieve version string from ${GET_VERSION_SCRIPT}")
else()
  message(STATUS "GIT VERSION ${GIT_DESCRIBE_VERSION}")
endif()

# Get short version from get_version.sh
execute_process(
  COMMAND ${GET_VERSION_SCRIPT} --short
  OUTPUT_VARIABLE GIT_DESCRIBE_VERSION_STRIP
  RESULT_VARIABLE GIT_DESCRIBE_VERSION_STRIP_ERROR_CODE
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

if(NOT GIT_DESCRIBE_ERROR_CODE EQUAL 0)
  message(FATAL_ERROR "Failed to retreieve short version string from ${GET_VERSION_SCRIPT}")
else()
  message(STATUS "SHORT GIT VERSION ${GIT_DESCRIBE_VERSION_STRIP}")
endif()

set(GIT_REPO_VERSION_FULL ${GIT_DESCRIBE_VERSION})
set(GIT_REPO_VERSION ${GIT_DESCRIBE_VERSION_STRIP})

# Set the C++ standard to use to build this target.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED on)

# various options
option(WITH_RELEASE "release build" OFF)
option(WITH_COVERAGE "Enable code coverage" OFF)
if (WITH_RELEASE)
        SET(CMAKE_CXX_FLAGS "-O3 -Wall -Werror")
else ()
        SET(CMAKE_CXX_FLAGS "-O0 -g3 -Wall -Werror")
endif()

if(WITH_COVERAGE)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} --coverage")
endif(WITH_COVERAGE)

option(WITH_VERBOSE "verbose" OFF)
if(WITH_VERBOSE)
    set(CMAKE_VERBOSE_MAKEFILE ON)
else()
    set(CMAKE_VERBOSE_MAKEFILE OFF)
endif()

if (WITH_VERBOSE)
  message(STATUS "Git repo full version ${GIT_REPO_VERSION_FULL}")
  message(STATUS "Git repo version for CMake ${GIT_REPO_VERSION}")
endif()
