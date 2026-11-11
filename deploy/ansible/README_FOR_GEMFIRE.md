# VMware GemFire + YCSB Benchmarking with Ansible

## Overview

This project provides an end-to-end Ansible automation suite for deploying VMware GemFire clusters and running YCSB (Yahoo! Cloud Serving Benchmark) workloads against them. It covers the full lifecycle:

1. **Environment Setup** — validate dependencies, check ports, install Java, start GemFire locators and servers, create regions, and prepare YCSB clients
2. **Data Load** — generate YCSB configuration and load initial data
3. **Workload** — run YCSB benchmarks with configurable read/write/update mix, collect system metrics, and parse results
4. **Cleanup** — stop all services cleanly

## Supported Platforms

| Distribution | Version |
|---|---|
| Ubuntu | 22.04, 24.04 |
| OracleLinux | 9.6, 10.1 |

## Prerequisites

### Hardware

* gemfire_server:
  * Equipped with **NVMe disks** to store data of gemfire server
  * **100GbE NICs**. NICs should be evenly distributed across each CPU socket.
  * **CXL devices**. CXL devices should be evenly distributed across each CPU socket.

* gemfire_locators:
  * **100GbE NICs**. NICs on locators must be evenly distributed across each CPU socket, and must have network connectivity with the corresponding GemFire servers.

### Artifacts

* Please contact the responsible person and obtain the GemFire-related packages from the local MSL server.

```
# tree -L 2 artifacts/
artifacts/
├── gf_metrics_collect_scripts.tar.gz
├── hmsdk.tar.gz
├── numactl-2.0.19.tar.gz
├── vmware-gemfire-10.1.3.tar
└── ycsb-geode-binding-0.18.0-SNAPSHOT.tar.gz

0 directories, 6 files
```

## Gemfire Project Structure

```
svk-ansible-gemfire/
├── ansible.cfg                  # Ansible runtime configuration
├── gemfire_hosts                # Inventory for GemFire + YCSB benchmark
├── ansible.cfg                  # Ansible runtime configuration
├── collections/
│   └── requirements.yml         # Ansible Galaxy collections
├── group_vars/
│   ├── benchmark_all.yml        # GemFire + YCSB benchmark variables (main config)
├── host_vars/
│   ├── gemfire1.yml             # Per-host NIC interfaces and NVMe disks
│   ├── gemfire2.yml             # Per-host NIC interfaces and NVMe disks
│   ├── gemfire3.yml             # Per-host NIC interfaces and NVMe disks
│   └── locator1.yml             # Locator-specific variables
├── playbooks/
│   ├── setup_gemfire.yml        # Deploy and start GemFire cluster + YCSB client prep
│   ├── run_ycsb_dataload.yml    # Generate config and load initial dataset
│   ├── run_ycsb_workload.yml    # Run YCSB workloads with metrics collection
│   └── cleanup_gemfire.yml      # Stop YCSB clients, GemFire servers and locators
├── roles/
│   # --- GemFire roles ---
│   ├── validate_ansible          # Validate Ansible version and dependencies
│   ├── validate_os               # Validate OS distribution and version
│   ├── validate_kernel           # Validate kernel version
│   ├── gf_check_deps             # Check prerequisites for GemFire server/locator
│   ├── gf_check_ports            # Check port availability for locators and servers
│   ├── gf_install_java           # Install Java 21 JDK
│   ├── gf_install_numactl        # Install numactl
│   ├── gf_get_numa_ids           # Detect NUMA topology
│   ├── gf_nic_status             # Check NIC status
│   ├── gf_locator_start          # Start GemFire locator instances
│   ├── gf_locator_stop           # Stop GemFire locator instances
│   ├── gf_server_start           # Start GemFire server instances
│   ├── gf_server_stop            # Stop GemFire server instances
│   ├── gf_member_stat            # Get GemFire member/region status
│   # --- YCSB roles ---
│   ├── ycsb_check_deps           # Check prerequisites for YCSB client
│   ├── ycsb_install_py27         # Install Python 2.7
│   ├── ycsb_config_set           # Generate YCSB configuration files
│   ├── ycsb_damon_check          # Check DAMON configuration
│   ├── ycsb_dataload_run         # Run YCSB data load
│   ├── ycsb_workload_config_generate  # Generate YCSB workload config
│   ├── ycsb_workload_run         # Run YCSB workload
│   ├── ycsb_ssh_connect          # Setup SSH between YCSB client and GemFire servers
│   ├── ycsb_pcm_install          # Install Intel PCM on Ubuntu/Debian
│   └── ycsb_client_stop          # Stop YCSB clients
└── artifacts/                    # Put gemfire related pacakges under artifacts directory
```

