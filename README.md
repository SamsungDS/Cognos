# Cognos Ansible README.md

## Overview

Ansible automation for configuration, deployment and orchestration of Cognos software.

### Cognos Cluster Considerations

Presently, Cognos is supported and tested on Ubuntu 22.04 and OEL 10.

It is not possible to deploy to other Linux distributions at this time.

## Prerequisite

### I. Add an Ansible User

A user should be provisioned on all hosts in the cluster with "NOPASSWD" sudo access.
Ansible will use this account for all automated configuration.
The default user is "ansible", and you can change the default user in inventory file.

#### Steps for create an ansible user on each cognos node and ansible controller node

* Login the system with 'root' or other account has permissions to create user.
* Create an **ansible** user, assuming that username is ansible

        useradd -m -d /custom/path -s /bin/bash ansible

  **Note**:
  * It is recommended to set the **/custom/path** to **/home/{username}** to ensure proper ownership, access control, and consistency with standard user directory practices.
  * If using a custom path outside **/home/{username}**, make sure the **ansible** user or their group has appropriate permissions on the parent directory.
    * For instance, if '/custom/path' is set to '/root/ansible', ensure the ansible user has the necessary permissions for the '/root' directory.

* Set password for the created user

        passwd ansible

* Set NOPASSWD privileges for **ansible** user

    For cognos nodes

        visudo -f /etc/sudoers.d/ansible
        ansible ALL=(ALL) NOPASSWD: /bin/sh,/usr/bin/python,/usr/bin/python3

    For ansible controller node

        visudo -f /etc/sudoers.d/ansible
        ansible ALL=(ALL) NOPASSWD: /bin/sh,/usr/bin/python,/usr/bin/python3,/usr/bin/dnf install python3-pip

* Repeat the above steps to created an ansible user on each machine

### II. Ansible Controller Setup

On a linux host, on the same management network as all hosts in the Cognos cluster, install the version of ansible-core version is >= 2.16.6 and <= 2.18.4,  _**preferably 2.17.4**_.

And installed Python version is larger than or equal to 3.10.12.

The above dependencies will be validated on runtime, and if not met, will fail assertion, preventing Ansible playbook execution.

To install python & ansible, use the following commands (example for OEL10) with **ansible** user:

```
sudo dnf install python3-pip

sudo python3 -m pip install --upgrade pip

sudo python3 -m pip install ansible-core==2.17.4

ansible-galaxy collection install community.general

ansible-galaxy collection install ansible.posix

# Before running the internal create_ansible_user.yml playbook, ensure that python3-passlib is installed.
sudo dnf install python3-passlib 
```

### III. Prepare Inventory File

Prior to creating your inventory file for your cluster, it is necessary to have some understanding of Ansible inventory file creation, as well as Ansible variables.

Please reference the official documentation:

<https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html>

<https://docs.ansible.com/ansible/latest/user_guide/playbooks_variables.html>

#### Example Inventory File

The example inventory file is located at `$project_dir/hosts`.

Below is an example inventory file defining a cluster with one host in the `[kernel_upgrade_node]` group, one in the `[management_server]` group, and two hosts in the `[application_server]` group.

Specified the user and password (use ansible-vault to store password) for cognos deployment in `[all:vars]`.

        [kernel_upgrade_node]
        hostname1/host_ip1

        [management_server]
        hostname2/host_ip2

        [application_server]
        hostname3/host_ip3
        hostname4/host_ip4

        [all:vars]
        ansible_user=<user name>
        ansible_password={{ vault_ansible_password }}

#### Inventory Groups illustration

Your inventory file should contain hosts in the following groups:

* [kernel_upgrade_node]
  * Hosts for conducting the kernel upgrade, the default is upgrade kernel to version 6.11.0.
  * kernel upgrading will be done on hosts which available capacity >= 29G and current kernel version != 6.11.0, and hosts that do not meet the conditions will be ignored.
  * **Note:** kernel upgrade module is `only support to Ubuntu` now.

* [management_server]
  * Hosts running the cognos-management side services, including the following packages:
    * cognos-app
    * cognos-core
    * cognos-mgmt-fw

