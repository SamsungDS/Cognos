find_package(fmt REQUIRED)
find_package(spdlog REQUIRED)

include_directories(${Common_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/common)
add_executable(svk_logger_ut svk_logger_ut.cc ${Common_INC_DIR}/svk_logger.h)
target_compile_definitions(svk_logger_ut PUBLIC "-DSPDLOG_FMT_EXTERNAL")

target_link_libraries(svk_logger_ut GTest::gtest_main svklogger)

include(GoogleTest)
gtest_discover_tests(svk_logger_ut DISCOVERY_MODE PRE_TEST)