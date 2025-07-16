execute_process(COMMAND pkg-config --cflags svkframework OUTPUT_VARIABLE SVK_FW_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${SVK_FW_CFLAGS}")
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
include_directories(${GRPC_STUB_HDRS})
include_directories( ${GRPC_SERVER_INC_DIR})
include_directories(${COMMON_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/grpc_controller)
add_executable(svkgrpccontroller_ut
  ${CMAKE_SOURCE_DIR}/tests/mocks/client/mock_client.cpp
  grpc_controller_ut.cc)
target_include_directories(svkgrpccontroller_ut PRIVATE ${CMAKE_SOURCE_DIR}/tests/mocks/client)

target_link_libraries(
  svkgrpccontroller_ut
  GTest::gtest_main
  gmock_main
  svkgrpccontrollertest
  dl
)
#  ${SVK_FW_GRPC_CORE_LIB}

include(GoogleTest)
gtest_discover_tests(svkgrpccontroller_ut)
