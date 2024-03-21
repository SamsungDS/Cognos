include_directories(${Framework_INC_DIR} ${Framework_INC_PRIVATE_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/framework)
add_executable(framework_ut framework_ut.cc ${Framework_INC_DIR}/framework_upstream.h)

target_link_libraries(
  framework_ut
  GTest::gtest_main
  gmock_main
  svkframework
  dl
)

include(GoogleTest)
gtest_discover_tests(framework_ut)