# SVK Management Framework

## Description

The SVK Management Framework repository contains code related to REST API Server, gRPC server for the SVK Controller and the Agent nodes, proto files, configuration files and the unit tests.

## Supported build and runtime platforms

- Rockylinux 9
- Ubuntu 22

## Install build dependencies

```bash
./scripts/dependencies/install.sh
```

### SVK Dependencies

The [dependencies install script](#Install-build-dependencies) will configure your build environment to pull packages from [SSG Nexus](http://ssg-nexus.msl.lab:8081).

The following SVK dependencies are installed automatically by the above script, but can be manually updated, if necessary, using your OS's package manager:

- `svk-core`
- `svk-core-dev` (Ubuntu) or `svk-core-devel` (Rockylinux)
- `svk-grpc`
- `svk-go-modules`

### Manual upgrade of SVK Packages

#### Rockylinux

```bash
dnf clean all
dnf install svk-core-devel svk-grpc svk-go-modules  -y
```

#### Ubuntu

```bash
apt-get update
apt-get install svk-core-dev svk-grpc svk-go-modules -y
```

## Building and executing unit tests

- [Install build dependencies](#Install-build-dependencies)
- Execute `./scripts/build.sh` script from the top level directory. The `-h` option will show what options are available for building SVK Management Framework:

```bash
$ ./scripts/build.sh -h
Build script for SVK Management Framework

Syntax: build.sh [-t|c|h|p|r|f]
options:
-t | --build-tests
  Build the unit tests for SVK Framework.
-c | --with-coverage
  Build with code coverage report. Must build unit tests for this.
-h | --help
  Print this help.
-p | --install-prefix
  Install libraries and related files to specified dir.
-r | --release
  Release build. Generates a tarball called svk-mgmt-fw-<version>.tgz by default.
-f | --filename
  Filename prefix to use for release tarball. Only applicable when building with release flag.
-b | --build-package
  Generate SVK Mgmt FW RPMs/DEB packages.
-i | --install-path
  Path that RPMs/DEBs should install mgmt-fw to (Default: /usr/local/svk/mgmt-fw). Only applicable when building with release flag.
```

### Unit Tests and Code Coverage

Execute the following script to build with unit tests, and display code coverage results:

```bash
./scripts/build.sh -t -c
```

### Generate release artifacts

Execute the build script to create a release build and copy the resulting libraries to `/usr/local/svk/mgmt-fw`:

```bash
./scripts/build.sh -r -b -p /usr/local/svk/mgmt-fw
```

The above command generates the artifact `svk-mgmt-fw-<git_tag>.tgz` as well as RPM/DEB packages in the `build` directory.

### Release build & RPMs

* `svk-mgmt-fw`: Runtime version of SVK Management Framework
* `svk-mgmt-fw-dev` (Ubuntu) or `svk-mgmt-fw-devel` (Rockylinux): Development package of SVK Management Framework

By default, installing the RPM/DEB will install files to  `/usr/local/svk/mgmt-fw`. If packages are built with `-i <install_path>` from the build script, then they will be installed to the given `install_path` instead.

## Installation

To install a pre-compiled version of SVK Management Framework and its dependencies, configure your package manager to use the SSG Nexus repo, then install the Management Framework package(s).

### Rockylinux

```bash
curl -fsSL http://ssg-nexus.msl.lab:8081/repository/svk_common/ssg-nexus-$(. /etc/os-release && echo "$ID${VERSION_ID%%.*}").repo -o /etc/yum.repos.d/ssg-nexus.repo
dnf install epel-release -y
dnf install svk-mgmt-fw -y
# Optional - install devel package
dnf install svk-mgmt-fw-devel -y
```

### Ubuntu

```bash
wget --quiet --output-document /usr/share/keyrings/ssg-nexus.pgp  http://ssg-nexus.msl.lab:8081/repository/svk_common/public.pgp
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ssg-nexus.pgp] http://ssg-nexus.msl.lab:8081/repository/svk_apt_ubuntu22 $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ssg-nexus.list
apt update
apt-get install svk-mgmt-fw -y
# Optional - install devel package
apt-get install svk-mgmt-fw-dev -y
```

## Usage

Once `svk-core` and `svk-mgmt-fw` artifacts are installed, the user needs to run the commands in the following manner
- Copy the configuration JSON files to /etc/svk/ directory. Sample config file can be seen at `config/config.json.example`
- The server hosting `controller` should have the **svk_mgmt_fw_controller** section in the JSON configuration file (/etc/svk/controller.json)
- The server hosting `node agent` should have the following
    * svk-core rpm/tarball should be installed as the prerequisite
    * **core** section in the JSON configuration file (/etc/svk/core.json). The **feat_modules_dir** should be updated to the proper directory containing feature module's libraries.
    * **svk_mgmt_fw_node** section in the JSON configuration file (/etc/svk/node_agent.json). The `lib_path` in *framework* section of **svk_mgmt_fw_node** should point to the file path of *libsvkframework.so*. The `conf_file` in *framework* section should point to the JSON file having the **core** section
- The server hosting `REST server` should have the **svk_mgmt_rest_api** section in the JSON configuration file(/etc/svk/rest_server.json)

- Depending on the type of server being deployed, the scripts expect the following configuration files 
	```
	For Controller, the file is /etc/svk/controller.json
	For Rest Server, the file is /etc/svk/rest_server.json
	For Node agent, the file is /etc/svk/node_agent.json and /etc/svk/core.json
	```
- Copy the appropriate files from the *systemd_files* directory in the repository to `/etc/systemd/system` and run the command `systemctl daemon-reload`

- Run the controller server on the controller node. Controller runs on the port 9999 by default. It can be run using `systemctl start svk-controller`
- Run the node server on the agent nodes. By default node server runs on port 9998. It can be run using `systemctl start svk-node`
- Run the REST API server on the controller node using the command `systemctl start svk-restserver`. By default, the REST server runs on port 8001.
