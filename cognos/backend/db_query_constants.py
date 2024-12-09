get_all_devices_query = "SELECT * FROM logical_memory_device;"

get_device_host_connections_query = (
    "SELECT lmd, GROUP_CONCAT(DISTINCT host SEPARATOR ',') "
    "as memory_servers FROM connections GROUP BY lmd;"
)

update_lmd_status_query = (
    "UPDATE logical_memory_device SET status = %s WHERE lmd = %s;"
)

DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
APPLICATION_JSON = "application/json"
CLUSTER_SETUP_COMMAND = "cluster_id=CLUST1;command=SetupInfo"
DUMMYIP = "255.255.254.0"
