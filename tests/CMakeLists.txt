include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)
link_directories("${CMAKE_INCLUDE_PATH}/build" "${CMAKE_SOURCE_DIR}/build/src")

file(GLOB TEST_SOURCES *.cc) 

# Create executable for tests
add_executable(cxl_ut ${TEST_SOURCES})

include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)

# Include directories (adjust as needed)
target_include_directories(cxl_ut PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    /usr/include
    /usr/local/include 
)

# Link with the library created in src
target_link_libraries(cxl_ut PRIVATE cxl_lib gtest gtest_main gmock gmock_main)

include(GoogleTest)
gtest_discover_tests(cxl_ut)
