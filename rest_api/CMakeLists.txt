set(SVK_GRPC_GW svkfwgrpcgw PARENT_SCOPE)
project(svkfwgrpcgw VERSION ${SVK_GRPC_FW_VERSION} DESCRIPTION "SVK FW GRPC Protobuf")

set(PROTOBUF_ABSL_DEPS absl_absl_check absl_absl_log absl_algorithm absl_base absl_bind_front
                        absl_bits absl_btree absl_cleanup absl_cord absl_core_headers absl_debugging
                        absl_die_if_null absl_dynamic_annotations absl_flags absl_flat_hash_map absl_flat_hash_set
                        absl_function_ref absl_hash absl_layout absl_log_initialize absl_log_severity absl_memory
                        absl_node_hash_map absl_node_hash_set absl_optional absl_span absl_status absl_statusor absl_strings
                        absl_synchronization absl_time absl_type_traits absl_utility absl_variant)

set(GRPC_DEPS protobuf grpc++ absl_flags absl_flags_parse)

find_program(GRPC_PROTOC protoc)

if (NOT GRPC_PROTOC)
    MESSAGE(FATAL_ERROR "protoc not found")
endif()

set(PROTO_PATH ${PARENT_DIR}/proto/)
set(PROTO_THIRD_PARTY_PATH ${PROTO_PATH}/third_party)
set(PROTO_GO_API_DIR ${CMAKE_CURRENT_BINARY_DIR}/api/)
set(PROTO_OPENAPI_DIR ${CMAKE_CURRENT_BINARY_DIR}/third_party/OpenAPI)
set(GOPATH_DIR "$ENV{GOPATH}")

set(PROTO_FILE ${PROTO_PATH}/framework/framework.proto)
make_directory(${CMAKE_CURRENT_BINARY_DIR}/api/)
make_directory(${CMAKE_CURRENT_BINARY_DIR}/third_party/OpenAPI)

execute_process(COMMAND ${GRPC_PROTOC} --go_out=${PROTO_GO_API_DIR} --go_opt paths=source_relative
                    --go-grpc_out=${PROTO_GO_API_DIR} --go-grpc_opt paths=source_relative
                    --grpc-gateway_out=${PROTO_GO_API_DIR} --grpc-gateway_opt paths=source_relative 
                    --openapiv2_out=logtostderr=true:${PROTO_OPENAPI_DIR}
                    --proto_path=${PROTO_PATH} --proto_path=${PROTO_THIRD_PARTY_PATH}
                    ${PROTO_FILE}
                )

file(COPY ${PARENT_DIR}/rest_api/cmd DESTINATION ${PARENT_DIR}/build/rest_api/tests)
file(COPY ${PARENT_DIR}/rest_api/third_party DESTINATION ${PARENT_DIR}/build/rest_api/tests)
file(COPY ${GOPATH_DIR}/go_files_dir/go.mod DESTINATION ${PARENT_DIR}/build/rest_api/tests)
file(COPY ${GOPATH_DIR}/go_files_dir/go.sum DESTINATION ${PARENT_DIR}/build/rest_api/tests)
file(COPY ${CMAKE_CURRENT_BINARY_DIR}/api DESTINATION ${PARENT_DIR}/build/rest_api/tests)
file(COPY ${CMAKE_CURRENT_BINARY_DIR}/third_party DESTINATION ${PARENT_DIR}/build/rest_api/tests)
