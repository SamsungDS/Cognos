execute_process(COMMAND pkg-config --cflags svkframework OUTPUT_VARIABLE SVK_FW_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${SVK_FW_CFLAGS}")
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
include_directories(${GRPC_STUB_HDRS})
include_directories( ${GRPC_NODE_SERVER_INC_DIR})
include_directories(${GRPC_CONTROLLER_INC_DIR})
include_directories(${COMMON_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/grpc_node_server)
link_directories(${CMAKE_SOURCE_DIR}/build/grpc_controller)
add_executable(svkgrpcserver_it grpc_server_it.cc)

target_link_libraries(
    svkgrpcserver_it
    GTest::gtest_main
    gmock_main
    svkgrpcnodetest
    svkgrpccontrollertest
    dl
)

include(GoogleTest)
gtest_discover_tests(svkgrpcserver_it)
