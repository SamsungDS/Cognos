set(NodeMgmt_INC_DIR ${CMAKE_SOURCE_DIR}/include)

include_directories(${NodeMgmt_INC_DIR})
link_directories(${CMAKE_SOURCE_DIR}/build/src)
add_executable(node_info_ut node_info_ut.cc ${NodeMgmt_INC_DIR}/node_info.hpp)

target_link_libraries(
    node_info_ut
    GTest::gtest_main
    gmock_main
    svknode
    svkframework
)

file(COPY "${CMAKE_SOURCE_DIR}/src/node_info/find_node_info.py" DESTINATION "node/scripts/")
file(COPY "${CMAKE_SOURCE_DIR}/config/node_mgmt_conf.json" DESTINATION "node/config/")

include(GoogleTest)
gtest_discover_tests(node_info_ut)
