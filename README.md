# SVK Management Framework

## Name
SVK Management Framework

## Description
The SVK Management Framework repository contains code related to REST API Server, gRPC server for the Controller and the Agent nodes, proto files, configuration files and the unit tests.

## Installation
- Run the script `scripts/dependencies/install.sh` to install necessary packages.
- The above script compiles the gRPC related packages and installs in the standard library path
- Requires artifacts of svk-core repo installed in the directory /usr/local/svk/core as the prerequiste to start with.
- On Ubuntu OS v22.04, the default `go` package is not sufficient for the project. Need to download go v1.21+ and set the PATH variable accordingly
  ```
  export PATH=$PATH:/usr/local/go/bin
  ```
- Configure the PKG_CONFIG_PATH to point to the package config file
  ```
  export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/lib/pkgconfig/:/usr/local/lib64/pkgconfig/:/usr/local/svk/core/lib64/pkgconfig/:/usr/local/svk/core/lib/pkgconfig/
  ```
  Check the lib path depending on the OS version.

- Requires GCC toolset 11 and source the gcc environment using the command `source /opt/rh/gcc-toolset-11/enable`
- Run the script `sh scripts/build.sh` with the appropriate flags
- To generate the artifact `svk-mgmt-fw-<git_tag>.tgz`, run the build script with `-r` flag

## Testing
- Requires prerequisite packages as mentioned in the Installation section. Some of them are grpc, svk-core, gcc-toolset-11
- Run the script `sh scripts/build.sh` with the flags `-t -c` to run unit tests and code coverage results

## Usage
Once all the svk-core and svk-mgmt-fw artifacts are installed, the user needs to run the commands in the following manner
- Copy the configuration JSON files to /etc/svk/ directory. Sample config file is config/config.json.example. Needs to update the fields as per the deployment.
- Depending on the type of server being deployed, the scripts expect the following configuration files 
	```
	For Controller, the file is /etc/svk/controller.json
	For Rest Server, the file is /etc/svk/rest_server.json
	For Node agent, the file is /etc/svk/node_agent.json
	```
- Copy the appropriate files under systemd_files directory to `/etc/systemd/system` and run the command `systemctl daemon-reload`

- Run the controller server on the controller node. Controller runs on the port 9999 by default. It can be run using `systemctl start svk-controller`
- Run the node server on the agent nodes. By default node server runs on port 9998. It can be run using `systemctl start svk-node`

- Run the REST API server on the controller node using the command `systemctl start svk-restserver`
