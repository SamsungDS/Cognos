set(RAS_REQ_HANDLER_UT "ras_req_handler_ut")
set(RAS_REQ_HANDLER_UT_SOURCES
${CMAKE_SOURCE_DIR}/src/utils/logic_module_manager.cc
${CMAKE_SOURCE_DIR}/src/utils/ras_json_validate.cpp
${CMAKE_SOURCE_DIR}/src/ras_request_handler.cc
${CMAKE_SOURCE_DIR}/src/ras_monitor.cc 
ras_req_handler_ut.cc
)
add_executable(${RAS_REQ_HANDLER_UT} ${RAS_REQ_HANDLER_UT_SOURCES})
add_dependencies(${RAS_REQ_HANDLER_UT} rte_ring)
target_include_directories(${RAS_REQ_HANDLER_UT} PUBLIC 
    ${CMAKE_SOURCE_DIR}/src/utils/rte_ring 
    ${CMAKE_SOURCE_DIR}/include
    )

target_link_directories(${RAS_REQ_HANDLER_UT} PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  ${RAS_REQ_HANDLER_UT}
  GTest::gtest_main
  rte_ring
  svklogger
  fmt
  nlohmann_json::nlohmann_json
)

include(GoogleTest)
gtest_discover_tests(${RAS_REQ_HANDLER_UT})
