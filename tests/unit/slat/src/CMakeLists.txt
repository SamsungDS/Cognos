include_directories(${SLAT_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/slat)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(slat_ut slat_ut.cc)
execute_process(COMMAND pkg-config --cflags svkframework OUTPUT_VARIABLE SVK_FW_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
execute_process(COMMAND pkg-config --libs --static svkframework OUTPUT_VARIABLE SVK_FW_LIBS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC ${SVK_FW_CFLAGS}")

target_link_libraries(
  slat_ut
  GTest::gtest_main
  gmock_main
  "${SVK_FW_LIBS}"
  svkslat
  dl
)

include(GoogleTest)
gtest_discover_tests(slat_ut)
