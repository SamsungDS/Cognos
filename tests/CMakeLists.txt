set(CMAKE_VERBOSE_MAKEFILE OFF)

set(CMMH_STATIC_LIB "${PROJECT_SOURCE_DIR}/third_party/libcmmh.a")
if(NOT EXISTS ${CMMH_STATIC_LIB})
 message(FATAL_ERROR "libcmmh.a not found at ${CMMH_STATIC_LIB}")
endif()

include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)

link_directories("${FMAPI_INCLUDE_PATH}/build" "${CMAKE_SOURCE_DIR}/build/src" "${CMAKE_MGMT_FW_LIBRARY_DIR}")
file(GLOB TEST_SOURCES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} *.cc)
list(REMOVE_ITEM TEST_SOURCES test_plugin.cc)
list(REMOVE_ITEM TEST_SOURCES bw_monitor_ut.cc)

file(GLOB_RECURSE ADAPTER_SOURCES "${CMAKE_SOURCE_DIR}/src/*/sc_*.cc")
list(REMOVE_ITEM ADAPTER_SOURCES "${CMAKE_SOURCE_DIR}/src/sc_utility.cc")

file(GLOB MOCK_ADAPTER_SRC "${CMAKE_SOURCE_DIR}/src/mock/mock_cmmh.cc")
file(GLOB MOCK_CMMH_CALLS "${CMAKE_CURRENT_SOURCE_DIR}/test_mocks.cc")

# Build dummy plugin to test dlopen/dlsym
add_library(dummy_plugin SHARED test_plugin.cc)
target_include_directories(dummy_plugin PRIVATE ${CMAKE_SOURCE_DIR}/src/include ${CMAKE_CURRENT_SOURCE_DIR} "${PROJECT_SOURCE_DIR}/third_party" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
set_target_properties(dummy_plugin PROPERTIES OUTPUT_NAME dummy_plugin)
add_custom_command(TARGET dummy_plugin POST_BUILD
COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:dummy_plugin> ${CMAKE_CURRENT_BINARY_DIR}
)

# Main test executable
add_executable(cxl_ut ${TEST_SOURCES} ${ADAPTER_SOURCES})
target_sources(cxl_ut PRIVATE ${MOCK_ADAPTER_SRC} ${MOCK_CMMH_CALLS})
target_compile_definitions(cxl_ut PRIVATE MOCK=1 TEST_BUILD=1)
target_link_options(cxl_ut PRIVATE "-Wl,--allow-multiple-definition")

target_include_directories(cxl_ut PUBLIC ${CMAKE_CURRENT_SOURCE_DIR} "${PROJECT_SOURCE_DIR}/third_party" "${CMAKE_SOURCE_DIR}/src/include" "${CMAKE_SOURCE_DIR}/src/cmmh/include" "${CMAKE_SOURCE_DIR}/src/tm/include" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS} ${FMAPI_INCLUDE_PATH})
target_link_directories(cxl_ut PRIVATE "${FMAPI_INCLUDE_PATH}/build" "${PROJECT_SOURCE_DIR}/third_party" ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(cxl_ut PRIVATE svkcxl gtest gtest_main gmock gmock_main svcmgr jansson zmq numa mbox_a1_shared yaml-cpp pci ${CMMH_STATIC_LIB})
target_compile_definitions(cxl_ut PRIVATE TEST_PLUGIN_DIR="${CMAKE_CURRENT_BINARY_DIR}")

include(GoogleTest)
gtest_discover_tests(cxl_ut)
