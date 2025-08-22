set(RAS_EVENT_PUBLISHER_UT "ras_event_publisher_ut")

set(RAS_EVENT_PUBLISHER_UT_SOURCES
ras_event_publisher_ut.cc
)
add_executable(${RAS_EVENT_PUBLISHER_UT} ${RAS_EVENT_PUBLISHER_UT_SOURCES})
target_include_directories(${RAS_EVENT_PUBLISHER_UT} PUBLIC  
  ${CMAKE_SOURCE_DIR}/include 
  ${CMAKE_SOURCE_DIR}/tests/unit/include
)

target_link_directories(${RAS_EVENT_PUBLISHER_UT} PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  ${RAS_EVENT_PUBLISHER_UT}
  GTest::gtest_main
  svklogger
  fmt
  nlohmann_json::nlohmann_json
)

include(GoogleTest)
gtest_discover_tests(${RAS_EVENT_PUBLISHER_UT})
