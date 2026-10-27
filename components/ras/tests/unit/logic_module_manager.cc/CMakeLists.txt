
function(add_wrap_linker_flag func_name)
  add_link_options(-Wl,--wrap,${func_name})
endfunction()

# Usage
add_wrap_linker_flag(calloc)

include_directories(${UNIT_TEST_MOCK_INCLUDE_DIR})
set(LOGIC_MODULE_MANAGER_UT "lmm_ut")
set(LOGIC_MODULE_MANAGER_UT_SOURCES
${CMAKE_SOURCE_DIR}/src/utils/logic_module_manager.cc
logic_module_manager_ut.cc
)

add_executable(${LOGIC_MODULE_MANAGER_UT} ${LOGIC_MODULE_MANAGER_UT_SOURCES})
target_include_directories(${LOGIC_MODULE_MANAGER_UT} PUBLIC ${CMAKE_SOURCE_DIR}/include)
target_compile_options(${LOGIC_MODULE_MANAGER_UT} PRIVATE -std=c++20)


target_link_libraries(
  ${LOGIC_MODULE_MANAGER_UT}
  GTest::gtest_main
  gmock_main
)

include(GoogleTest)
gtest_discover_tests(${LOGIC_MODULE_MANAGER_UT})
