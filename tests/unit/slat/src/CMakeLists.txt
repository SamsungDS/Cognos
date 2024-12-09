include_directories(${SLAT_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/slat)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(slat_ut slat_ut.cc)
target_link_directories(slat_ut PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  slat_ut
  GTest::gtest_main
  gmock_main
  svklogger
  svkslat
  svkzmq
  dl
)

include(GoogleTest)
gtest_discover_tests(slat_ut)
