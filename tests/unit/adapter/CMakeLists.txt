
set(LIBMOCKTEST "libmocktest")
set(LIBMOCK_INCLUDE_DEST ${CMAKE_SOURCE_DIR}/include/adapters/mock_adapter/include ${CMAKE_CURRENT_SOURCE_DIR}/include ${CMAKE_SOURCE_DIR}/adapters/mock_adapter/src)

include_directories(${LIBMOCK_INCLUDE_DEST})
link_directories(${CMAKE_SOURCE_DIR}/adapters/mock_adapter/lib64)
add_executable(${LIBMOCKTEST} libmocktest.cpp)

target_include_directories(${LIBMOCKTEST} PUBLIC ${LIBMOCK_INCLUDE_DEST})
find_package(GTest)

target_link_libraries(${LIBMOCKTEST} GTest::gtest_main gmock_main mock numa )

configure_file(${CMAKE_SOURCE_DIR}/adapters/mock_adapter/config/mock_config.json ${CMAKE_CURRENT_BINARY_DIR}/config/mock_config.json @ONLY)


include(GoogleTest)
gtest_discover_tests(${LIBMOCKTEST})
