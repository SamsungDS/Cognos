project(
  svksvcmgr
  VERSION ${SVK_GRPC_FW_VERSION}
  DESCRIPTION "SVK Service Manager")

set(SRCS
    ${SVC_MGR_STUB_SRCS} ${CMAKE_CURRENT_SOURCE_DIR}/src/svc.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/svc_mgr.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/thread.cc)
set(INC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include/)

add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

add_executable(${PROJECT_NAME} ${SRCS})
add_library(svcmgr SHARED ${SRCS})

execute_process(
  COMMAND pkg-config --cflags svkframework
  OUTPUT_VARIABLE SVK_FW_CFLAGS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
execute_process(
  COMMAND pkg-config --libs --static svkframework
  OUTPUT_VARIABLE SVK_FW_LIBS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)

set(CMAKE_CXX_FLAGS
    "${CMAKE_CXX_FLAGS} -fPIC -rdynamic ${GRPC_CFLAGS} ${SVK_FW_CFLAGS}")
set_target_properties(
  ${PROJECT_NAME} PROPERTIES VERSION ${PROJECT_VERSION}
                             SOVERSION ${PROJECT_VERSION_MAJOR})

target_include_directories(${PROJECT_NAME} PUBLIC ${INC_DIR})
target_include_directories(svcmgr PUBLIC ${INC_DIR})

target_link_libraries(
  ${PROJECT_NAME}
  PUBLIC
    "${GRPC_LINK_LIBRARIES_FLAG} ${SVK_FW_LIBS} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -lzmq -lpthread -Wl,--as-needed -ldl -lsvklogger"
)
target_link_libraries(${PROJECT_NAME} PUBLIC ${SVK_FW_GRPC_CORE_LIB})
# target_link_libraries(${PROJECT_NAME} PUBLIC re2)
target_link_libraries(
  svcmgr
  PUBLIC
    "${GRPC_LINK_LIBRARIES_FLAG} ${SVK_FW_LIBS} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -lzmq -lpthread -Wl,--as-needed -ldl -lsvklogger"
)
target_link_libraries(svcmgr PUBLIC ${SVK_FW_GRPC_CORE_LIB})
# target_link_libraries(svcmgr PUBLIC re2)
if(BUILD_TESTING)
  add_library(svksvcmgrtest STATIC ${SRCS})
  set_target_properties(svksvcmgrtest PROPERTIES COMPILE_DEFINITIONS
                                                 "BUILD_TESTING")
  target_include_directories(svksvcmgrtest PUBLIC ${GRPC_PROTO_SRC})
  target_include_directories(svksvcmgrtest PUBLIC ${INC_DIR} ${COMMON_INC_DIR})
  target_link_libraries(svksvcmgrtest PUBLIC svcmgr)
  # target_link_libraries(svksvcmgrtest PUBLIC re2)
  install(FILES ${GRPC_INC_FILES} DESTINATION ${SVKGRPCFW_INCLUDE_DEST})
endif()
install(DIRECTORY ${INC_DIR} DESTINATION ${SVKGRPCFW_INCLUDE_DEST})
install(TARGETS svcmgr LIBRARY DESTINATION ${SVKGRPCFW_LIB_DEST})
install(
  TARGETS ${PROJECT_NAME}
  # name of the CMake "export group" containing the targets we want to install
  EXPORT ${PROJECT_NAME}Targets
  # Dynamic, static library and include destination locations after running
  # "make install"
  LIBRARY DESTINATION ${SVKGRPCFW_LIB_DEST}
  ARCHIVE DESTINATION ${SVKGRPCFW_LIB_DEST}
  INCLUDES
  DESTINATION ${SVKGRPCFW_INCLUDE_DEST})
