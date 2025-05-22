include_directories(${Framework_INC_DIR} ${Framework_INC_PRIVATE_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/framework)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(framework_ut framework_ut.cc ${Framework_INC_DIR}/framework_upstream.h)

target_link_libraries(
  framework_ut
  GTest::gtest_main
  gmock_main
  svkframework
  dl
)

add_executable(svk_pub_sub_ut svk_pub_sub_ut.cc ${Framework_INC_DIR}/svk_publisher.h)
target_link_libraries(svk_pub_sub_ut GTest::gtest_main gmock_main svkframework)

include(GoogleTest)
gtest_discover_tests(framework_ut)
gtest_discover_tests(svk_pub_sub_ut DISCOVERY_MODE PRE_TEST)