* [applicaition_server]
  * Hosts running the cognos-application side services, including the following packages:
    * cognos-core
    * cognos-cxl/cognos-cxl-mock
    * cognos-me
    * cognos-mgmt-fw
    * cognos-node
    * cognos-ras
    * cognos-slat
  
  **Note:**  The `cognos-cxl-mock` is installed only when `scmc_cxl_mock_enable` is set to `true`, under the condition that the application server is equipped with **CMMB**.

### IV. <a id="encrypt_pass">Encrypt ansible password with ansible-vault on ansible controller node</a>

1. Enter $project_dir

        cd ./svk-ansible

2. Create a **passwords.yml** to store ansible password by ansible-vault

        ansible-vault create group_vars/all/passwords.yml

    **Note:** User need to set a vault password (enter twice) for encrypt `group_vars/all/passwords.yml`.

3. Enter the following content in **group_vars/all/passwords.yml**, and save it.

        ---
        vault_ansible_password: '<your_ansible_password>'

    **Note:** '<your_ansible_password>' is the password for the 'ansible_user' specified in the 'hosts' inventory file.

### V. <a id="prepare_artifacts">Prepare the artifacts</a>

The cognos packages to be installed should be placed in the artifacts directory in advance.

1. Enter $project_dir and create a directory named artifacts.
    * cd ./svk-ansible
    * mkdir artifacts
2. Download the cognos packages into artifacts directory.
3. Enter artifacts directory.
    * cd ./artifacts
4. Extract the packages, and packages in artifacts are listed as follows:
    * tar xvf cognos_runner_mvp1.3.tar.gz
    * tree -L 2 artifacts/

            artifacts/
            └── SVK
                ├── cognos-app-<version>-1.el10.ol10.1.x86_64.rpm
                ├── cognos-core-<version>-1.el10.ol10.1.x86_64.rpm
                ├── cognos-cxl-<version>-1.el10.ol10.1.x86_64.rpm
                ├── cognos-me-<version>-1.el10.ol10.1.x86_64.rpm
                ├── cognos-mgmt-fw-<version>-1.el10.ol10.1.x86_64.rpm
                ├── cognos-node-<version>-1.el10.ol10.1.x86_64.rpm
                ├── cognos-ras-<version>-1.el10.ol10.1.x86_64.rpm
                └── cognos-slat-<version>-1.el10.ol10.1.x86_64.rpm

## Deploy Cognos Software Stack (Quick-Start)
  
### Upgrade Kernel (only for Ubuntu)

Perform the kernel upgrade and default to upgrading to version 6.11.0:
  
    ansible-playbook -i your_inventory playbooks/deploy_kernel.yml

### Deploy Cognos

