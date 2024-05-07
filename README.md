# SVK Management Framework

## Name
SVK Management Framework

## Description
The SVK Management Framework repository contains code related to REST API Server, gRPC server for the Controller and the Agent nodes, proto files, configuration files and the unit tests.

## Installation
- Run the script `scripts/dependencies/install.sh` to install necessary packages.
- The above script compiles the gRPC related packages and installs in the standard library path
- Requires artifacts of svk-core repo as the prerequiste to start with.
- Configure the PKG_CONFIG_PATH to point to the package config file
  ```
  export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/local/lib/pkgconfig/:/usr/local/lib64/pkgconfig/:/usr/local/svk/lib64/pkgconfig/
  ```
- Requires GCC toolset 11 and source the gcc environment using the command `source /opt/rh/gcc-toolset-11/enable`
- Run the script `sh scripts/build.sh` with the appropriate flags
- To generate the artifact `svk-mgmt-fw-<git_tag>.tgz`, run the build script with `-r` flag

## Testing
- Requires prerequisite packages as mentioned in the Installation section. Some of them are grpc, svk_framework, gcc-toolset-11
- Run the script `sh scripts/build.sh` with the flags `-t -c` to run unit tests and code coverage results

## Usage
Once all the libraries and binaries are installed, the user needs to run the commands in the following manner
- Edit the /etc/ld.so.conf file to resolve the libraries lookup. Add the line `/usr/local/svk/lib64` to the file and run `ldconfig` command.
<!-- - Run the controller server on the controller node. Controller runs on the port 9999 by default. It can be changed through command line options
	./bin/ctrlr_server & -->
- Run the node server on the agent nodes with the cluster id, framework library path and its node id. By default node server runs on port 9998
	./bin/svkgrpcnode --svk_conf_file config/conf.json &
<!-- - Run the client for validation using. This is a simple test utility to validate the plugin function
	./bin/ctrlr_client --option=command --command "cluster_id=cluster1;command=GetDiskPowerState; disk_id=/dev/nvme0;"
- REST API Server can be started on the controller node with the following commands
	
	export GO111MODULE=on
	cd proxy
	go run cmd/app/main.go -->

