set(RAS_UT "ras_ut")
set(RAS_UT_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include)


function(set_if_running_inside_container)
  message(STATUS "Checking if running inside a container")
  set(RAS_UT_INSIDE_CONTAINER 0 PARENT_SCOPE)
  if(EXISTS /.dockerenv) #This checks if running inside docker container
    set(RAS_UT_INSIDE_CONTAINER 1 PARENT_SCOPE)
    message(STATUS "Running inside docker container")
  # ADD more cases if other containers need to be supported
  else()
   message(STATUS "Not running inside any container")
  endif()
endfunction()

set_if_running_inside_container()

include_directories(${CMAKE_CURRENT_BINARY_DIR}/include)

set(UNIT_TEST_MOCK_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_subdirectory(logic_module_manager.cc)

set(BUILD_ADAPTERS_DIR ${CMAKE_BINARY_DIR}/adapters)
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/include/ras_ut_config.h.in ${CMAKE_CURRENT_BINARY_DIR}/include/ras_ut_config.h @ONLY)

#TODO: if all the subdirectories of testing are using svk-core,
# put this complication option to the top level
add_compile_options(${SVK_FW_CFLAGS})

include_directories(${RAS_UT_INCLUDE_DEST})
link_directories(${CMAKE_SOURCE_DIR}/build/src)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

file(MAKE_DIRECTORY ${BUILD_ADAPTERS_DIR}/mock/lib64)
file(MAKE_DIRECTORY ${BUILD_ADAPTERS_DIR}/ras/lib64)

add_custom_target(copy_mock_adapter_lib
  COMMAND ${CMAKE_COMMAND} -E copy
  ${CMAKE_BINARY_DIR}/adapters/mock_adapter/libmock.so
  ${BUILD_ADAPTERS_DIR}/mock/lib64/
  COMMAND ${CMAKE_COMMAND} -E copy
  ${CMAKE_BINARY_DIR}/src/libras.so
  ${BUILD_ADAPTERS_DIR}/ras/lib64/
)

add_dependencies(copy_mock_adapter_lib mock ras)

add_executable(${RAS_UT} ras_ut.cc)
add_dependencies(${RAS_UT} copy_mock_adapter_lib)
add_dependencies(${RAS_UT} copy_ras_ut_adapter_lib)
target_include_directories(${RAS_UT} PUBLIC ${RAS_UT_INCLUDE_DEST} ${CMAKE_CURRENT_BINARY_DIR}/include)
target_link_directories(${RAS_UT} PUBLIC ${SVKFW_LIBRARY_DIRS})


target_link_libraries(
  ${RAS_UT}
  dl
  GTest::gtest_main
  svkframework
  svklogger
  ras
  fmt
)

enable_testing()
add_subdirectory(RequestManager.cpp)
add_subdirectory(RequestProcessor)
add_subdirectory(ras_monitor.cc)
add_subdirectory(ras_request_handler.cc)
add_subdirectory(ras_device.h)

add_subdirectory(adapter)

include(GoogleTest)
gtest_discover_tests(${RAS_UT})


