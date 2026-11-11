# Cognos Memory Engine

## Description

Cognos Memory Engine is responsible for optimal data movement, it is important to efficiently profile application memory to move appropriate data between faster and slower memory tiers.

### Supported OS List

- Rockylinux 9
- Oracle Linux 10
- Ubuntu 22.04
- Ubuntu 24.04

## Build

me is built and tested with the rest of Cognos, from the repository root: see
[Build](../../README.md#build) (`./build.sh me`, and `./build.sh --test me` for its unit tests).

## AMT 2.0 build, deploy, test

* The application/workload PID , NUMA nodes : slower NUMA node , faster NUMA node are to be furnished by the user prior to execution as mentioned in the below config file.
* Present support is implemented for two tiers [slow NUMA node(CXL, remote memory), fast NUMA node(DRAM)]
* The present imlpementation supports only one version  AMT1.0 or AMT2.0 at one time.
* This means it does not support AMT 1.0 commands (API call) overlapping with AMT 2.0 processing.
* Example:
 - Time t1: AMT 1.0 move()/move_hot()/move_cold() API call triggered with success response.
 - Time t2: AMT 1.0 stop() API call for the corresponding context with success response.
 - Time t3: AMT 2.0 script processing for a PID started.
 - Time t4: AMT 2.0 processing is stopped.
 * Here: t1--t2 time window cannot overlap with t3--t4 time window.

#### AMT 2.0 build
To build the Cognos ME with AMT 2.0 scripts  execute a standard release build after pulling the repo locally:

```bash
./scripts/build.sh -r
```

This will create a .deb/rpm package in the build directory of the form:

*/path/to/cognos/features/me/build/artifacts/ubuntu22/cognos-me_1.4.2-1-ge54a-ubuntu22.04_amd64.deb*

#### AMT 2.0 installation

The above package can be installed like:

```bash
apt install /path/to/cognos/features/me/build/artifacts/ubuntu22/cognos-me_1.4.2-1-ge54a-ubuntu22.04_amd64.deb
```

Alternatively the deb/rpm package can be installed from Nexus

```bash
apt-get install cognos-me
```

* AMT 2.0 can be tested after successful installation. It does not need Cognos node service to be started. Although AMT 2.0 can be used/tested with all Cognos services running. 

Following are the details that can be checked after installation:

```bash
###############################
Installation
###############################

root@host-srf02:/path/to/cognos/features/me# apt install /path/to/cognos/features/me/build/artifacts/ubuntu22/cognos-me_1.4.2-1-ge54a-ubuntu22.04_amd64.deb
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Note, selecting 'cognos-me' instead of '/path/to/cognos/features/me/build/artifacts/ubuntu22/cognos-me_1.4.2-1-ge54a-ubuntu22.04_amd64.deb'
The following packages were automatically installed and are no longer required:
  libdbd-sqlite3-perl libdbi-perl sqlite3
Use 'apt autoremove' to remove them.
The following NEW packages will be installed:
  cognos-me
0 upgraded, 1 newly installed, 0 to remove and 69 not upgraded.
Need to get 0 B/230 kB of archives.
After this operation, 894 kB of additional disk space will be used.
Get:1 /path/to/cognos/features/me/build/artifacts/ubuntu22/cognos-me_1.4.2-1-ge54a-ubuntu22.04_amd64.deb cognos-me amd64 1.4.2-1-ge54a-ubuntu22.04 [230 kB]
Selecting previously unselected package cognos-me.
(Reading database ... 207763 files and directories currently installed.)
Preparing to unpack .../cognos-me_1.4.2-1-ge54a-ubuntu22.04_amd64.deb ...
Unpacking cognos-me (1.4.2-1-ge54a-ubuntu22.04) ...
Setting up cognos-me (1.4.2-1-ge54a-ubuntu22.04) ...
Requirement already satisfied: pip in ./usr/local/svk/venv/me/lib/python3.10/site-packages (26.1.2)
Requirement already satisfied: pyyaml in ./usr/local/svk/venv/me/lib/python3.10/site-packages (from -r /usr/local/svk/feature_modules/me/scripts/dependencies/python/requirements_deploy.txt (line 2)) (6.0.3)
Requirement already satisfied: damo==3.1.0 in ./usr/local/svk/venv/me/lib/python3.10/site-packages (from -r /usr/local/svk/feature_modules/me/scripts/dependencies/python/requirements_deploy.txt (line 3)) (3.1.0)
Requirement already satisfied: psutil in ./usr/local/svk/venv/me/lib/python3.10/site-packages (from -r /usr/local/svk/feature_modules/me/scripts/dependencies/python/requirements_deploy.txt (line 4)) (7.2.2)
Processing triggers for libc-bin (2.35-0ubuntu3.13) ...
Scanning processes...                                                                                                                                                                                                                                                          
Scanning candidates...                                                                                                                                                                                                                                                         
Scanning processor microcode...                                                                                                                                                                                                                                                
Scanning linux images...                                                                                                                                                                                                                                                       

Running kernel seems to be up-to-date.

The processor microcode seems to be up-to-date.

Restarting services...
Service restarts being deferred:
 systemctl restart networkd-dispatcher.service
 systemctl restart unattended-upgrades.service

No containers need to be restarted.

No user sessions are running outdated binaries.

No VM guests are running outdated hypervisor (qemu) binaries on this host.
root@host-srf02:/path/to/cognos/features/me# 

###############################
Check after installation:
###############################

root@host-srf02:/usr/local/svk# tree feature_modules/me
feature_modules/me
├── config
│   ├── cme_config.json
│   ├── damo_config.json
│   └── tm_gen_config.py
├── lib64
│   └── libsvkme.so
├── logic_modules
│   └── movers
│       └── lib64
│           ├── libmover_damo.so
│           └── libnuma_move_all.so
└── scripts
    ├── amt2_scripts
    │   ├── amt2_cleanup.sh
    │   ├── amt2_config.json
    │   ├── memory_monitor.sh
    │   ├── memory_mover_fsr.py
    │   └── memory_profiler.py
    └── dependencies
        └── python
            ├── requirements_deploy_amt_2.txt
            └── requirements_deploy.txt

9 directories, 13 files

###############################
Check amt2 config file:
###############################

Default: 

{
    "target_pid": 1234,
    "monitor_interval_s": 10,
    "max_csv_files": 10,
    "fast_numa_node": 0,
    "slow_numa_node": 2,
    "action": "p",
    "_action_comment": "action can be: p (promote hot to fast), d (demote cold to slow), a (both)",
    "fsr_size_mb": 32,
    "move_interval_s": 20,
    "hot_threshold": 2,
    "warm_threshold": 1,
    "damo_path": "/usr/local/svk/venv/me/amt2/bin/damo"
}

```

#### AMT 2.0 execution and testing:

Once above installation steps are done and verified, following execution/testing steps can be performed:

```bash
###############################
Modify to add PID and numa nodes:
###############################

root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# cat amt2_config.json
{
    "target_pid": 1942458,
    "monitor_interval_s": 10,
    "max_csv_files": 10,
    "fast_numa_node": 0,
    "slow_numa_node": 2,
    "action": "p",
    "_action_comment": "action can be: p (promote hot to fast), d (demote cold to slow), a (both)",
    "fsr_size_mb": 32,
    "move_interval_s": 20,
    "hot_threshold": 2,
    "warm_threshold": 1,
    "damo_path": "/usr/local/svk/venv/me/amt2/bin/damo"
}

```

Explanation of the above config file:

"target_pid": Target workload/application PID

"monitor_interval_s": Interval in seconds of the monitoing the workload hotness periodically.

"max_csv_files": Max number of .csv files generated by the monitoring scripts. These are read by fsr mover script.

"fast_numa_node": Faster numa node, usually DRAM node that workload is bound to.

"slow_numa_node": SLower numa node, usually CXL node that workload is bound to.

"action": promote/demote movement: action can be: p (promote hot to fast), d (demote cold to slow), a (both).

"fsr_size_mb": FSR size: Application VMA is broken down logically to FSR size in MB for movement.

"move_interval_s":  Interval in seconds of the  processing of profiled  region and doing FSR based movement.

"hot_threshold": Access threshold for hot data.

"warm_threshold": Access threshold for warm data.

"damo_path": Path to the 3.1.0 version of the damo tool needed for AMT 2.0.

The above parameters are used by the monitoring and fsr movement scripts. Workload PID and workload pertaining numa node information are to be provided in the config file above.
Remainder of the fields can be left to be default values.

For example below is a cachebench workload with PID 1942458 and bound to numa node 0 and 2; with numa node 0 as fast_numa_node and numa node 2 as slow_numa_node:

```bash

###############################
Workload details: PID, numa node bindings
###############################

root@host-srf02:~/poc_cat2/cachebench# numactl --weighted-interleave=0,2  CacheLib/opt/cachelib/bin/cachebench --json_test_config test_dram_cxl_1kb.json --report_api_latency &
[1] 1942458
root@host-srf02:~/poc_cat2/cachebench# ===JSON Config===
{
  "cache_config": {
    "cacheSizeMB": 170536, 
    "htBucketPower": 26,
    "htLockPower": 20,
    "numPools": 1,
    "poolSizes": [1.0]
  },
  "test_config": {
    "populate": false,
    "numOps": 10000000,
    "numThreads": 32,
    "numKeys": 128000000,
    "keySizeRange": [16, 64],
    "keySizeRangeProbability": [1.0],
    "valSizeRange": [1023, 1025],
    "valSizeRangeProbability": [1.0],
    "getRatio": 0.67,
    "setRatio": 0.33,
    "distribution": "zipfian"
  }
}

Welcome to OSS version of cachebench
Created 128,000,000 keys in 4.05 mins
Generating 320.00M sampled accesses
Generated access patterns in 0.00 mins
Total 320.00M ops to be run
18:39:34       0.00M ops completed. Hit Ratio   0.00% (RAM   0.00%, NVM   0.00%)
18:40:34      76.79M ops completed. Hit Ratio  

```

Once the workload is started and the amt2_config.json file is populated with appropriate data, amt2.0 scripts can be started as follows:

For monitoring script:

```bash
cd /usr/local/svk/feature_modules/me/scripts/amt2_scripts
./memory_monitor.sh
```

In another terminal, for FSR movement script:

```bash
cd /usr/local/svk/feature_modules/me/scripts/amt2_scripts
/usr/local/svk/venv/me/amt2/bin/python3 memory_mover_fsr.py
```

Example runs for the above two scripts below:

```bash
###############################
Start amt2 scripts: Need PID, numa node info for workload
###############################

- Monitor script:

root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# ls
amt2_cleanup.sh  amt2_config.json  memory_monitor.sh  memory_mover_fsr.py  memory_profiler.py
root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# ./memory_monitor.sh
DAMON is not turned on
[+] Starting DAMON on Kernel 6.11 for PID 1942458...
[+] Monitoring active. Snapshots every 10s...
[+] Tried_regions found, processing to csv...
[+] Tried_regions found, processing to csv...
[+] Tried_regions found, processing to csv...
[+] Tried_regions found, processing to csv...
[+] Tried_regions found, processing to csv...
.
.
.
[+] Tried_regions found, processing to csv...
DAMON is not turned on
root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# 

- FSR Mover script:

root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# ls
amt2_cleanup.sh  amt2_config.json  memory_monitor.sh  memory_mover_fsr.py  memory_profiler.py  report_1942458
root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts#  /usr/local/svk/venv/me/amt2/bin/python3 memory_mover_fsr.py
--- Movement Report for PID 2095057 ---
FSR size = 32 MB
Movement interval = 20s
In progress: ...
Total PROMOTED: 0.00 MB | Total DEMOTED: 0.00 MB ...
Hot pages detected
Total PROMOTED: 3628.89 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 3628.89 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 3628.89 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 3628.89 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 3628.89 MB | Total DEMOTED: 0.00 MB ...
Hot pages detected

.
.
.
Hot pages detected
Total PROMOTED: 24493.98 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 24493.98 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 24493.98 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 24493.98 MB | Total DEMOTED: 0.00 MB ...
Total PROMOTED: 24493.98 MB | Total DEMOTED: 0.00 MB ...
[-] PID 2095057 does not exist or is not accessible. Exiting.
root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# 

```

The FSR mover script periodically prints the hitherto total promoted data. This can be verfied with *numastat -p PID* command

Both the scripts continue to run as long as the workload PID is active. The scripts can be stopped anytime using Ctrl+c as well.

During the run the scripts generate temporary workload profile data:

```bash
###############################
Check during run:
###############################

root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# ls
amt2_cleanup.sh  amt2_config.json  memory_monitor.sh  memory_mover_fsr.py  memory_profiler.py  report_1942458
root@host-srf02:/usr/local/svk/feature_modules/me/scripts/amt2_scripts# ls report_1942458/
access_map.1783733824.csv  access_map.1783733837.csv  access_map.1783733848.csv  access_map.1783733861.csv  access_map.1783733873.csv  access_map.1783733885.csv

```
