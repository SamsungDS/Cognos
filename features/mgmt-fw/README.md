# SVK Management Framework

## Description

The SVK Management Framework repository contains code related to REST API Server, gRPC server for the SVK Controller and the Agent nodes, proto files, configuration files and the unit tests.

## Supported OS List

- Rockylinux 9
- Ubuntu 22.04
- Ubuntu 24.04
- Oracle Linux 10

## Build

mgmt-fw is built and tested with the rest of Cognos, from the repository root: see
[Build](../../README.md#build) (`./build.sh mgmt-fw`, and `./build.sh --test mgmt-fw` for its unit tests).

## Usage

Once `cognos-core` and `cognos-mgmt-fw` artifacts are installed, the user needs to run the commands in the following manner

- Edit the JSON configuration file `/etc/svk/mgmt_fw_config.json` depending on the system configuration
- The server hosting `controller` should have the **svk_mgmt_fw_controller** section updated as per the system configuration
- The server hosting `node agent` should have the following
  - cognos-core rpm/deb should be installed as the prerequisite
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

- Run the controller server on the controller node. Controller runs on the port 9999 by default. It can be run using `systemctl start cognos-controller`. This is a prerequisite for the Node Server and the REST API server.
- Run the node server on the agent nodes. By default node server runs on port 9998. It can be run using `systemctl start cognos-node`. Please make sure that the controller is started before starting the node server.
- Run the REST API server on the controller node using the command `systemctl start cognos-restserver`. By default, the REST server runs on port 8001. Please make sure that the controller is started before starting the REST API server.
- Enable the services to start across reboot using the command `systemctl enable cognos-<servertype>`
- Start SVK service manager on controller or node server as `systemctl start cognos-svc-mgr` on RHEL systems or as `service cognos-svc-mgr start` on Debian based systems.
  - Make sure to update feature libs directory (`feat_sm_svcs_dir`) in `svk_mgmt_fw_svc_mgr` section of `/etc/svk/mgmt_fw_config.json`

## REST Server in HTTPS mode

Before starting the REST server, the admin needs to either download the CA Certificate/Key files from the appropriate authority or generate a self signing certificate.

To generate a self signing certificate, follow these steps
- Generate the RSA based Key file
  - openssl genrsa -out key.pem 2048
- Create a Certificate Signing Request (CSR) file
  - openssl req -new -key key.pem -out csr.pem
  - This procedure asks several questions, which are self explanatory, as part of CSR file generation
    - The `Organization` should be the name of the organization hosting the REST server
    - The `Country` should be the country code of the organization hosting the REST server
    - The `State` should be the state of the organization hosting the REST server
    - The `Locality` should be the locality of the organization hosting the REST server
    - The `Organizational Unit` should be the organizational unit of the organization hosting the REST 
    - The `Common Name` should be the hostname of the server hosting the REST server
    - The `Email` should be the email of the organization hosting the REST server
    - The `Challenge Password` should be the password of the organization hosting the REST server
- Create the certificate file
  - openssl x509 -req -days 365 -in csr.pem -signkey key.pem -out cert.pem
- Copy the key.pem and cert.pem files to the `/etc/svk/certificates` directory of the server hosting the REST server.
- Restart the cognos-restserver service

### curl command usage
To run the curl commands with HTTPS mode, there are two options
- With CA certificate
  - curl --cacert /path/to/cert.pem https://<rest_server_ip>:8001/api/v1/clusters/CL_ID_1 -d '{"command_name": "list_nodes_in_cluster"}'
- Bypassing the certificates (**Risky to use, use only for testing purposes, may not work with trusted CA certs**)
  - curl -k  https://<rest_server_ip>:8001/api/v1/clusters/CL_ID_1 -d '{"command_name": "list_nodes_in_cluster"}'

### Updating certificates through REST call
The certificates can be uploaded through REST call which are automatically saved at the default location `/etc/svk/certificates/` directory. Once the upload call is successful, the service `cognos-restserver` needs to be restarted through `systemctl restart cognos-restserver` command to bring up the HTTPS mode.

The cURL command to upload the certificates is
- curl -X POST http://<rest_server_ip>:8001/UpdateCertificate -H 'Content-Type: multipart/form-data' -F 'certificate_pem_file=@/local/path/to/cert.pem' -F 'key_pem_file=@/local/path/to/key.pem'
