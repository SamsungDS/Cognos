
get_all_devices_query = "SELECT * FROM logical_memory_device;"

get_device_host_connections_query = (
    'SELECT lmd, GROUP_CONCAT(DISTINCT host SEPARATOR \',\') '
    'as memory_servers FROM connections GROUP BY lmd;'
)

update_lmd_status_query = (
    "UPDATE logical_memory_device "
    "SET status = %s "
    "WHERE lmd = %s;"
)
