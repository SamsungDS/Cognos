set(RAS_MONITOR_UT "ras_monitor_ut")
set(RAS_MONITOR_UT_SOURCES ras_monitor_ut.cc)

add_executable(${RAS_MONITOR_UT} ${RAS_MONITOR_UT_SOURCES})
add_dependencies(${RAS_MONITOR_UT} rte_ring)
target_include_directories(${RAS_MONITOR_UT} PUBLIC ${CMAKE_SOURCE_DIR}/src/utils/rte_ring ${CMAKE_SOURCE_DIR}/include)

target_link_libraries(
  ${RAS_MONITOR_UT}
  GTest::gtest_main
  rte_ring
  ras
)

include(GoogleTest)
gtest_discover_tests(${RAS_MONITOR_UT})
