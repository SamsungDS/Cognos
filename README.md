# SVK Ansible README.md

## Note: Pending CICD ## 

## Overview

Ansible automation for configuration, deployment and orchestration of SVK software.

### Cognos Cluster Considerations

Presently, SVK is supported and tested on Ubuntu 22.04 and Ubuntu 24.04.

It is not posible to deploy to other Linux distributions at this time.

### Ansible Host Setup

On a linux host, on the same management network as all hosts in the Cognos cluster, install the version of Ansible version is >= 2.16.6 and <= 2.18.4.

And installed Python version is larger than or equal to 3.10.12.

The above dependencies will be validated on runtime, and if not met, will fail assertion, preventing Ansible playbook execution.

To install python & ansible, use the following commands (on Ubuntu22.04 or Ubuntu24.04):
```
sudo apt update

sudo apt install python3.10

sudo python3.10 -m pip install --upgrade pip

sudo python3.10 -m pip install ansible
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

Configure an Ansible inventory file for the cluster.
Below is an example inventory file defining a cluster of one host in the [slat_node] group, with one also in the [converged_node] group.

    [slat_node]
    hostname1/host_ip1

    [converged_node]
    hostname2/host_ip2

    [kernel_upgrade_node]
    hostname3/host_ip3

    [management_server]
    hostname4/host_ip4

    [application_server]
    hostname5/host_ip5


#### Inventory Groups

Your inventory file should contain hosts in the following groups:

* [slat_node]
  * Hosts running the SLA Tracker related packages,includes:
    * svk-core
    * svk-cxl
    * svk-mgmt-fw
    * svk-slat
* [converged_node]
  * Hosts running converged related packages, includes:
    * svk-converged
    * svk-core

* [kernel_upgrade_node]
  * Hosts for conducting the kernel upgrade, the default is upgrade kernel to version 6.11.11.
  * kernel upgrading will be done on hosts of slat_node which available capacity >= 29G and current kernel version < 6.11.11, and hosts that do not meet the conditions will be ignored.

* [management_server]
  * Hosts running the scmc-managment side services, including:
    * svk-core
    * svk-cxl
    * svk-mgmt-fw
    * svk-app

* [applicaition_server]
  * Hosts running the scmc-application side services, including:
    * svk-core
    * svk-cxl
    * svk-mgmt-fw

### Prepare the artifacts:
The cognos packages to be installed should be placed in the artifacts directory in advance.
1. Enter $project_dir and create a directory named artifacts. 
    * cd ./svk-ansible
    * mkdir artifacts'
2. Download the cognos packages into artifacts directory.
3. Enter artifacts directory.
    * cd./artifacts
4. Extract the packages, and packages in artifacts are listed as follows:
    * tar xvf cognos_runner_mvp3.tar.gz
    * tree -L 3 artifacts/
        *       artifacts
                ├── cognos_runner_mvp5.tar.gz
                └── SVK
                ├── Application_Server
                │   ├── svk-core_0.7.2-ubuntu22.04_amd64.deb
                │   ├── svk-cxl_0.7.1-ubuntu22.04_amd64.deb
                │   └── svk-mgmt-fw_0.7.5-ubuntu22.04_amd64.deb
                ├── Converged
                │   ├── svk-converged_0.7.0-ubuntu24.04_amd64.deb
                │   └── svk-core_0.7.2-ubuntu24.04_amd64.deb
                ├── Management_Server
                │   ├── svk-app_0.7.8-ubuntu22.04_amd64.deb
                │   ├── svk-core_0.7.2-ubuntu22.04_amd64.deb
                │   ├── svk-cxl_0.7.1-ubuntu22.04_amd64.deb
                │   └── svk-mgmt-fw_0.7.5-ubuntu22.04_amd64.deb
                ├── Memory_Engine
                │   ├── svk-core_0.7.2-ubuntu22.04_amd64.deb
                │   ├── svk-me_0.7.0-ubuntu22.04_amd64.deb
                │   └── svk-mgmt-fw_0.7.5-ubuntu22.04_amd64.deb
                ├── Node_Management
                │   ├── svk-core_0.7.2-ubuntu22.04_amd64.deb
                │   └── svk-node_0.7.0-ubuntu22.04_amd64.deb
                └── SLA_Tracker
                    ├── svk-core_0.7.2-ubuntu22.04_amd64.deb
                    ├── svk-cxl_0.7.1-ubuntu22.04_amd64.deb
                    ├── svk-mgmt-fw_0.7.5-ubuntu22.04_amd64.deb
                    └── svk-slat_0.7.0-ubuntu22.04_amd64.deb

                7 directories, 19 files



## Deploy SVK Software Stack (Quick-Start)

### SVK Converged:

Perform the deployment of SVK Converged:
  
    ansible-playbook -i your_inventory playbooks/deploy_cognos_converged.yml

Enable and start SVK Converged service:
  
    ansible-playbook -i your_inventory playbooks/start_cognos_converged.yml

Stop SVK Converged service:
  
    ansible-playbook -i your_inventory playbooks/stop_cognos_converged.yml

Remove or uninstall SVK Converged related packages:
  
    ansible-playbook -i your_inventory playbooks/remove_cognos_converged.yml


### SVK SLA Tracker:

Perform the deployment of SVK SLA Tracker:
  
    ansible-playbook -i your_inventory playbooks/deploy_cognos_slat.yml

Enable and start SVK SLA Tracker:
  
    ansible-playbook -i your_inventory playbooks/start_cognos_slat.yml

Stop SVK SLA Tracker service:
  
    ansible-playbook -i your_inventory playbooks/stop_cognos_slat.yml

Remove or uninstall SVK SLA Tracker related packages:
  
    ansible-playbook -i your_inventory playbooks/remove_cognos_slat.yml
  

### Upgrade Kernel:

Perform the kernel upgrade and default to upgrading to version 6.11.11:
  
    ansible-playbook -i your_inventory playbooks/deploy_kernel.yml

### SVK SCMC:
Perform the deployment of SCMC:

    ansible-playbook -i your_inventory playbooks/deploy_scmc.yml

Configure and start SCMC Tracker:

    Update the values in roles/management_server_start/vars/main.yml & roles/application_server_start/vars/main.yml, then    

    ansible-playbook -i your_inventory playbooks/start_scmc.yml

Stop SCMC service:

    ansible-playbook -i your_inventory playbooks/start_scmc.yml

Remove or uninstall SCMC related packages:

    ansible-playbook -i your_inventory playbooks/remove_scmc.yml


### Complete Playbook Documentation

#### playbooks/deploy_cognos_converged.yml

Execute this playbook to deploy the SVK Converged application accross all [converged_node]

**SVK converged hosts need to meet the following conditions:**
* OS versions == '24.04'
* Kernel version >= 6.8.0
* CPU numbers >= 1
* NVMe devices >= 1
* Host memory >= 64 GB 
    * When host type is 'server', Host memory >= 64GB
    * when host type is 'vm',Host memory >= 4 GB.
    * _All converged nodes are either physical machines or virtual machines._

**NOTE:** _This playbook will terminate if converged_node do not meet the above conditions._

#### playbooks/deploy_cognos_slat.yml

Execute this playbook to deploy the SVK SLA Tracker application accross all [slat_node]

**SVK SLA Tracker hosts need to meet the following conditions:**
* OS versions == '24.04'
* Kernel version == 6.11.11

**NOTE:** _This playbook will terminate if slat_node do not meet the above conditions._

#### playbooks/deploy_kernel.yml

Execute this playbook to automatically upgrade the kernel accross all [kernel_upgrade_node], and the default is upgrade kernel to version 6.11.11.
 
**Hosts for conducting the kernel upgrade need to meet the following conditions:**
* Available capacity of hosts >= 29G
* Current kernel version < 6.11.11

**NOTE:** _hosts that do not meet the conditions will be ignored._


#### playbooks/remove_cognos_converged.yml

Execute this playbook to clean up all installed SVK converged related packages on all [converged_node].

#### playbooks/remove_cognos_slat.yml

Execute this playbook to clean up all installed SVK SLA Tracker related packages on all [slat_node].

#### playbooks/start_cognos_converged.yml

Execute this playbook to automatically configure, enable and start SVK converged service accross all [converged_node].

#### playbooks/start_cognos_slat.yml

Execute this playbook to automatically configure and start SVK SLA Tracker accross all [slat_node].

#### playbooks/stop_cognos_converged.yml

Execute this playbook to automatically stop and disable SVK converged service accross all [converged_node].

#### playbooks/stop_cognos_slat.yml

Execute this playbook to automatically stop SVK SLA Tracker service accross all [slat_node].

#### playbooks/deploy_scmc.yml

Execute this playbooks to install svk-core, svk-mgmt-fw, svk-cxl to management & application servers, and install svk-app to management servers, as well as their dependencies.

**NOTE:** _It's currently tested in Ubuntu22.04. You may want to keep the influxdb token displayed during execution for later use._

#### playbooks/start_scmc.yml

Execute this playbook to automatically configure and start services running on management and application servers

#### playbooks/stop_scmc.yml

Execute this playbook to stop services running on management and application servers

#### playbooks/remove_scmc.yml

Execute this playbook to automatically remove all scmc-related packages on management and application servers