## Inventory

The inventory file is `gemfire_hosts`. It defines five groups:

```ini
[gemfire_server]
gemfire1 ansible_host=<hostname/host_ip> server_ports=40404 damo_config="damo-default-config-node0-2.yaml"
gemfire2 ansible_host=<hostname/host_ip> server_ports=40404 damo_config="damo-default-config-node0-2.yaml"
gemfire3 ansible_host=<hostname/host_ip> server_ports=40404 damo_config="damo-default-config-node0-2.yaml"

[gemfire_locator]
locator1 ansible_host=<hostname/host_ip> locator_port=10334

[ycsb_client]
hostname5/host_ip5

[benchmark_all:children]
gemfire_server
gemfire_locator
ycsb_client

[all:vars]
ansible_user=<user name>
ansible_password={{ vault_ansible_password }}
```

- **gemfire_server** — hosts running GemFire server instances (default: 3 hosts)
- **gemfire_locator** — hosts running GemFire locator instances (default: 1 host)
- **ycsb_client** — hosts running YCSB benchmark clients
- **benchmark_all** — aggregate group containing all three groups above
- **all:vars** — shared connection variables; the password is encrypted via Ansible Vault

## Variable Configuration

### Primary Variables: `group_vars/benchmark_all.yml`

This file is the central configuration for the entire GemFire + YCSB benchmark workflow. Key sections:

#### Java and GemFire Version

| Variable | Default | Description |
|---|---|---|
| `gf_java_ver` | `21` | Java major version |
| `gemfire_ver` | `10.1.3` | VMware GemFire version |
| `gf_ycsb_ver` | `0.18.0` | YCSB version |

#### GemFire Locator Configuration

| Variable | Default | Description |
|---|---|---|
| `gf_locator_num_per_host` | `4` | Number of locator instances per host |
| `gf_locator_xms` | `10G` | Locator heap start size |
| `gf_locator_xmx` | `10G` | Locator heap max size |
| `gf_locator_xmn` | `2G` | Locator young generation size |
| `gf_locator_xss` | `512K` | Locator stack size |
| `locator_port` | `10334` | Locator communication port |
| `zgc_enable` | `false` | Enable ZGC (Z Garbage Collector) |

#### GemFire Server Configuration

| Variable | Default | Description |
|---|---|---|
| `gfs_num_each_host` | `4` | Server instances per host |
| `gf_server_host_num` | `3` | Number of hosts running servers |
| `gf_server_total_num` | `12` | Total server instances |
| `server_port_base` | `40404` | Base port for server instances |
| `gfs_server_xmn` | `2G` | Server young generation size |
| `gfs_server_xss` | `512K` | Server stack size |
| `gfs_data_size_gb` | `10` | Data size per server (G) for heap calc |
| `gfs_async_enable` | `false` | Async disk-synchronous mode |
| `gfs_ratio` | `1:1` | DRAM:CXL ratio |
| `cxl_num` | `1` | CXL devices per server |
| `persistency_enable` | `true` | Enable disk persistence |
| `persistency` | `true` | Persistent region config |
| `redundancy` | `0` | Region redundancy count (0 = no redundancy) |
| `asynch` | `true` | Asynchronous writes |
| `enable_statistics` | `false` | Enable GemFire statistics |
| `region_count` | `1` | Number of regions to create |

#### YCSB Data Load Parameters

| Variable | Default | Description |
|---|---|---|
| `dataload_parameter.dataset_GB` | `10` | Dataset size in GB |
| `dataload_parameter.concurrency.clients` | `10` | YCSB client count |
| `dataload_parameter.concurrency.threads` | `10` | Threads per client |
| `config_type_key` | `random` | Distribution type: `default`, `hotspot`, `random`, `hotspot_constant`, `hotspot_uniform`, `zipfian_uniform` |

#### YCSB Workload Parameters

