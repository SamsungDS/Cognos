
project(svkfwgrpccore VERSION ${SVK_GRPC_FW_VERSION} DESCRIPTION "SVK FW GRPC Protobuf")

find_program(GRPC_PROTOC protoc)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin)

if (NOT GRPC_PROTOC OR NOT GRPC_CPP_PLUGIN)
    MESSAGE(FATAL_ERROR "protoc or cpp plugin not found")
endif()

set(PROTO_PATH .)
set(PROTO_THIRD_PARTY_PATH third_party)

set(GRPC_PROTO_SRC ${CMAKE_CURRENT_BINARY_DIR}/grpc/src)
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
    add_custom_command(OUTPUT ${PROTO_SRC} ${PROTO_HDR} ${GRPC_SRC} ${GRPC_HDR}
                        COMMAND ${GRPC_PROTOC} --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN} --cpp_out=${GRPC_PROTO_SRC} --grpc_out=${GRPC_PROTO_SRC} 
                        --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/${PROTO_THIRD_PARTY_PATH} --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/${PROTO_PATH} ${PROTO_FILE}
                        DEPENDS ${PROTO_FILE}
                        )

    list(APPEND GRPC_STUB_SRCS ${PROTO_SRC} ${GRPC_HDR}) 
    list(APPEND GRPC_STUB_HDRS ${GRPC_HDR} ${PROTO_HDR})
endforeach()

if (BUILD_SHARED_LIBS)
    add_library(${PROJECT_NAME} SHARED ${GRPC_STUB_SRCS})
else()
    add_library(${PROJECT_NAME} STATIC ${GRPC_STUB_SRCS})
endif()

set_target_properties(${PROJECT_NAME} PROPERTIES 
                        VERSION ${PROJECT_VERSION}
                        SOVERSION ${PROJECT_VERSION_MAJOR})

target_include_directories(${PROJECT_NAME} PUBLIC ${GRPC_PROTO_SRC})

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
