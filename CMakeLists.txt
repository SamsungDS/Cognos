cmake_minimum_required(VERSION 3.7)

include(GNUInstallDirs)
include(FindPkgConfig)

if (EXISTS "${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake")
    include (${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)
else()
    message(FATAL_ERROR "Global cmake file missing")
endif()

option(BUILD_SHARED_LIBS "shared libs" OFF)
option(BUILD_TESTING "Run unit tests" OFF)

set(SVK_RAS_FEATURE_VERSION_FULL ${GIT_REPO_VERSION_FULL})
set(SVK_RAS_FEATURE_VERSION ${GIT_REPO_VERSION})

project(SVKRAS VERSION ${SVK_RAS_FEATURE_VERSION} DESCRIPTION "SVK RAS Feature")

pkg_check_modules(SVKFW REQUIRED svkframework)
add_compile_options(${SVKFW_CFLAGS})

set(PARENT_DIR ${CMAKE_CURRENT_SOURCE_DIR})

add_subdirectory(adapters)
add_subdirectory(src)
add_subdirectory(config)

if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
