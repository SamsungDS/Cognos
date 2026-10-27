set(LIBMOCK_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/libmock.cpp)
set(LOGICMOCK_SRC ${CMAKE_CURRENT_SOURCE_DIR}/src/logicmock.cpp)
set(LIBMOCK_INC ${CMAKE_CURRENT_SOURCE_DIR}/src/libmock.h)
set(LIBMOCK_CFG ${CMAKE_CURRENT_SOURCE_DIR}/config/mock_config.json)
set(LIBMOCK_LIB_DEST "adapters/mock/lib64/")
set(LIBMOCK_INCLUDE_DEST "include/adapters/mock")
set(LIBMOCK_CFG_DEST "adapters/mock/config/")
set(LIBMOCK "mock")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC")

include_directories(${CMAKE_SOURCE_DIR}/include)
add_library(libmock_mod OBJECT ${LIBMOCK_SRC})
add_library(${LIBMOCK} SHARED ${LOGICMOCK_SRC})
target_link_libraries(${LIBMOCK} libmock_mod numa svklogger)
target_link_directories(${LIBMOCK} PUBLIC ${SVKFW_LIBRARY_DIRS})

set_target_properties(${LIBMOCK} PROPERTIES
                      VERSION ${SVK_RAS_VERSION_FULL}
                      SOVERSION ${SVK_RAS_VERSION})

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/config/mock_config.json ${CMAKE_CURRENT_BINARY_DIR}/config/mock_config.json @ONLY)


install(TARGETS ${LIBMOCK}
        LIBRARY DESTINATION ${LIBMOCK_LIB_DEST}
        ARCHIVE DESTINATION ${LIBMOCK_INSTALL_DEST}
        INCLUDES DESTINATION ${LIBMOCK_INCLUDE_DEST})

install(FILES ${LIBMOCK_CFG} DESTINATION ${LIBMOCK_CFG_DEST})
