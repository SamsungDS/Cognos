execute_process(COMMAND pkg-config --cflags svkframework OUTPUT_VARIABLE SVK_FW_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${SVK_FW_CFLAGS}")
include_directories(${GRPC_STUB_HDRS})
include_directories(${GRPC_SERVER_INC_DIR})
include_directories(${GRPC_SERVER_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/grpc_node_server)
# add_executable(svkgrpcnode_ut grpc_node_server_ut.cc ${GRPC_SERVER_INC_DIR}/grpc_server.h ${GRPC_SERVER_INC_DIR}/client_library.h)
add_executable(svkgrpcnode_ut grpc_node_server_ut.cc)

target_link_libraries(
  svkgrpcnode_ut
  GTest::gtest_main
  gmock_main
  svkgrpcnodetest
  dl
)
#  ${SVK_FW_GRPC_CORE_LIB}

include(GoogleTest)
gtest_discover_tests(svkgrpcnode_ut)
