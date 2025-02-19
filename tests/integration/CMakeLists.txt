set(RAS_IT "integr_framework")
set(RAS_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include)

include_directories(${RAS_INC_DEST})
link_directories(${CMAKE_SOURCE_DIR}/build/src)
link_directories(${CMAKE_SOURCE_DIR}/include)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(${RAS_IT} ras_it_svkcore.cc)

target_include_directories(${RAS_IT} PUBLIC ${RAS_INCLUDE_DEST})
target_link_directories(${RAS_IT} PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  ${RAS_IT}
  dl
  GTest::gtest_main
  gmock_main
  svkframework
  svklogger
)

include(GoogleTest)
gtest_discover_tests(${RAS_IT})
