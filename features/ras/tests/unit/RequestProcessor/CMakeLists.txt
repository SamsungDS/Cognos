set(REQUEST_PROCESSOR_UT "requestProcessor_ut")
set(REQUEST_PROCESSOR_UT_SOURCES
  RequestProcessor_ut.cc
)
add_executable(${REQUEST_PROCESSOR_UT} ${REQUEST_PROCESSOR_UT_SOURCES})
add_dependencies(${REQUEST_PROCESSOR_UT} rte_ring)
target_include_directories(${REQUEST_PROCESSOR_UT} PUBLIC ${CMAKE_SOURCE_DIR}/src/utils/rte_ring ${CMAKE_SOURCE_DIR}/include)

target_link_libraries(
  ${REQUEST_PROCESSOR_UT}
  GTest::gtest_main
  rte_ring
)

include(GoogleTest)
gtest_discover_tests(${REQUEST_PROCESSOR_UT})