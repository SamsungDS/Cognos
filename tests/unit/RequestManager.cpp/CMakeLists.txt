link_directories(${CMAKE_BUILD_DIR}/src)

set(REQUEST_MANAGER_UT "requestManager_ut")
set(REQUEST_MANAGER_UT_SOURCES
  RequestManager_ut.cc
)
add_executable(${REQUEST_MANAGER_UT} ${REQUEST_MANAGER_UT_SOURCES})
add_dependencies(${REQUEST_MANAGER_UT} rte_ring)
target_include_directories(${REQUEST_MANAGER_UT} PUBLIC ${CMAKE_SOURCE_DIR}/src/utils/rte_ring ${CMAKE_SOURCE_DIR}/include)

target_link_libraries(
  ${REQUEST_MANAGER_UT}
  GTest::gtest_main
  rte_ring
)

include(GoogleTest)
gtest_discover_tests(${REQUEST_MANAGER_UT})