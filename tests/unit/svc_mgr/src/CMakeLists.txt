execute_process(
  COMMAND pkg-config --cflags svkframework
  OUTPUT_VARIABLE SVK_FW_CFLAGS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${SVK_FW_CFLAGS}")
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
include_directories(${SVC_MGR_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/svc_mgr)
add_executable(svksvcmgr_ut svc_mgr_ut.cc)

target_link_libraries(svksvcmgr_ut GTest::gtest_main gmock_main svksvcmgrtest
                      dl)
# ${SVK_FW_GRPC_CORE_LIB}

include(GoogleTest)
gtest_discover_tests(svksvcmgr_ut)
