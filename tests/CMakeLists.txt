include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)

link_directories("${FMAPI_INCLUDE_PATH}/build" "${CMAKE_SOURCE_DIR}/build/src" "${CMAKE_MGMT_FW_LIBRARY_DIR}")
file(GLOB TEST_SOURCES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} *.cc)
list(REMOVE_ITEM TEST_SOURCES test_plugin.cc)

file(GLOB_RECURSE ADAPTER_SOURCES "${CMAKE_SOURCE_DIR}/src/*/sc_*.cc")
list(REMOVE_ITEM ADAPTER_SOURCES "${CMAKE_SOURCE_DIR}/src/sc_utility.cc")

# Build dummy plugin to test dlopen/dlsym
add_library(dummy_plugin SHARED test_plugin.cc)
target_include_directories(dummy_plugin PRIVATE ${CMAKE_SOURCE_DIR}/src/include ${CMAKE_CURRENT_SOURCE_DIR} ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
set_target_properties(dummy_plugin PROPERTIES OUTPUT_NAME dummy_plugin)
add_custom_command(TARGET dummy_plugin POST_BUILD
COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:dummy_plugin> ${CMAKE_CURRENT_BINARY_DIR}
)

# Main test executable
add_executable(cxl_ut ${TEST_SOURCES} ${ADAPTER_SOURCES})
target_link_options(cxl_ut PRIVATE "-Wl,--allow-multiple-definition")
include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

target_include_directories(cxl_ut PUBLIC ${CMAKE_CURRENT_SOURCE_DIR} "${CMAKE_SOURCE_DIR}/src/include" "${CMAKE_SOURCE_DIR}/src/cmmh/include" "${CMAKE_SOURCE_DIR}/src/tm/include" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS} ${FMAPI_INCLUDE_PATH})
target_link_directories(cxl_ut PRIVATE "${FMAPI_INCLUDE_PATH}/build" ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
target_link_libraries(cxl_ut PRIVATE svkcxl gtest gtest_main gmock gmock_main svcmgr jansson zmq numa mbox_a1_shared yaml-cpp pci)
target_compile_definitions(cxl_ut PRIVATE TEST_PLUGIN_DIR="${CMAKE_CURRENT_BINARY_DIR}")

include(GoogleTest)
gtest_discover_tests(cxl_ut)
