project(
  svkgrpcnode
  VERSION ${SVK_GRPC_FW_VERSION}
  DESCRIPTION "SVK GRPC Node Server")

set(PROTOBUF_ABSL_DEPS
    absl_absl_check
    absl_absl_log
    absl_algorithm
    absl_base
    absl_bind_front
    absl_bits
    absl_btree
    absl_cleanup
    absl_cord
    absl_core_headers
    absl_debugging
    absl_die_if_null
    absl_dynamic_annotations
    absl_flags
    absl_flat_hash_map
    absl_flat_hash_set
    absl_function_ref
    absl_hash
    absl_layout
    absl_log_initialize
    absl_log_severity
    absl_memory
    absl_node_hash_map
    absl_node_hash_set
    absl_optional
    absl_span
    absl_status
    absl_statusor
    absl_strings
    absl_synchronization
    absl_time
    absl_type_traits
    absl_utility
    absl_variant)

set(GRPC_DEPS protobuf grpc++ absl_flags absl_flags_parse)

set(COMMON_INC_DIR ${PARENT_DIR}/common/include/)
set(COMMON_SRC_DIR ${PARENT_DIR}/common/src)
set(SRCS ${GRPC_STUB_SRCS} ${CMAKE_CURRENT_SOURCE_DIR}/src/grpc_server.cc
         ${COMMON_SRC_DIR}/client_library.cc)
if(BUILD_TESTING)
  set(GRPC_INC_FILES
      ${COMMON_INC_DIR}/grpc_hdr.h ${COMMON_INC_DIR}/client_library.h
      ${CMAKE_CURRENT_SOURCE_DIR}/include/grpc_server.h
      PARENT_SCOPE)
endif()
set(INC_DIR ${CMAKE_CURRENT_SOURCE_DIR}/include/ ${json_SOURCE_DIR}/include)
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

add_executable(${PROJECT_NAME} ${SRCS})

string(REPLACE ";" " " absl_deps "${PROTOBUF_ABSL_DEPS}")
execute_process(
  COMMAND pkg-config --libs --static protobuf grpc++ absl_flags absl_flags_parse
          "${absl_deps}"
  OUTPUT_VARIABLE GRPC_LINK_LIBRARIES_FLAG
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
execute_process(
  COMMAND pkg-config --cflags protobuf grpc absl_flags absl_flags_parse
  OUTPUT_VARIABLE GRPC_CFLAGS
  OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
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

target_include_directories(${PROJECT_NAME} PUBLIC ${GRPC_PROTO_SRC})
target_include_directories(${PROJECT_NAME} PUBLIC ${INC_DIR} ${COMMON_INC_DIR})

target_link_libraries(
  ${PROJECT_NAME}
  PUBLIC
    "${GRPC_LINK_LIBRARIES_FLAG} ${SVK_FW_LIBS} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -Wl,--as-needed -ldl -lsvklogger -lsvkframework"
)
target_link_libraries(${PROJECT_NAME} PUBLIC ${SVK_FW_GRPC_CORE_LIB})

if(BUILD_TESTING)
  add_library(svkgrpcnodetest STATIC ${SRCS})
  set_target_properties(svkgrpcnodetest PROPERTIES COMPILE_DEFINITIONS
                                                   "BUILD_TESTING")
  target_include_directories(svkgrpcnodetest PUBLIC ${GRPC_PROTO_SRC})
  target_include_directories(svkgrpcnodetest PUBLIC ${INC_DIR}
                                                    ${COMMON_INC_DIR})

  target_link_libraries(
    svkgrpcnodetest
    PUBLIC
      "${GRPC_LINK_LIBRARIES_FLAG} ${SVK_FW_LIBS} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -Wl,--as-needed -ldl -lsvklogger -lsvkframework"
  )
  target_link_libraries(svkgrpcnodetest PUBLIC ${SVK_FW_GRPC_CORE_LIB})
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