1. [Download cognos release bundle to `artifacts` directory and extract it](#prepare_artifacts).

2. Edit `[management_server]` and `[application_server]` groups in `hosts` inventory file.

3. Edit **ansible_user** in `hosts` inventory file, assuming the username is **ansible**

        [all:vars]
        ansible_user=ansible
        ansible_password={{ vault_ansible_password }}

    **Note:** The `ansible_password` is set to the variable {{ vault_ansible_password }} and will be encrypted in step 4 using ansible-vault.

4. [Encrypt the password of specified ansible_user with ansible-vault](#encrypt_pass).

5. Update variables in `group_vars/all/all.yml`, `group_vars/management_server.yml`, and `group_vars/application_server.yml` as needed.

    **NOTE: No changes are required by default.**

6. Perform the deployment of Cognos to install the required packages and start Cognos services.

        ansible-playbook -i your_inventory playbooks/deploy_cognos.yml --ask-vault-pass

    **Note:** When running a playbook with `--ask-vault-pass`, the user must enter **the vault password** to decrypt the contents of `group_vars/all/passwords.yml`.

7. Configure and start Cognos services.

        ansible-playbook -i your_inventory playbooks/start_cognos.yml --ask-vault-pass

8. Stop Cognos services.

        ansible-playbook -i your_inventory playbooks/stop_cognos.yml --ask-vault-pass

9. Stop Cognos services and remove Cognos related packages.

        ansible-playbook -i your_inventory playbooks/remove_cognos.yml --ask-vault-pass

## Explanation of key variables in `group_vars/all/all.yml`

### scmc_cxl_mock_enable

* Set `scmc_cxl_mock_enable: false` to deploy Cognos in hardware mode. **Hardware mode is enabled by default.**
* Set `scmc_cxl_mock_enable: true` to deploy Cognos in mock mode. **Mock mode is available only for CMMB.**

### cognos_install_gui_enabled

* Set `cognos_install_gui_enabled: false` to deploy Cognos without the SCMC GUI. **This is the default.**
* Set `cognos_install_gui_enabled: true` to deploy Cognos with the SCMC GUI.
  
### cognos_rbac_enabled

* Set `cognos_rbac_enabled: true` to deploy SCMC GUI with RBAC service enabled.

    **NOTE:** This is the default setting and only takes effect when cognos_install_gui_enabled is set to true.
* Set `cognos_rbac_enabled: false` to deploy Cognos SCMC GUI without RBAC service.

### cognos_certificates_enabled

* Set `cognos_certificates_enabled: false` to deploy Cognos in HTTP-only mode. **This is the default.**
* Set `cognos_certificates_enabled: true` to enable HTTPS support with automatically generated self-signed certificates during deployment.

### influxdb_uninstall_flag

* Set `influxdb_uninstall_flag: false` to keep InfluxDB installed. **This is the default.**
* Set `influxdb_uninstall_flag: true`. **Warning:** This will permanently delete all InfluxDB data and uninstall the database.

### cognos_cleanup_enable_log_collection

* Set `cognos_cleanup_enable_log_collection: true` to collect logs when running the remove_cognos.yml playbook.
* Set `cognos_cleanup_enable_log_collection: false` to skip log collection when running the remove_cognos.yml playbook. **The default is false.**

### application_server_type

* The `application_server_type` in `group_vars/all/all.yml` must be set to either **'CMMB'** or **'CMMH'**.
* **The default is 'CMMH'** for application hosts equipped with **CMMD** or **CMMH**.

### management_server_type

* The `management_server_type` in `group_vars/all/all.yml` can be **''**, **'CMMB'** or **'CMMH'**. **The default is ''**.

## Complete Playbook Documentation

### playbooks/deploy_kernel.yml (only for Ubuntu)

Run this playbook to automatically upgrade the kernel on all [kernel_upgrade_node]. The default target is kernel version 6.11.0.

**The hosts used for the kernel upgrade must meet the following requirements:**

* Available capacity of hosts >= 29G
* Current kernel version != 6.11.0

**NOTE:** _hosts that do not meet the conditions will be ignored._

### playbooks/deploy_cognos.yml

Execute this playbook to install required packages and configure and start the necessary services on both the management and application servers.

* **Default installed packages are:**
  * management_server
    * cognos-core
    * cognos-mgmt-fw
  * management_server
    * cognos-core
    * cognos-mgmt-fw
    * cognos-cxl
    * cognos-me
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
- By default, cognos-app is not installed and the frontend services are not started.
- To deploy Cognos with the SCMC GUI, set `cognos_install_gui_enabled: true` before running the `deploy_cognos.yml` playbook, or run `deploy_frontend_cognos.yml` afterward if `deploy_cognos.yml` completes successfully.

### playbooks/start_cognos.yml

Execute this playbook to automatically configure and start all services running on management and application servers

### playbooks/stop_cognos.yml

Execute this playbook to stop all services running on management and application servers

### playbooks/remove_cognos.yml

Execute this playbook to automatically stop all services and remove all Cognos packages on management and application servers

### playbooks/deploy_frontend_cognos.yml

If you've deployed Cognos without GUI enabled and now need to access the Cognos UI, run this playbook.

Execute this playbook to install `cognos-app` package and configure and start the frontend related services on the management server.
* **The frontend related services are:**
    * cognos-subscriber.service
    * cognos-app.service
    * caddy.service
    * cognos-rbac.service

**NOTE:** _It's currently tested on Ubuntu22.04 and OEL10. You may want to keep the influxdb token displayed during execution for later use._

### playbooks/start_frontend_cognos.yml

Execute this playbook to automatically configure and launch the frontend related services on the management server.

### playbooks/stop_frontend_cognos.yml

Execute this playbook to stop the frontend related services on management server.

### playbooks/remove_frontend_cognos.yml

Execute this playbook to automatically stop the `cognos-subscriber.service`,`cognos-app.service`,`caddy.service`,`cognos-rbac.service` and remove `cognos-app` package on management server.

### playbooks/collect_logs_cognos.yml

Run this playbook to automatically gather logs from application and management servers.

**Collected information includes:**

* All files in the /var/log/cognos directory
* dmesg output
* /var/log/messages* (kernel and system journal messages)
* journalctl -u cognos-<node/controller/restserver/app/rbac>.service/caddy.service -b, if the service exists
* journalctl --list-boots (boot history)
* uptime (boot details)
* uname -a (kernel information)
* ps -auxww (running processes)
* lsof (depending on the rpms installed)
* ss -a or netstat -pan (depending on the rpms installed)

### playbooks/create_ansible_user.yml

The playbook is for **internal use only** and is designed to create users. The playbook will perform the following:

* Create ansible user on hosts of [management_server] and [application_server] group
* Set password for the ansible user
* Configure NOPASSWD sudo privileges for the ansible user

**Variables description**:

* Update the variables defined in `roles/create_ansible_user/defaults/main.yml`
  * `create_ansible_user_name`: Defaults to `ansible`, user can specify any other username.
  * `create_ansible_user_password`: Defaults to the vaule of `{{ vault_ansible_password }}`. If not defined, uses `changeme` as the initial password. User can modify it as they want.
  * `create_ansible_user_custom_parent_path`: Defaults to `'root'` because `/home` is a mounted directory on MSL Lab machines. Set this to an alternative path as needed. If set to `''` or `/home`, the user's home directory will be set to `/home/{username}`.

**Usage**:

* ansible-playbook -i your_inventory playbooks/create_ansible_user.yml --ask-vault-pass

    **Note**: The playbook requires the target host to have a `root` account or another account with superuser privileges. Specify the `ansible_user` in the inventory file as `root` or **another account with elevated permissions** before running the playbook.

## Trouble shooting

**Q1**: Error message: To use the 'ssh' connection type with passwords or pkcs11_provider, you must install the sshpass program

* Install **sshpass** on the Ansible controller node.
  
  If using a non-root account, ensure the user has permission to run `dnf install sshpass`.

    For example (assume the non-root user is ansible):

            visudo -f /etc/sudoers.d/ansible
            ansible ALL=(ALL) NOPASSWD: /bin/sh,/usr/bin/python,/usr/bin/python3,/usr/bin/dnf install python3-pip,/usr/bin/dnf install sshpass

**Q2**: Failed to connect to the host via ssh.Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password,keyboard-interactive)

* Conduct `ssh user@host` on terminal, and check the response.

        [user@hostname ~]$ ssh user@hostname
        @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
        @    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
        @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
        IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
        Someone could be eavesdropping on you right now (man-in-the-middle attack)!
        It is also possible that a host key has just been changed.
        The fingerprint for the ED25519 key sent by the remote host is
        SHA256:I09PCHKE6ijrabmZ2pDAfZPgX9V7Xx1MfCNeoa0bOhw.
        Please contact your system administrator.
        Add correct host key in /user_home_path/.ssh/known_hosts to get rid of this message.
        Offending RSA key in KnownHostsCommand-HOSTNAME:3
        Host key for hostname has changed and you have requested strict checking.
        Host key verification failed.

* If an error occurred in the previous step, run the following commands and verify the results.
  
          ssh-keygen -R hostname
          ssh-keyscan -H hostname >> ~/.ssh/known_hosts
        
    If reported **"bash: /user_home_path/.ssh/known_hosts: No such file or directory"** error, please conduct the following commands.

               # Create .ssh directory if it doesn't exist
               mkdir -p ~/.ssh
               # Add the host key to known_hosts
               ssh-keyscan -H hostname >> ~/.ssh/known_hosts

**Q3**: Failed at step **"cognos_rbac_start : Wait up to 120 seconds for rbac api port to become available"**

* This is the final step in the Ansible Cognos deployment. If this step fails, the user can wait longer for the RBAC API port to become available on the management server.
