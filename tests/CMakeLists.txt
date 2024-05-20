# Include directories
include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)

file(GLOB TEST_SOURCES
    sc_host_ut.cc
    sc_id_ut.cc
    main.cc
)

# Create executable for tests
add_executable(cxl_ut ${TEST_SOURCES})


# Include directories (adjust as needed)
target_include_directories(cxl_ut PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    /usr/local/include  # Add path to gtest/gmock headers
)


# Link with the library created in src
target_link_libraries(cxl_ut PRIVATE cxl_lib gtest gtest_main gmock gmock_main)

# Enable testing
enable_testing()
add_test(NAME cxl_test_suite COMMAND cxl_ut)
