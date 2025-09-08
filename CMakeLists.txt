cmake_minimum_required(VERSION 3.7)
include(FindPkgConfig)

if(EXISTS "${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake")
  include(${CMAKE_SOURCE_DIR}/cmake/svk_global.cmake)
else()
  message(FATAL_ERROR "Global cmake file missing")
endif()

option(BUILD_SHARED_LIBS "shared libs" OFF)
option(BUILD_TESTING "Run unit tests" OFF)

set(SVK_GRPC_FW_VERSION_FULL ${GIT_REPO_VERSION_FULL})
set(SVK_GRPC_FW_VERSION ${GIT_REPO_VERSION})

project(
  SVKGRPCFW
  VERSION ${SVK_GRPC_FW_VERSION}
  DESCRIPTION "SVK gRPC Framework")

set(SVKGRPCFW_INCLUDE_DEST "include/")
set(SVKGRPCFW_LIB_DEST "lib64/")

set(PARENT_DIR ${CMAKE_CURRENT_SOURCE_DIR})
pkg_check_modules(SVKFW REQUIRED svkframework)

include(FetchContent)
FetchContent_Declare(
  json
  URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz)
FetchContent_MakeAvailable(json)

add_subdirectory(proto)
add_subdirectory(grpc_node_server)
add_subdirectory(grpc_controller)
add_subdirectory(rest_api)
add_subdirectory(svc_mgr)
add_subdirectory(config)

if(BUILD_TESTING)
  add_subdirectory(tests)
endif()
