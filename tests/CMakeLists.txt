# Include directories
include_directories(${CMAKE_SOURCE_DIR}/src)
include(gtest)
link_directories(/home/s1.nagaraja/cxl_memory_box/mbox_a1/build ${CMAKE_SOURCE_DIR}/build/src)

file(GLOB TEST_SOURCES
    sc_servicer_ut.cc	
    sc_global_ut.cc	
    sc_mbox_ut.cc	
    sc_endpoint_ut.cc
    sc_switch_ut.cc    
    sc_device_ut.cc
    sc_mld_ut.cc
    sc_sld_ut.cc
    sc_host_ut.cc
    sc_id_ut.cc
    main.cc
)

# Create executable for tests
add_executable(cxl_ut ${TEST_SOURCES})

include(${CMAKE_SOURCE_DIR}/cmake/gtest.cmake)
# Include directories (adjust as needed)
target_include_directories(cxl_ut PRIVATE
    ${CMAKE_SOURCE_DIR}/src
    /usr/include
    /usr/local/include  # Add path to gtest/gmock headers
)


# Link with the library created in src
target_link_libraries(cxl_ut PRIVATE cxl_lib gtest gtest_main gmock gmock_main)

include(GoogleTest)
gtest_discover_tests(cxl_ut)