| Variable | Default | Description |
|---|---|---|
| `workload_parameter.iteration_count` | `5` | Number of benchmark iterations |
| `workload_parameter.results_directory` | `test` | Output directory name |
| `workload_config_file_parameter.readproportion` | `0.66` | Read operation ratio |
| `workload_config_file_parameter.insertProportion` | `0` | Insert operation ratio |
| `workload_config_file_parameter.updateProportion` | `0.34` | Update operation ratio |
| `workload_config_file_parameter.locatorAddress` | `127.0.0.1` | Locator connection address |
| `workload_config_file_parameter.dataset` | `10G` | Workload dataset size |
| `workload_config_file_parameter.concurrency.clients` | `20` | Client count for workload |
| `workload_config_file_parameter.concurrency.threads` | `10` | Threads per client |
| `workload_config_file_parameter.typeofRun` | `dramcxl` | Run type: `dramcxl` or `dram` |
| `svk_enable` | `nosvk` | Environment: `svk` or `nosvk` |
| `config_type_key_workload` | `hotspot` | Workload distribution type |

#### Metrics Collection

| Variable | Default | Description |
|---|---|---|
| `metrics_enable` | `true` | Enable metrics collection |
| `collect_multi_node` | `true` | Collect from all nodes |

Metrics can be configured per phase (pre-iteration, during iteration, post-iteration, all iterations). Each phase supports:
- `dstat`, `sensor`, `device_temperature`, `dmesg`, `numastat`, `vmstat`, `top`, `cpu_metrics_mpstat`, `power_consumption`, `trigger_PCM`, `disk_usage`, `numactl`, `damo`

#### Log Parsing and Dashboard

| Variable | Default | Description |
|---|---|---|
| `ycsb_logs_parser_enable` | `true` | Enable log parsing |
| `ycsb_logs_parser_skiptimeout` | `false` | Skip timeout entries |
| `ycsb_logs_upload_to_dashboard_enable` | `false` | Upload to dashboard DB, disable this option unless you have a Grafana dashboard to display the workload results.  |
| `dashboard_db_info.host` | <grafana_database_ip> | Grafana Dashboard database host |
| `dashboard_db_info.port` |  <grafana_database_port> | Dashboard database port |
| `dashboard_db_info.db` |  <grafana_database_name> | Dashboard database name |

### Host-Specific Variables: `host_vars/`

Each host in the inventory can have its own variables file. Key per-host variables:

- **`gf_nvme_disks`** — list of NVMe disk devices and their mount points, e.g.:
  ```yaml
  gf_nvme_disks:
    - dev: "/dev/nvme3n1"
      mount_point: "/mnt/gemfire1"
    - dev: "/dev/nvme4n1"
      mount_point: "/mnt/gemfire2"
  ```

- **`gf_nic_interfaces`** — list of NIC interfaces and their IP addresses, e.g.:
  ```yaml
  gf_nic_interfaces:
    - interface: "ens514f0np0"
      ip: "201.0.0.14"
    - interface: "ens514f1np1"
      ip: "202.0.0.14"
    - interface: "ens1282f0np0"
      ip: "203.0.0.14"
    - interface: "ens1282f1np1"
      ip: "204.0.0.14"
  ```

Example host files:

| File | Role | Example IPs |
|---|---|---|
| `host_vars/gemfire1.yml` | GemFire server 1 | 201.0.0.13–204.0.0.13 |
| `host_vars/gemfire2.yml` | GemFire server 2 | 201.0.0.14–204.0.0.14 |
| `host_vars/gemfire3.yml` | GemFire server 3 | 201.0.0.15–204.0.0.15 |
| `host_vars/locator1.yml` | GemFire locator 1 | 201.0.0.34–204.0.0.34 |

## Playbooks

### 1. `setup_gemfire.yml` — Deploy and Start GemFire Cluster

Executes a multi-phase deployment:

| Phase | Hosts | Description |
|---|---|---|
| Validate Ansible | `localhost` | Check Ansible version and Python dependencies |
| Check Locator Ports | `gemfire_locator` | Verify `locator_port` is available on each locator |
| Check Server Ports | `gemfire_server` | Verify `server_port_base` through `server_port_base + gfs_num_each_host - 1` are available |
| Check Dependencies | `gemfire_server`, `gemfire_locator` | Validate OS version, kernel, Java, cgroup, and other prerequisites |
| Start Locators | `gemfire_locator` | Generate and execute locator start scripts; auto-detects if locators are already running |
| Start Servers | `gemfire_server` | Generates `start_<hostname>.sh` with NUMA/CXL/DNUM binding, starts server instances, validates all servers reach `Ready` state |
| Create Regions | *(via server role)* | Creates GemFire regions based on `region_count`, `persistency`, `redundancy` settings |
| Add to cgroup | `gemfire_server` | Places all server processes into the cgroup controller |
| Prepare YCSB Client | `ycsb_client` | Checks YCSB client prerequisites (Java, Python, packages) |

