# SVK Ansible README.md

## Note: Pending CICD ## 

## Overview

Ansible automation for configuration, deployment and orchestration of SVK software.

### Cognos Cluster Considerations

Presently, SVK is supported and tested on Ubuntu 22.04 and OEL 10.

It is not posible to deploy to other Linux distributions at this time.

### Ansible Host Setup

On a linux host, on the same management network as all hosts in the Cognos cluster, install the version of ansible-core version is >= 2.16.6 and <= 2.18.4,  _**preferably 2.17.14**_.

And installed Python version is larger than or equal to 3.10.12.

The above dependencies will be validated on runtime, and if not met, will fail assertion, preventing Ansible playbook execution.

To install python & ansible, use the following commands (example for Ubuntu):
```
sudo python3 -m pip install --upgrade pip

sudo python3 -m pip install ansible-core==2.17.14

sudo ansible-galaxy collection install community.general
```

### SVK Host Setup

#### Add Ansible User

A user should be provisioned on all hosts in the cluster with "NOPASSWD" sudo access.
Ansible will use this account for all automated configuration.
The default user is "root".

#### Enable SSH access

Ensure the Ansible host can access all hosts in the cluster via SSH.
The SSH service should be started and enabled on all hosts.

#### Generate SSH key

Generate an SSH key on Ansible host, unless already generated.

Example command:

    [root@host ~] ssh-keygen
    Generating public/private rsa key pair.
    Enter file in which to save the key (/home/ylo/.ssh/id_rsa):
    Enter passphrase (empty for no passphrase):
    Enter same passphrase again:
    Your identification has been saved in id_rsa.
    Your public key has been saved in id_rsa.pub.
    The key fingerprint is:
    SHA256:GKW7yzA1J1qkr1Cr9MhUwAbHbF2NrIPEgZXeOUOz3Us root@host
    The key's randomart image is:
    +---[RSA 2048]----+
    |.*++ o.o.        |
    |.+B + oo.        |
    | +++ *+.         |
    | .o.Oo.+E        |
    |    ++B.S.       |
    |   o * =.        |
    |  + = o          |
    | + = = .         |
    |  + o o          |
    +----[SHA256]-----+

#### Copy Public Key for Passwordless SSH Authentication

Copy the SSH public key to each of the hosts using the shh-copy-id command:

    ssh-copy-id root@testhost01.domain.com

To copy keys to 10 hosts automatically, use `sshpass` in a bash loop, for example:

    for i in {01..10}; do sshpass -p "******" ssh-copy-id -o StrictHostKeyChecking=no root@testhost${i}.domain.com; done

#### Validate Passwordless SSH Authentication

To validate that the public key was copied successfully, verify that you can SSH to each host without providing a password, from the Ansible host.

### Prepare Inventory File

Prior to creating your inventory file for your cluster, it is necessary to have some understanding of Ansible inventory file creation, as well as Ansible variables.

Please reference the official documentation:

<https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html>
<https://docs.ansible.com/ansible/latest/user_guide/playbooks_variables.html>

#### Example Inventory File

Set up an Ansible inventory file for the cluster.
Below is an example inventory file defining a cluster with one host in the `[kernel_upgrade_node]` group, one in the `[management_server]` group, and two hosts in the `[application_server]` group.

    [kernel_upgrade_node]
    hostname3/host_ip3

    [management_server]
    hostname4/host_ip4

    [application_server]
    hostname5/host_ip5
    hostname6/host_ip6


#### Inventory Groups

Your inventory file should contain hosts in the following groups:

* [kernel_upgrade_node]
  * Hosts for conducting the kernel upgrade, the default is upgrade kernel to version 6.11.11.
  * kernel upgrading will be done on hosts of slat_node which available capacity >= 29G and current kernel version != 6.11.11, and hosts that do not meet the conditions will be ignored.
  * **Note:** kernel upgrade module is `only support to Ubuntu` now.

* [management_server]
  * Hosts running the cognos-managment side services, including:
    * cognos-app
    * cognos-core
    * cognos-grpc(OEL 10 only)
    * cognos-mgmt-fw

