# Set the minimum required version of CMake for this project.
cmake_minimum_required(VERSION 3.7)

find_package(Git)

if(GIT_EXECUTABLE)
  # Generate a git-describe version string from Git repository tags
  execute_process(
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts
    COMMAND ./get_version.sh
    OUTPUT_VARIABLE GIT_DESCRIBE_VERSION
    RESULT_VARIABLE GIT_DESCRIBE_ERROR_CODE
    OUTPUT_STRIP_TRAILING_WHITESPACE
    )
  if(NOT GIT_DESCRIBE_ERROR_CODE)
    message(STATUS "GIT VERSION ${GIT_DESCRIBE_VERSION}")
    # git tag can be in the form of v1.0.2 or v1.9.2-1-abcd. Get only the <major>.<minor>.<rev>.
    string(REGEX MATCH "([0-9]+)\\.([0-9]+)\\.([0-9]+)" GIT_DESCRIBE_VERSION_STRIP ${GIT_DESCRIBE_VERSION})

    set(GIT_REPO_VERSION_FULL ${GIT_DESCRIBE_VERSION})
    set(GIT_REPO_VERSION ${GIT_DESCRIBE_VERSION_STRIP})
  else()
    message(FATAL_ERROR "git failed in getting the tag for the repo")
  endif()
else()
  message(FATAL_ERROR "git command not found")
endif()

# Set the C++ standard to use to build this target.
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED on)

# various options
option(WITH_RELEASE "release build" OFF)
option(WITH_COVERAGE "Enable code coverage" OFF)
if (WITH_RELEASE)
        SET(CMAKE_CXX_FLAGS "-O2 -Wall -Werror")
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

