set(LIBMOCK_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/libmock.cpp)
set(LIBMOCK_INC ${CMAKE_SOURCE_DIR}/include/adapters/mock_adapter/include/libmock.h)
set(LIBMOCK_CFG ${CMAKE_CURRENT_SOURCE_DIR}/config/mock_config.json)
set(LIBMOCK_LIB_DEST "adapters/mock_adapter/lib64/")
set(LIBMOCK_INCLUDE_DEST "include/adapters/mock_adapter/include/")
set(LIBMOCK_CFG_DEST "adapters/mock_adapter/config")
set(LIBMOCK "mock")

include_directories(${CMAKE_SOURCE_DIR}/include)
add_library(${LIBMOCK} SHARED ${LIBMOCK_SRC} )
target_link_directories(${LIBMOCK} PUBLIC ${SVKFW_LIBRARY_DIRS})
target_link_libraries(${LIBMOCK} numa svklogger)

set_target_properties(${LIBMOCK} PROPERTIES
                      VERSION ${SVK_RAS_VERSION_FULL}
                      SOVERSION ${SVK_RAS_VERSION})

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/config/mock_config.json ${CMAKE_CURRENT_BINARY_DIR}/config/mock_config.json @ONLY)

install(DIRECTORY DESTINATION ${LIBMOCK_LIB_DEST})
install(TARGETS ${LIBMOCK}
        LIBRARY DESTINATION ${LIBMOCK_LIB_DEST}
        ARCHIVE DESTINATION ${LIBMOCK_INSTALL_DEST}
        INCLUDES DESTINATION ${LIBMOCK_INCLUDE_DEST})

install(DIRECTORY DESTINATION ${LIBMOCK_INCLUDE_DEST})
install(FILES ${LIBMOCK_INC} DESTINATION ${LIBMOCK_INCLUDE_DEST})
install(DIRECTORY DESTINATION ${LIBMOCK_CFG_DEST})
install(FILES ${LIBMOCK_CFG} DESTINATION ${LIBMOCK_CFG_DEST})

