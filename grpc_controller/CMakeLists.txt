project(
  svkgrpccontroller
  VERSION ${SVK_GRPC_FW_VERSION}
  DESCRIPTION "SVK GRPC Controller Server")

set(COMMON_INC_DIR ${PARENT_DIR}/common/include/)
set(COMMON_SRC_DIR ${PARENT_DIR}/common/src)
set(SRCS
    ${GRPC_STUB_SRCS}
    ${CMAKE_CURRENT_SOURCE_DIR}/src/circular_queue.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/grpc_controller.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/events_handler.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/events_hlpr.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/sla_hlpr_fns.cc
    ${CMAKE_CURRENT_SOURCE_DIR}/src/node_cmd_helper_fns.cc
    ${PARENT_DIR}/heartbeat/src/heartbeat_manager.cc
    ${COMMON_SRC_DIR}/client_library.cc)
if(BUILD_TESTING)
  set(GRPC_INC_FILES
      ${COMMON_INC_DIR}/grpc_hdr.h ${COMMON_INC_DIR}/client_library.h
      ${CMAKE_CURRENT_SOURCE_DIR}/include/grpc_controller.h
      PARENT_SCOPE)
endif()
set(INC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include/ ${json_SOURCE_DIR}/include)
set(HEARTBEAT_INC_DIR ${PARENT_DIR}/heartbeat/include/)

add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)
add_executable(${PROJECT_NAME} ${SRCS})

execute_process(
  COMMAND pkg-config --cflags svkframework
  OUTPUT_VARIABLE SVK_FW_CFLAGS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
execute_process(
  COMMAND pkg-config --libs --static svkframework
  OUTPUT_VARIABLE SVK_FW_LIBS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC ${GRPC_CFLAGS} ${SVK_FW_CFLAGS}")
set_target_properties(
  ${PROJECT_NAME} PROPERTIES VERSION ${PROJECT_VERSION}
                             SOVERSION ${PROJECT_VERSION_MAJOR})

set(HEARTBEAT_LOGGER_MODULE_NAME_CONTROLLER "mgmt_fw_controller")
target_compile_definitions(${PROJECT_NAME} PRIVATE "HEARTBEAT_LOGGER_MODULE_NAME=\"${HEARTBEAT_LOGGER_MODULE_NAME_CONTROLLER}\"")

target_include_directories(${PROJECT_NAME} PUBLIC ${GRPC_PROTO_SRC})
target_include_directories(${PROJECT_NAME} PUBLIC ${INC_DIR} ${COMMON_INC_DIR}
                                                 ${HEARTBEAT_INC_DIR})
target_link_directories(${PROJECT_NAME} PUBLIC ${SVKFW_LIBRARY_DIRS})

target_link_libraries(
  ${PROJECT_NAME}
  PUBLIC
    "${GRPC_LINK_LIBRARIES_FLAG} ${SVK_FW_LIBS} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -Wl,--as-needed -ldl -lsvklogger"
)
target_link_libraries(${PROJECT_NAME} PUBLIC ${SVK_FW_GRPC_CORE_LIB})
target_link_libraries(${PROJECT_NAME} PUBLIC zmq)
target_link_libraries(${PROJECT_NAME} PUBLIC svkzmq)
target_link_libraries(${PROJECT_NAME} PUBLIC nlohmann_json::nlohmann_json)
target_link_libraries(${PROJECT_NAME} PUBLIC systemd)

if(BUILD_TESTING)
  add_library(svkgrpccontrollertest SHARED ${SRCS})
  set_target_properties(svkgrpccontrollertest PROPERTIES COMPILE_DEFINITIONS
                                                         "BUILD_TESTING")
  target_include_directories(svkgrpccontrollertest PUBLIC ${GRPC_PROTO_SRC})
  target_include_directories(svkgrpccontrollertest PUBLIC ${INC_DIR}
                                                          ${COMMON_INC_DIR}
                                                          ${HEARTBEAT_INC_DIR})
  target_compile_definitions(svkgrpccontrollertest PRIVATE "HEARTBEAT_LOGGER_MODULE_NAME=\"${HEARTBEAT_LOGGER_MODULE_NAME_CONTROLLER}\"")
  target_link_directories(${PROJECT_NAME} PUBLIC ${SVKFW_LIBRARY_DIRS})
  target_link_libraries(
    svkgrpccontrollertest
    PUBLIC
      "${GRPC_LINK_LIBRARIES_FLAG} ${SVK_FW_LIBS} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -Wl,--as-needed -ldl -lsvklogger"
  )
  target_link_libraries(svkgrpccontrollertest PUBLIC ${SVK_FW_GRPC_CORE_LIB})
  target_link_libraries(svkgrpccontrollertest PUBLIC svkzmq)
  target_link_libraries(svkgrpccontrollertest PUBLIC zmq)
  target_link_libraries(svkgrpccontrollertest PUBLIC systemd)
  install(FILES ${GRPC_INC_FILES} DESTINATION ${SVKGRPCFW_INCLUDE_DEST})
endif()

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
