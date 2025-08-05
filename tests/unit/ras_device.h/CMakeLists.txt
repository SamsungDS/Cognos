set(RAS_DEVICE_UT "ras_device_ut")
set(RAS_DEVICE_UT_SOURCES ras_device_ut.cc)
add_executable(${RAS_DEVICE_UT} ${RAS_DEVICE_UT_SOURCES})
target_include_directories(${RAS_DEVICE_UT} PUBLIC ${CMAKE_SOURCE_DIR}/include)


target_link_libraries(
  ${RAS_DEVICE_UT}
  GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(${RAS_DEVICE_UT})
