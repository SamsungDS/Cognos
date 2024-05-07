set(SVK_FW_GRPC_CORE_LIB svkfwgrpccore PARENT_SCOPE)
project(svkfwgrpccore VERSION ${SVK_GRPC_FW_VERSION} DESCRIPTION "SVK FW GRPC Protobuf")

set(PROTOBUF_ABSL_DEPS absl_absl_check absl_absl_log absl_algorithm absl_base absl_bind_front
                        absl_bits absl_btree absl_cleanup absl_cord absl_core_headers absl_debugging
                        absl_die_if_null absl_dynamic_annotations absl_flags absl_flat_hash_map absl_flat_hash_set
                        absl_function_ref absl_hash absl_layout absl_log_initialize absl_log_severity absl_memory
                        absl_node_hash_map absl_node_hash_set absl_optional absl_span absl_status absl_statusor absl_strings
                        absl_synchronization absl_time absl_type_traits absl_utility absl_variant)

set(GRPC_DEPS protobuf grpc++ absl_flags absl_flags_parse)

# find_package(protobuf CONFIG REQUIRED)
# find_package(grpc CONFIG REQUIRED)

find_program(GRPC_PROTOC protoc)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin)

if (NOT GRPC_PROTOC OR NOT GRPC_CPP_PLUGIN)
    MESSAGE(FATAL_ERROR "protoc or cpp plugin not found")
endif()

set(PROTO_PATH .)
set(PROTO_THIRD_PARTY_PATH third_party)

set(GRPC_PROTO_SRC ${CMAKE_CURRENT_BINARY_DIR}/grpc/src)
set(GRPC_PROTO_SRC ${GRPC_PROTO_SRC} PARENT_SCOPE)
set(GRPC_PROTO_OPENAPI_SRC src/openapi_gw)

file(MAKE_DIRECTORY ${GRPC_PROTO_SRC})

file(GLOB_RECURSE PROTO_FILES "${PROTO_PATH}/*.proto")

foreach(PROTO_FILE ${PROTO_FILES})
    # Get the filename and the directory path
    get_filename_component(FILENAME ${PROTO_FILE} NAME_WLE)
    get_filename_component(ITEM_PATH ${PROTO_FILE} DIRECTORY)

    # Get the relative path w.r.t. "proto" dir
    file(RELATIVE_PATH ITEM_PATH_REL "${CMAKE_CURRENT_SOURCE_DIR}/" ${ITEM_PATH})
    # Strip the "third_party/" text from the relative path as the protoc fails in generating the stubs
    if ("${ITEM_PATH_REL}" STREQUAL "")
        set(ITEM_PATH_STRIP "")
    else()
        string(REPLACE "third_party/" "" ITEM_PATH_STRIP ${ITEM_PATH_REL})
    endif()
    file(MAKE_DIRECTORY ${GRPC_PROTO_SRC}/${ITEM_PATH_STRIP})
    # The stubs generated will be of the form <file>.pb.cc/h and <file>.grpc.pb.cc/h for GRPC
    set(PROTO_SRC "${GRPC_PROTO_SRC}/${ITEM_PATH_STRIP}/${FILENAME}.pb.cc")
    set(PROTO_HDR "${GRPC_PROTO_SRC}/${ITEM_PATH_STRIP}/${FILENAME}.pb.h")
    set(GRPC_SRC "${GRPC_PROTO_SRC}/${ITEM_PATH_STRIP}/${FILENAME}.grpc.pb.cc")
    set(GRPC_HDR "${GRPC_PROTO_SRC}/${ITEM_PATH_STRIP}/${FILENAME}.grpc.pb.h")

    # Run the protoc compiler on the proto files
    if(BUILD_TESTING)
        set(GRPC_MOCK_HDR "${GRPC_PROTO_SRC}/${ITEM_PATH_STRIP}/${FILENAME}_mock.grpc.pb.h")
        add_custom_command(OUTPUT ${PROTO_SRC} ${PROTO_HDR} ${GRPC_SRC} ${GRPC_HDR}
                            COMMAND ${GRPC_PROTOC} --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN} --cpp_out=${GRPC_PROTO_SRC} --grpc_out=generate_mock_code=true:${GRPC_PROTO_SRC}
                            --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/${PROTO_THIRD_PARTY_PATH} --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/${PROTO_PATH} ${PROTO_FILE}
                            DEPENDS ${PROTO_FILE}
                        )
    else()
        set(GRPC_MOCK_HDR "")
        add_custom_command(OUTPUT ${PROTO_SRC} ${PROTO_HDR} ${GRPC_SRC} ${GRPC_HDR}
                            COMMAND ${GRPC_PROTOC} --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN} --cpp_out=${GRPC_PROTO_SRC} --grpc_out=${GRPC_PROTO_SRC} 
                            --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/${PROTO_THIRD_PARTY_PATH} --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/${PROTO_PATH} ${PROTO_FILE}
                            DEPENDS ${PROTO_FILE}
                        )
    endif()

    list(APPEND GRPC_STUB_SRCS ${GRPC_SRC} ${PROTO_SRC})
    list(APPEND GRPC_STUB_HDRS ${GRPC_HDR} ${PROTO_HDR} ${GRPC_MOCK_HDR})
endforeach()

set(${GRPC_STUB_SRCS} ${${GRPC_STUB_SRCS}} PARENT_SCOPE)
set(${GRPC_STUB_HDRS} ${${GRPC_STUB_HDRS}} PARENT_SCOPE)

string(REPLACE ";" " " absl_deps "${PROTOBUF_ABSL_DEPS}")

execute_process(COMMAND pkg-config --libs --static protobuf grpc++ absl_flags absl_flags_parse "${absl_deps}" OUTPUT_VARIABLE GRPC_LINK_LIBRARIES_FLAG OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)

execute_process(COMMAND pkg-config --cflags protobuf grpc absl_flags absl_flags_parse OUTPUT_VARIABLE GRPC_CFLAGS OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC ${GRPC_CFLAGS}")

if (BUILD_SHARED_LIBS)
    add_library(${PROJECT_NAME} SHARED ${GRPC_STUB_SRCS})
else()
    add_library(${PROJECT_NAME} STATIC ${GRPC_STUB_SRCS})
endif()

set_target_properties(${PROJECT_NAME} PROPERTIES 
                        VERSION ${PROJECT_VERSION}
                        SOVERSION ${PROJECT_VERSION_MAJOR})

target_include_directories(${PROJECT_NAME} PUBLIC ${GRPC_PROTO_SRC})
target_link_libraries(${PROJECT_NAME} PUBLIC "${GRPC_LINK_LIBRARIES_FLAG} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -Wl,--as-needed -ldl")

install(
    TARGETS ${PROJECT_NAME}
    # name of the CMake "export group" containing the targets we want to install
    EXPORT ${PROJECT_NAME}Targets
    # Dynamic, static library and include destination locations after running
    # "make install"
    LIBRARY DESTINATION ${SVKGRPCFW_LIB_DEST}
    ARCHIVE DESTINATION ${SVKGRPCFW_LIB_DEST} 
    INCLUDES DESTINATION ${SVKGRPCFW_INCLUDE_DEST}
    )

foreach(HDR_FILE ${GRPC_STUB_HDRS})
    get_filename_component(ITEM_PATH ${HDR_FILE} DIRECTORY)
    string(REPLACE "${GRPC_PROTO_SRC}" "" ITEM_PATH_REL ${ITEM_PATH})
    INSTALL(FILES ${HDR_FILE} DESTINATION ${SVKGRPCFW_INCLUDE_DEST}/${ITEM_PATH_REL})
endforeach()