**What it does internally:**

1. **Port checks** — uses `ss -tuln` to verify no service is listening on the target ports before starting
2. **Locator startup** — generates `start_<hostname>.sh` and `check_gf_status_<hostname>.sh` templates, starts locators, and collects status back to the control node
3. **Server startup** — performs complex resource allocation:
   - Validates CXL device count meets `gfs_num_each_host * cxl_num`
   - Maps each server process to a NUMA socket (round-robin)
   - Assigns NVMe disks, NIC IPs, DRAM ranges, CXL devices, and CPU chunks per process
   - Calculates heap size from `gfs_data_size_gb`
   - Generates `cache.xml` with region, persistency, and redundancy configuration
   - Verifies all servers report `Ready` via `gf_member_stat`
4. **Region creation** — checks if `usertable1` already exists; if not, runs `create_region.sh` generated from templates

### 2. `run_ycsb_dataload.yml` — Generate Config and Load Data

Prepares the YCSB client and loads the initial dataset.

| Phase | Hosts | Description |
|---|---|---|
| Generate Config | `ycsb_client` | Creates YCSB configuration from `benchmark_all.yml` settings (distribution type, record count, region count, etc.) |
| Run Data Load | `ycsb_client` | Executes the data load script against the running GemFire cluster |

**Data load behavior:**

- Reads the locator info file generated during setup to connect to the cluster
- Automatically calculates `operation_cnt` and `record_cnt` from `dataset_GB`, `region_count`, and client count
- The concurrency parameters (`clients`, `threads`) control parallelism
- Results are written to `{{ gf_installed_base_dir }}/ycsb_benchmarks/results/`

### 3. `run_ycsb_workload.yml` — Run YCSB Workloads

Executes benchmark iterations with optional metrics collection.

| Phase | Hosts | Description |
|---|---|---|
| Install Intel PCM | `gemfire_server` | Installs Intel PCM for power/energy monitoring (Ubuntu/Debian only) |
| Check DAMON Config | `gemfire_server` | Verifies DAMON (Data Access Monitor) configuration |
| Generate Workload Config | `ycsb_client` | Creates workload config files based on `config_type_key_workload` and `workload_config_file_parameter` |
| Setup SSH | `ycsb_client`, `gemfire_server` | Configures SSH trust between YCSB client and all GemFire server nodes |
| Run Workload | `ycsb_client` | Executes YCSB workload iterations with metrics collection |

**Workload details:**

- Runs `iteration_count` iterations (default: 5)
- Each iteration uses the operation mix defined by `readproportion`, `insertProportion`, and `updateProportion`
- Supports multiple distribution types: `default` (zipfian), `hotspot`, `random`, `hotspot_constant`, `hotspot_uniform`, `zipfian_uniform`
- Metrics are collected at four phases:
  - **Pre-iteration** — before the first iteration (NUMA, power, disk, PCM, DAMON)
  - **During iteration** — live CPU (`mpstat`) and power consumption
  - **Post-iteration** — DAMO, NUMASTAT, CPU, power, NUMACTL, disk usage
  - **All iterations** — dstat, sensor, device temperature, dmesg, NUMASTAT, vmstat, top
- Optional log parsing via `ycsb-logs-parser.sh` and results generation via `ycsb-results-generator.sh`.
- Optional upload to MySQL dashboard database, the default is false.

### 4. `cleanup_gemfire.yml` — Stop All Services

Gracefully stops all components in reverse order:

| Phase | Hosts | Description |
|---|---|---|
| Stop YCSB Clients | `ycsb_client` | Stops YCSB client processes |
| Stop GemFire Servers | `gemfire_server` | Stops all GemFire server instances |
| Stop GemFire Locators | `gemfire_locator` | Stops all locator instances |

## Usage Examples

### Setup GemFire Cluster Only

