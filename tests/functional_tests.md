svk cxl functional testing (mutable and immutable functions) 

  Mutable functions: 
  1. DetachMemory - remove attached memory device from host. 
  2. AttachMemory - attach memory device to host.

  Immutable functions: 
  1. SetupInfo - provide complete memory box setup inforamtion including devices, hosts and their connections. 
  2. ListDevices - list out the device details. 
  3. ListHosts - list out the host details.
   

################################
# Steps for Functional testing #
################################

Step1: execute the below services 

  1. controller service  
     
     option1: systemctl start svk-controller
              systemctl status svk-controller
      
     option2: if system controller command doesnt work - 
              /usr/local/svk/mgmt-fw/bin/svkgrpccontroller  --svk_conf_file /etc/svk/controller.json

  2. Node service 

     option1: systemctl start svk-node
              systemctl status svk-node
     
     option2:
              /usr/local/svk/mgmt-fw/bin/svkgrpcnode  --svk_conf_file /etc/svk/node_agent.json

  3. Rest service  

     option1: systemctl start svk-restserver
              systemctl status svk-restserver

     option2:
              /usr/local/svk/mgmt-fw/rest_api/svk_rest_server --config-file /etc/svk/rest_server.json


Step2: Issue curl commands 


Immutable functions:

1. ListDevices:
   
   curl -X 'POST' 'http://105.128.44.45:8001/api/v1/process_controller_command' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_id": "CL_ID_1","node_id": "localhost","feature_id": "3", "feature_params": "cluster_id=CL_ID_1;command=ListDevices;FM_id=203;FM_endpoint=samsung.com" }'

2. ListHosts:
   
   curl -X 'POST' 'http://105.128.44.45:8001/api/v1/process_controller_command' -H 'accept: application/json' -H 'Content-Type: application/json' -d '{ "cluster_id": "CL_ID_1","node_id": "localhost","feature_id": "3", "feature_params":"cluster_id=CL_ID_1;command=ListHosts" }' 

3. SetupInfo
    
   curl -X 'POST' 'http://105.128.44.45:8001/api/v1/process_controller_command' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_id": "CL_ID_1","node_id": "localhost","feature_id": "3", "feature_params": "cluster_id=CL_ID_1;command=SetupInfo" }'

   

Mutable functions:

1. DetachMemory:

   curl -X 'POST' 'http://105.128.44.45:8001/api/v1/process_controller_command' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_id": "CL_ID_1","node_id": "localhost","feature_id": "3", "feature_params": "cluster_id=CL_ID_1;command=DetachMemory;dev_id=549755813888;host_id=551903297536;mode=direct" }'

   Note: once the response is recieved with rc:0, open input.json file from /usr/local/svk/cxl/lib64/input.json and verify of device is detached from hosts list 


2. AttachMemory:

   curl -X 'POST' 'http://105.128.44.45:8001/api/v1/process_controller_command' -H 'accept:application/json' -H 'Content-Type: application/json' -d '{ "cluster_id": "CL_ID_1","node_id": "localhost","feature_id": "3", "feature_params": "cluster_id=CL_ID_1;command=AttachMemory;dev_id=549755813888;host_id=551903297536;mode=direct" }'


   Note: once the response is recieved with rc:0, open input.json file from /usr/local/svk/cxl/lib64/input.json and verify of device is attached to hosts list 




