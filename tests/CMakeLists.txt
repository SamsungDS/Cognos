include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)

link_directories( "${CMAKE_SOURCE_DIR}/build/src" "${CMAKE_MGMT_FW_LIBRARY_DIR}")

file(GLOB TEST_SOURCES *.cc)

# Create executable for tests
add_executable(svkme_ut ${TEST_SOURCES})

include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

target_include_directories(svkme_ut PUBLIC ${CMAKE_CURRENT_SOURCE_DIR} "${CMAKE_SOURCE_DIR}/src/include" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
target_link_directories(svkme_ut PRIVATE  ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})

target_link_libraries(svkme_ut PRIVATE svkme gtest gtest_main gmock gmock_main jansson numa yaml-cpp)

include(GoogleTest)
gtest_discover_tests(svkme_ut)
