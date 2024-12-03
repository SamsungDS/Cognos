SET(CONFIG_FILES "mgmt_fw_config.json;device_sla_config.json.example")
set(CONFIG_DIR "/etc/svk")

foreach(ITEM ${CONFIG_FILES})
    install(
        FILES "${ITEM}"
        DESTINATION "${CONFIG_DIR}"
        PERMISSIONS OWNER_READ OWNER_EXECUTE GROUP_READ WORLD_READ
    )
endforeach()
