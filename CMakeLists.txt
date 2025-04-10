cmake_minimum_required(VERSION 3.7)

if (EXISTS "${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake")
    include (${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)
else()
    message(FATAL_ERROR "Global cmake file missing")
endif()

set(CMAKE_INSTALL_LIBDIR "lib64")
include(GNUInstallDirs)

option(BUILD_SHARED_LIBS "shared libs" OFF)
option(BUILD_TESTING "Run unit tests" OFF)

set(SVK_NODE_FEATURE_VERSION_FULL ${GIT_REPO_VERSION_FULL})
set(SVK_NODE_FEATURE_VERSION ${GIT_REPO_VERSION})

project(SVK_NODE_FEATURE VERSION ${SVK_NODE_FEATURE_VERSION} DESCRIPTION "SVK Node Feature")

set(SVK_NODE_FEATURE_INCLUDE_DEST "include/")
set(SVK_NODE_FEATURE_LIB_DEST "lib64/")

set(PARENT_DIR ${CMAKE_CURRENT_SOURCE_DIR})

add_subdirectory(src)

if(BUILD_TESTING)
#    add_subdirectory(tests)
endif()
