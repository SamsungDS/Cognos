set(TEST_BIN_EXECUTABLE_PATH ${CMAKE_CURRENT_BINARY_DIR}/test_bin)
set(MLC_BIN_MOCK_EXECUTABLE_PATH ${CMAKE_CURRENT_BINARY_DIR}/mlc_bin_mock)
set(MLC_TEST_BIN_EXECUTABLE_PATH ${CMAKE_SOURCE_DIR}/modules/logic/slat_mlc/deps/mlc/Linux/mlc)
configure_file(test_bin.h.in test_bin.h @ONLY)
add_executable(test_bin test_bin.cc)
add_executable(mlc_bin_mock mlc_bin_mock.cc)

include_directories(${SLAT_INC_DIR})
include_directories(${CMAKE_SOURCE_DIR}/modules/logic/slat_mlc/src)
include_directories(${CMAKE_CURRENT_BINARY_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/slat)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(slat_run_bin_ut slat_run_bin_ut.cc)
add_dependencies(slat_run_bin_ut mlclogic)
target_link_directories(slat_run_bin_ut PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  slat_run_bin_ut
  mlclogic
  GTest::gtest_main
  gmock_main
  svklogger
  svkslat
  svkzmq
  dl
)

include(GoogleTest)
gtest_discover_tests(slat_run_bin_ut)