include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)
link_directories("${FMAPI_INCLUDE_PATH}/build" "${CMAKE_SOURCE_DIR}/build/src" "${CMAKE_MGMT_FW_LIBRARY_DIR}")

file(GLOB TEST_SOURCES *.cc) 

# Create executable for tests
add_executable(cxl_ut ${TEST_SOURCES})

include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

target_include_directories(cxl_ut PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include/" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS} ${FMAPI_INCLUDE_PATH})
target_link_directories(cxl_ut PRIVATE "${FMAPI_INCLUDE_PATH}/build" ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})
# target_link_libraries(cxl mbox_a1_shared svcmgr jansson zmq numa)

# Link with the library created in src

target_link_libraries(cxl_ut PRIVATE cxl gtest gtest_main gmock gmock_main svcmgr jansson zmq numa mbox_a1_shared)

include(GoogleTest)
gtest_discover_tests(cxl_ut)

