include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)
link_directories("${CMAKE_SOURCE_DIR}/build/src" "${CMAKE_MGMT_FW_LIBRARY_DIR}")

file(GLOB TEST_SOURCES *.cc)

# Create executable for tests
add_executable(cme_ut ${TEST_SOURCES})

include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

target_include_directories(cme_ut PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include/" ${SVKFRAMEWORK_INCLUDE_DIRS} ${SVKMGMTFW_INCLUDE_DIRS})
target_link_directories(cme_ut PRIVATE ${SVKMGMTFW_LIB_DIRS} ${SVKFRAMEWORK_LIBRARY_DIRS})

# Link with the library created in src

#FAM-1520: added yaml-cpp
target_link_libraries(cme_ut PRIVATE gtest gtest_main gmock gmock_main jansson numa yaml-cpp)

include(GoogleTest)
gtest_discover_tests(cme_ut)
