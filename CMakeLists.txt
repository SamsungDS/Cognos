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

find_package(OpenMP REQUIRED)
if(OPENMP_FOUND)
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} ${OpenMP_C_FLAGS}")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${OpenMP_CXX_FLAGS}")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${OpenMP_EXE_LINKER_FLAGS}")
endif()

add_subdirectory(src)
add_subdirectory(adapters)
add_subdirectory(config)

if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