* [applicaition_server]
  * Hosts running the cognos-application side services, including:
    * cognos-core
    * cognos-cxl/cognos-cxl-mock
    * cognos-me
    * cognos-grpc(OEL 10 only)
    * cognos-mgmt-fw
    * cognos-node
    * cognos-ras
    * cognos-slat

### Prepare the artifacts:
The cognos packages to be installed should be placed in the artifacts directory in advance.
1. Enter $project_dir and create a directory named artifacts. 
    * cd ./svk-ansible
    * mkdir artifacts
2. Download the cognos packages into artifacts directory.
3. Enter artifacts directory.
    * cd ./artifacts
4. Extract the packages, and packages in artifacts are listed as follows:
    * tar xvf cognos_runner_mvp9.tar.gz
    * tree -L 2 artifacts/
    *       artifacts/
            └── SVK
                ├── cognos-app-1.1_9-1.el10.ol10.1.x86_64.rpm
                ├── cognos-core-1.1.1-1.el10.ol10.1.x86_64.rpm
                ├── cognos-cxl-1.1.8-1.el10.ol10.1.x86_64.rpm
                ├── cognos-grpc-1.59.2-1.el10.x86_64.rpm
                ├── cognos-me-1.1.0_1_gc82f-1.el10.ol10.1.x86_64.rpm
                ├── cognos-mgmt-fw-1.1.5-1.el10.ol10.1.x86_64.rpm
                ├── cognos-node-1.1.1-1.el10.ol10.1.x86_64.rpm
                ├── cognos-ras-1.1.3-1.el10.ol10.1.x86_64.rpm
                └── cognos-slat-1.1.0-1.el10.ol10.1.x86_64.rpm


## Deploy SVK Software Stack (Quick-Start)
  

### Upgrade Kernel(only for Ubuntu):

Perform the kernel upgrade and default to upgrading to version 6.11.11:
  
    ansible-playbook -i your_inventory playbooks/deploy_kernel.yml

### Deploy Cognos:

1. Download cognos relase bundle to `artifacts` directory and extract it.

2. Edit `[management_server]` and `[application_server]` groups in `hosts` inventory file.

3. Edit the `scmc_cxl_mock_enable` setting in the `group_vars/all.yml`:

    *  Set `scmc_cxl_mock_enable: false` to deploy Cognos in hardware mode.
    *  Set `scmc_cxl_mock_enable: true` to deploy Cognos in mock mode.
    
    If you deploy Cognos in `hardware` mode, the `hosts in [application_server]` must be servers **equipped with** physical CMMB or CMMD/CMMH devices. **Hardware mode is enabled by default.**

4. Edit the `cognos_install_gui_enabled` setting in the `group_vars/all.yml`:

    - Set `cognos_install_gui_enabled: false` to deploy Cognos without the GUI. This is the default.
    - Set `cognos_install_gui_enabled: true` to deploy Cognos with the GUI.

5. Edit the `cognos_certificates_enabled` setting in the `group_vars/all.yml` file:
    
    - Set `cognos_certificates_enabled: false` to deploy Cognos in HTTP-only mode. This is the default configuration.
    - Set `cognos_certificates_enabled: true` to enable HTTPS support with automatically generated self-signed certificates during deployment.

6. Edit the `influxdb_uninstall_flag` setting in the `group_vars/all.yml`:
    
    * Set `influxdb_uninstall_flag: false` to keep InfluxDB installed.
    * Set `influxdb_uninstall_flag: true`. **Warning:** This will permanently delete all InfluxDB data and uninstall the database.

7. Edit the `cognos_cleanup_enable_log_collection` setting in the `group_vars/all.yml`:
    
    - Set `cognos_cleanup_enable_log_collection: true` to collect logs when running the remove_cognos.yml playbook.
    - Set `cognos_cleanup_enable_log_collection: false` to skip log collection when running the remove_cognos.yml playbook. **The default is false.**

