cmake_minimum_required(VERSION 3.7)
include(GNUInstallDirs)
include(FindPkgConfig)

if (EXISTS "${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake")
    include (${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)
else()
    message(FATAL_ERROR "Global cmake file missing")
endif()

option(BUILD_TESTING "Run unit tests" OFF)

set(SVK_SLAT_FEATURE_VERSION_FULL ${GIT_REPO_VERSION_FULL})
set(SVK_SLAT_FEATURE_VERSION ${GIT_REPO_VERSION})

project(SVKSLATracker VERSION ${SVK_SLAT_FEATURE_VERSION} DESCRIPTION "SVK SLAT Feature")

pkg_check_modules(SVKFW REQUIRED svkframework)

add_compile_options(${SVKFW_CFLAGS})
add_subdirectory(src)

if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
