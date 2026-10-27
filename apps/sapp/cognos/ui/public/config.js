
window.CONFIGS = {
    "mgmt_endpoint": "http://<frontend_ip>:<frontend_port>",
    "data_endpoint": "http://127.0.0.1:4000",
    "api_endpoint": "http://127.0.0.1:4000/api/v2.0.1",
    "rbac_endpoint": "http://127.0.0.1:6720",
    "download_only_mode": false,
    "rbac_enabled": true,
    "ssl": false,
    "clusterPolicy": "roundRobin", 
    "policyOptions": {
      "roundRobin": {
        "comment": "the use case is that the user wants to have minimum number of application server for redundancy",
        "minHostsPerCluster": 2
      }
    }
}
