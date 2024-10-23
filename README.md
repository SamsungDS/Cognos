# SVK Management Framework

## Description

The SVK Management Framework repository contains code related to REST API Server, gRPC server for the SVK Controller and the Agent nodes, proto files, configuration files and the unit tests.

## Supported OS List

- Rockylinux 9
- Ubuntu 22.04

## Installation

The prefered method to install SVK Management Framework is through your OS package manager.

SVK Management Framework's CI/CD automatically produces release artifacts which are published to [SSG-Nexus](http://ssg-nexus.msl.lab:8081/), which you can browse from within the SSG lab network.

Release artifacts are also published to the [SVK Management Framework Package Registry on Gitlab](https://cxl-gitlab.ssi.samsung.com/dfs/svk/mgmt-fw/-/packages).

Enable the SSG Nexus repo for your distro, then install the `svk-mgmt-fw` packages via the package manager:

### Ubuntu Installation

```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt update
apt-get install svk-mgmt-fw svk-mgmt-fw-dev -y

```

### Rockylinux Installation

```bash
curl -fsSL http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}").repo -o /etc/yum.repos.d/ssg-nexus.repo
dnf install epel-release -y
dnf install svk-mgmt-fw svk-mgmt-fw-devel -y
```

## Build & Installation

### Build Dependencies

Execute the dependencies installation script to install all build dependencies for your current OS:

```bash
./scripts/dependencies/install.sh
```

### Build SVK Management Framework

[After installing build dependencies](#build-dependencies), execute the `./scripts/build.sh` script. The `-h` option will show what options are available for building SVK Management Framework:

```bash
./scripts/build.sh -h
```

To build SVK Management Framework, run unit tests and generate code coverage reports, execute:

```bash
./scripts/build.sh -t
```

To build and install SVK Management Framework to a specified directory, execute:

```bash
./scripts/build.sh -p install_dir
```

Note: Unless an absolute path is provided, the install path is relative to the `build` dir in the project root.

### Release build

To execute a release build, execute:

```bash
./scripts/build.sh -r
```

This will build and package RPM or Debian Packages (on Rockylinux or Ubuntu, respectively), which are staged in the `build/artifacts` dir in the project root. The packages produced include:

- `svk-mgmt-fw`: Runtime files
- `svk-mgmt-fw-dev(el)`: Development header files

## Usage

Once `svk-core` and `svk-mgmt-fw` artifacts are installed, the user needs to run the commands in the following manner

- Edit the JSON configuration file `/etc/svk/mgmt_fw_config.json` depending on the system configuration
- The server hosting `controller` should have the **svk_mgmt_fw_controller** section updated as per the system configuration
- The server hosting `node agent` should have the following
  - svk-core rpm/deb should be installed as the prerequisite
  - **core** section in the JSON configuration file. The **feat_modules_dir** should be updated to the proper directory containing feature module's libraries.
  - **svk_mgmt_fw_node** section in the JSON configuration file. The `lib_path` in *framework* section should point to the file path of *libsvkframework.so*. The `conf_file` in *framework* section should point to the JSON file path having the **core** section. The controller details need to be updated with the appropriate IP address or host name to which this node connects to.
- The server hosting `REST server` should have the **svk_mgmt_rest_api** section in the JSON configuration file and updated as per the system configuration. The controller details need to be updated with the appropriate IP address or host name to which the REST API Server connects to.

- Depending on the type of server being deployed, the scripts expect the following configuration files

  - Controller:  **svk_mgmt_fw_controller** section in JSON file
  - Rest Server: **svk_mgmt_rest_api** section in JSON file
  - Node agent:
    - **svk_mgmt_fw_node** section in JSON file
    - **core** section in JSON file

- Copy the appropriate files from the *systemd_files* directory in the repository to `/etc/systemd/system` and run the command `systemctl daemon-reload`

- Run the controller server on the controller node. Controller runs on the port 9999 by default. It can be run using `systemctl start svk-controller`. This is a prerequisite for the Node Server and the REST API server.
- Run the node server on the agent nodes. By default node server runs on port 9998. It can be run using `systemctl start svk-node`. Please make sure that the controller is started before starting the node server.
- Run the REST API server on the controller node using the command `systemctl start svk-restserver`. By default, the REST server runs on port 8001. Please make sure that the controller is started before starting the REST API server.
- Enable the services to start across reboot using the command `systemctl enable svk-<servertype>`
- Start SVK service manager on controller or node server as `systemctl start svk-svc-mgr` on RHEL systems or as `service svk-svc-mgr start` on Debian based systems.
  - Make sure to update feature libs directory (`feat_sm_svcs_dir`) in `svk_mgmt_fw_svc_mgr` section of `/etc/svk/mgmt_fw_config.json`
