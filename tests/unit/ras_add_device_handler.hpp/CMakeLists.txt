set(RAS_ADD_DEVICE_HANDLER_UT "ras_add_device_handler_ut")

set(RAS_ADD_DEVICE_HANDLER_UT_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include)

include_directories(${CMAKE_CURRENT_BINARY_DIR}/include)

add_compile_options(${SVK_FW_CFLAGS})

include_directories(${RAS_UT_INCLUDE_DEST})
link_directories(${CMAKE_SOURCE_DIR}/build/src)

add_executable(${RAS_ADD_DEVICE_HANDLER_UT} ras_add_device_handler_ut.cc)
add_dependencies(${RAS_ADD_DEVICE_HANDLER_UT} ${RAS_UT})
target_include_directories(${RAS_ADD_DEVICE_HANDLER_UT} PUBLIC 
      ${RAS_ADD_DEVICE_HANDLER_UT_INCLUDE_DEST} 
      ${CMAKE_SOURCE_DIR}/tests/unit/include
      ${CMAKE_SOURCE_DIR}/src/utils/rte_ring
      )
target_link_directories(${RAS_ADD_DEVICE_HANDLER_UT} PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  ${RAS_ADD_DEVICE_HANDLER_UT}
  dl
  GTest::gtest_main
  svkframework
  svklogger
  rte_ring
  ${SVK_RAS_LIB_TARGET_NAME}
)

include(GoogleTest)
gtest_discover_tests(${RAS_ADD_DEVICE_HANDLER_UT})


