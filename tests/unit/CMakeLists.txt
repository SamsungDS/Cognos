set(RAS_UT "ras_ut")
set(RAS_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include)

#TODO: if all the subdirectories of testing are using svk-core,
# put this complication option to the top level
add_compile_options(${SVK_FW_CFLAGS})

include_directories(${RAS_INCLUDE_DEST})
link_directories(${CMAKE_SOURCE_DIR}/build/src)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

add_executable(${RAS_UT} ras_ut.cc)

target_include_directories(${RAS_UT} PUBLIC ${RAS_INCLUDE_DEST})
target_link_directories(${RAS_UT} PUBLIC ${SVKFW_LIBRARY_DIRS})


target_link_libraries(
  ${RAS_UT}
  dl
  GTest::gtest_main
  gmock_main
  svkframework
  svklogger
  ras
)

include(GoogleTest)
gtest_discover_tests(${RAS_UT})
