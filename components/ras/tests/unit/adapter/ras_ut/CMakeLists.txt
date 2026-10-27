set(LOGICFAKE_SRC adapter_ras_ut.cc)
set(LIB_RAS_UT_ADAPTER "ras_adapter_ut")

include_directories(${CMAKE_SOURCE_DIR}/include)
include_directories(${CMAKE_CURRENT_BINARY_DIR})


set(UT_RAS_ADAPTER_NAME ${LIB_RAS_UT_ADAPTER})
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/adapter_ras_ut.h.in ${CMAKE_CURRENT_BINARY_DIR}/adapter_ras_ut.h @ONLY)

add_library(${LIB_RAS_UT_ADAPTER} SHARED ${LOGICFAKE_SRC})

set_target_properties(${LIB_RAS_UT_ADAPTER} PROPERTIES
                      VERSION ${SVK_RAS_VERSION_FULL}
                      SOVERSION ${SVK_RAS_VERSION})

file(MAKE_DIRECTORY ${BUILD_ADAPTERS_DIR}/${LIB_RAS_UT_ADAPTER}/lib64)
add_custom_target(copy_ras_ut_adapter_lib
  COMMAND ${CMAKE_COMMAND} -E copy
  ${CMAKE_CURRENT_BINARY_DIR}/lib${LIB_RAS_UT_ADAPTER}.so
  ${BUILD_ADAPTERS_DIR}/${LIB_RAS_UT_ADAPTER}/lib64/
)

add_dependencies(copy_ras_ut_adapter_lib ${LIB_RAS_UT_ADAPTER})