set(RAS_UT "ras_ut")
set(RAS_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include)

set(UNIT_TEST_MOCK_INCLUE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_subdirectory(logic_module_manager.cc)

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
  svkframework
  svklogger
  ras
)

enable_testing()
add_subdirectory(RequestManager.cpp)
add_subdirectory(RequestProcessor)
add_subdirectory(ras_monitor.cc)

include(GoogleTest)
gtest_discover_tests(${RAS_UT})


