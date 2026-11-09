set(RAS_ADAPTER_HELPER_UT "ras_adapter_helper_ut")

set(AS_ADAPTER_HELPER_UT_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include)

include_directories(${CMAKE_CURRENT_BINARY_DIR}/include)

add_compile_options(${SVK_FW_CFLAGS})

include_directories(${RAS_UT_INCLUDE_DEST})
link_directories(${CMAKE_SOURCE_DIR}/build/src)

add_executable(${RAS_ADAPTER_HELPER_UT} ras_adapter_helper_ut.cc)
add_dependencies(${RAS_ADAPTER_HELPER_UT} ${RAS_UT})
target_include_directories(${RAS_ADAPTER_HELPER_UT} PUBLIC 
      ${RAS_ADAPTER_HELPER_UT_INCLUDE_DEST} 
      ${CMAKE_BINARY_DIR}/tests/unit/include)
target_link_directories(${RAS_ADAPTER_HELPER_UT} PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  ${RAS_ADAPTER_HELPER_UT}
  dl
  GTest::gtest_main
  svkframework
  svklogger
  ${SVK_RAS_LIB_TARGET_NAME}
)

include(GoogleTest)
gtest_discover_tests(${RAS_ADAPTER_HELPER_UT})


