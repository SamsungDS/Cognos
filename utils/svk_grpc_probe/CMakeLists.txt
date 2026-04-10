# Project name and version
project(
  cognos_grpc_probe
  VERSION ${SVK_GRPC_FW_VERSION}
  DESCRIPTION "Cognos GRPC Probe utility")

set(COMMON_SRC_DIR ${PARENT_DIR}/common/src)
set(COMMON_INC_DIR ${PARENT_DIR}/common/include)
message(STATUS "GRPC HDR ${GRPC_PROTO_SRC}")

# Include directories
include_directories(${GRPC_PROTO_SRC})
include_directories(${COMMON_INC_DIR})

# Source files
set(SOURCES ${GRPC_STUB_SRCS} ${COMMON_SRC_DIR}/client_library.cc
            src/cognos_grpc_probe.cc)

# Add executable
add_executable(${PROJECT_NAME} ${SOURCES})

# Link libraries
target_link_libraries(
  ${PROJECT_NAME}
  PUBLIC
    "${GRPC_LINK_LIBRARIES_FLAG} -lutf8_validity -Wl,--no-as-needed -lgrpc++_reflection -Wl,--as-needed -ldl"
)

target_link_libraries(${PROJECT_NAME} PUBLIC ${SVK_FW_GRPC_CORE_LIB})

set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC ${GRPC_CFLAGS}")

# Install executable
install(TARGETS ${PROJECT_NAME} DESTINATION bin)