8. Update variables in `group_vars/all.yml`, `group_vars/management_server.yml`, and `group_vars/application_server.yml` as needed.

   **No changes are required by default.**

   **NOTE**: 
   - The 'application_server_type' in `group_vars/all.yaml` must be set to either 'CMMB' or 'CMMH'.**The default is 'CMMH'** for application hosts equipped with CMMD or CMMH.
   - The 'management_server_type' in `group_vars/all.yaml` can be '', 'CMMB' or 'CMMH'. The default is ''.


9. Perform the deployment of Cognos to install the required packages and start Cognos services:

        ansible-playbook -i your_inventory playbooks/deploy_cognos.yml

10. Configure and start Cognos services:

        ansible-playbook -i your_inventory playbooks/start_cognos.yml

11. Stop Cognos services:

        ansible-playbook -i your_inventory playbooks/stop_cognos.yml

12. Stop Cognos services and remove Cognos related packages:

        ansible-playbook -i your_inventory playbooks/remove_cognos.yml


### Complete Playbook Documentation

#### playbooks/deploy_kernel.yml (only for Ubuntu)

Execute this playbook to automatically upgrade the kernel accross all [kernel_upgrade_node], and the default is upgrade kernel to version 6.11.11.
 
**Hosts for conducting the kernel upgrade need to meet the following conditions:**
* Available capacity of hosts >= 29G
* Current kernel version != 6.11.11

**NOTE:** _hosts that do not meet the conditions will be ignored._

#### playbooks/deploy_cognos.yml

Execute this playbook to install required packages and configure and start the necessary services on both the management and application servers.

* **Installed packages are:**
    * cognos-core
    * cognos-cxl
    * cognos-me
    * cognos-mgmt-fw
    * cognos-node
    * cognos-ras
    * cognos-slat
* **Service started on management servers:**
    * cognos-controller.service
    * cognos-restserver.service
* **Service started on application servers:**
    * cmmd_driver.service
    * cognos-node.service
    * cognos-svc-mgr.service

**NOTE:** 
    - By default, cognos-app is not installed and frontend services are not started. To deploy Cognos with the GUI, set `cognos_install_gui_enabled: true` before running the `deploy_cognos.yml` playbook.
    - _It's currently tested on Ubuntu22.04 and OEL10. You may want to keep the influxdb token displayed during execution for later use._

At default, It is not install cognos-app and not start frontend servervices.

#### playbooks/start_cognos.yml

Execute this playbook to automatically configure and start all services running on management and application servers

#### playbooks/stop_cognos.yml

Execute this playbook to stop all services running on management and application servers

#### playbooks/remove_cognos.yml

Execute this playbook to automatically stop all services and remove all svk packages on management and application servers

#### playbooks/deploy_frontend_cognos.yml

If you've deployed Cognos without GUI enabled and now need to access the Cognos UI, run this playbook.

Execute this playbook to install `cognos-app` package and configure and start the `cognos-*.service` on the management server.
* **Cognos-*.service services are:**
    * cognos-subscriber.service
    * cognos-app.service
    * cognos-ui.service
    * cognos-rbac.service

**NOTE:** _It's currently tested on Ubuntu22.04 and OEL10. You may want to keep the influxdb token displayed during execution for later use._

#### playbooks/start_frontend_cognos.yml

Execute this playbook to automatically configure and start `cognos-*.service` running on the management server.

#### playbooks/stop_frontend_cognos.yml

Execute this playbook to stop `cognos-*.service` running on management server.

#### playbooks/remove_frontend_cognos.yml

Execute this playbook to automatically stop the `cognos-*.service` and remove cognos-app package on management server.

#### playbooks/collect_logs_cognos.yml

Run this playbook to automatically gather logs from application and management servers.

Collected information includes:
- All files in the /var/log/svk directory
- dmesg output
- /var/log/messages* (kernel and system journal messages)
- journalctl -u svk-<node/controller/restserver/app/rbac>.service -b, if the service exists
- journalctl --list-boots (boot history)
- uptime (boot details)
- uname -a (kernel information)
- ps -auxww (running processes)