```bash
cd svk-ansible-gemfire_oel10

# Edit the inventory file `gemfire_hosts`

# Edit the **gf_nvme_disks** and **gf_nic_interfaces** info under **host_vars** of each host defined in `gemfire_hosts`

# Edit the variables defined in `group_vars/benchmark_all.yml`

# Run the setup playbook
ansible-playbook -i gemfire_hosts playbooks/setup_gemfire.yml --ask-vault-pass

```

### Run Data Load

```bash
ansible-playbook -i gemfire_hosts playbooks/run_ycsb_dataload.yml --ask-vault-pass
```

### Run Workload

```bash
ansible-playbook -i gemfire_hosts playbooks/run_ycsb_workload.yml --ask-vault-pass
```

### Cleanup

```bash
ansible-playbook -i gemfire_hosts playbooks/cleanup_gemfire.yml --ask-vault-pass
```

## Key Paths

| Purpose | Path |
|---|---|
| GemFire installation base | `/root` |
| GemFire home | `/root/vmware-gemfire-{{ gemfire_ver }}` |
| YCSB benchmarks | `/root/ycsb_benchmarks/` |
| Benchmark results | `/root/ycsb_benchmarks/results/` |
| Workload configs | `/root/ycsb_benchmarks/workload-config/` |
| Cache XML | `/root/ycsb_benchmarks/cache.xml` |
| Locator info file | `/tmp/gf_check_stat/gf_locators.info` |
| Region info file | `/tmp/gf_check_stat/gf_regions.info` |
| Generated scripts | `/root/ycsb_benchmarks/` |
| Collected artifacts | `{{ inventory_dir }}/artifacts/` |
| Collected logs | `{{ inventory_dir }}/logs/` |

## Ansible Runtime Configuration (`ansible.cfg`)

| Setting | Value | Description |
|---|---|---|
| `inventory` | `hosts` | Default inventory file |
| `roles_path` | `roles` | Local roles directory |
| `forks` | `12` | Maximum parallel forks |
| `retry_files_enabled` | `false` | Do not save retry files on failure |
| `any_errors_fatal` | `true` | Treat any task failure as fatal |
| `host_key_checking` | `false` | Skip SSH host key verification |
| `timeout` | `20` | SSH/connection timeout in seconds |

> **Note:** `inventory = hosts` in `ansible.cfg` is the default, but the GemFire playbooks should be invoked with `-i gemfire_hosts` to use the correct inventory.

## Customization

### Adjusting Heap Sizes

Heap sizes are automatically calculated based on `gfs_data_size_gb`:

```yaml
# In group_vars/benchmark_all.yml:
gfs_data_size_gb: 10   # Adjust to your dataset size

# The formula used in gf_server_start role:
# gfs_server_xms = (gfs_data_size_gb * 3 / gfs_num_each_host) + 'G'
# gfs_server_xmx = (gfs_data_size_gb * 3 / gfs_num_each_host) + 'G'
```

### Changing Region Configuration

```yaml
# In group_vars/benchmark_all.yml:
region_count: 1        # Number of regions to create
persistency: true      # Disk persistence
redundancy: 0          # 0 = no redundancy; set to 1 for enable redundancy
asynch: true           # Asynchronous writes
enable_statistics: false
```

### Enabling ZGC

```yaml
# In group_vars/benchmark_all.yml:
zgc_enable: true
# This adds -XX:+UseZGC to locator JVM options
```

### Adjusting Metrics Collection

To disable all metrics:

```yaml
# In group_vars/benchmark_all.yml:
metrics_enable: false
```

To customize per-phase metrics, modify the `ycsb_metrics_*` dictionaries in `benchmark_all.yml`:

```yaml
ycsb_metrics_all_iterations:
  metrics:
    dstat: "on"
    sensor: "on"
    device_temperature: "off"   # disable device temperature
    dmesg: "on"
    numastat: "on"
    vmstat: "on"
    top: "on"
```

## Notes

- The playbooks use `any_errors_fatal = true`, so any single task failure will abort the entire run. This is intentional for benchmark reproducibility.
- The `become: true` directive is used throughout; ensure the `ansible_user` has sudo privileges without password, or configure `ansible_become_method` appropriately.
- The `ansible_password` is expected to be encrypted via Ansible Vault. If using SSH keys, remove or comment out `ansible_password` and ensure key-based auth is configured.
- The GemFire server role performs complex NUMA/CXL-aware process placement. Ensure the target hardware topology matches the expected configuration before running.
- YCSB requires Python 2.7 on the client node, which is installed automatically by the `ycsb_install_py27` role.
