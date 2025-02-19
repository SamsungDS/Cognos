if(NOT PKG_CONFIG_PREFIX)
  set(RAS_FEATURE_DIR "usr/local/svk/feature_modules/ras")
else()
  set(RAS_FEATURE_DIR "${PKG_CONFIG_PREFIX}")
endif()
set(CONFIG_DIR "${RAS_FEATURE_DIR}/config/")
message(STATUS "ras config dir set to ${CONFIG_DIR}")
configure_file(${CMAKE_CURRENT_SOURCE_DIR}/config.json.in ${CMAKE_CURRENT_BINARY_DIR}/config.json @ONLY)

install(
    FILES ${CMAKE_CURRENT_BINARY_DIR}/config.json
    DESTINATION "${CONFIG_DIR}"
    PERMISSIONS OWNER_READ OWNER_EXECUTE GROUP_READ WORLD_READ
)
