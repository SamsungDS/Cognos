#ifndef MBOX_A1_H
#define MBOX_A1_H

#include <fcntl.h>
#include <jansson.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <cstdint>
#include <iostream>

#include "sc_servicer.h"

#define MAX_DEVICES 16
#define MAX_HOSTS 5
#define MAX_ENDPOINTS 10
#define MAX_STRING_LEN 30

enum StatusCode {

  MBOX_SUCCESS = 0,
  MBOX_FAIL = 1,
  MBOX_MEM_ALLOC_FAIL = 2,
  MBOX_PING_FAIL = 3,
  MBOX_REBOOT_FAIL = 4,
  MBOX_CMD_EXEC_FAIL = 5,
  MBOX_NULL_POINTER = 6,
  MBOX_FILE_OPEN_FAIL = 7,
  MBOX_FILE_REDIRECT_FAIL = 7,

};

// Structure for devices information
typedef struct {
  int port;
  char addr[MAX_STRING_LEN];
  char size[MAX_STRING_LEN];
  int speed;
  int width;
  char port_type[MAX_STRING_LEN];
  char name[MAX_STRING_LEN];
  int aspm_active;
  int lock_active;
  int sris_active;

} DeviceInfo;

// Structure for Endpoint info
typedef struct {
  char mem_addr[MAX_STRING_LEN];
  char mem_size[MAX_STRING_LEN];
  int port;
  char dev_offset[MAX_STRING_LEN];
  char memdev[MAX_STRING_LEN];

} Endpoints;

// Structure for hosts information
typedef struct {
  int port;
  char addr[MAX_STRING_LEN];
  char size[MAX_STRING_LEN];
  int speed;
  int width;
  char port_type[MAX_STRING_LEN];
  char name[MAX_STRING_LEN];
  int aspm_active;
  int lock_active;
  int sris_active;
  int classcode;
  int deinit_active;
  Endpoints endpoints[MAX_ENDPOINTS];
  int num_endpoints;
} HostInfo;

struct StaticEndpointInfo {
  int port;
  uint64_t mem_addr;
  uint64_t mem_size;
  uint64_t dev_offset;
  char memdev_name[MAX_STRING_LEN];
  ;
};

struct StaticHostInfo {
  int class_code;
  uint64_t mem_addr;
  char name[MAX_STRING_LEN];
  int port;
  char port_type[MAX_STRING_LEN];
  uint64_t mem_size;
  int bus_speed;
  int bus_width;
  int ep_cnt;
  struct StaticEndpointInfo ep[MAX_STRING_LEN];
};

struct StaticDevInfo {
  char name[MAX_STRING_LEN];
  uint64_t mem_addr;
  uint64_t mem_size;
  int port;
  char port_type[MAX_STRING_LEN];
  int bus_speed;
  int bus_width;
};

struct StaticBoardInfo {
  char name[MAX_STRING_LEN];
  char port_type[MAX_STRING_LEN];
  char switch_mode[MAX_STRING_LEN];
  int port;
};

struct StaticPortInfo {
  int num_host;
  struct StaticHostInfo host[MAX_HOSTS];
  int num_dev;
  struct StaticDevInfo dev[MAX_DEVICES];
  struct StaticBoardInfo board;
};

int mbox_A1_connect_by_hostport(int host_port, int dev_port);
int mbox_A1_disconnect(int host_port, int dev_port);
int is_switch_alive(int);
int reboot_switch(void);
int update_json_and_install(void);
int init(const char *inp_file);
int mbox_get_static_config(const char *inp_file,
                           struct StaticPortInfo *port_info);
int set_ip(const char *ip_addr);

inline void connect_by_hostport(json_t *root, int host_port, int dev_port) {
  // printf("host_port[%d], dev_port[%d]\n",host_port,dev_port);
  // Get the root arrays for "Hosts" and "Devices"
  json_t *hosts_array = json_object_get(root, "Hosts");
  json_t *devices_array = json_object_get(root, "Devices");

  if (!hosts_array) {
    // printf("No Host array found. \n");
    return;
  }

  if (!devices_array) {
    // printf("No devices array found. \n");
    return;
  }

  // Initialize host and device object to null
  json_t *host_obj = NULL;
  json_t *dev_obj = NULL;
  int obj_found = 0;

  // check if host port exists
  size_t index;
  json_array_foreach(hosts_array, index, host_obj) {
    json_t *host_port_json = json_object_get(host_obj, "host_port");
    if (host_port_json && json_integer_value(host_port_json) == host_port) {
      // Host port found
      obj_found = 1;
      break;
    }
  }

  // IF host port not found, print error and return
  if (!obj_found) {
    printf("Host port %d not found. \n", host_port);
    return;
  }

  // check if device port exists
  obj_found = 0;
  json_array_foreach(devices_array, index, dev_obj) {
    json_t *dev_port_json = json_object_get(dev_obj, "dev_port");
    if (dev_port_json && json_integer_value(dev_port_json) == dev_port) {
      // device port found
      // printf("dev_port found[%lld] dev_obj[%p],
      // dev_addr[%s]\n",json_integer_value(dev_port_json), dev_obj,
      // json_string_value(json_object_get(dev_obj, "dev_addr")));
      obj_found = 1;
      break;
    }
  }

  // If host port not found, print error and return
  if (!obj_found) {
    // printf("Device port %d not found. \n", dev_port);
    return;
  }

  // Check if device is connected to any of the hosts
  json_t *tmp_obj;
  int target_found = 0;
  json_array_foreach(hosts_array, index, tmp_obj) {
    // check if target exists in this host

    json_t *endpoint_array = json_object_get(tmp_obj, "endpoint");
    if (endpoint_array) {
      size_t endpoint_index;
      json_t *endpoint_obj;
      json_array_foreach(endpoint_array, endpoint_index, endpoint_obj) {
        json_t *target_json = json_object_get(endpoint_obj, "target");

        if (target_json && json_integer_value(target_json) == dev_port) {
          // Host port found
          target_found = 1;
          break;
        }
      }
    }
    if (target_found) {
      break;  // No need to continue if target is found in host
    }
  }

  if (target_found) {
    // printf("Target %d found in one of the host. \n", dev_port);
    return;
  } else {
    printf("Target %d not found in any of the host. \n", dev_port);
  }

  // Get device information
  const char *dev_addr =
      json_string_value(json_object_get(dev_obj, "dev_addr"));
  const char *dev_size =
      json_string_value(json_object_get(dev_obj, "dev_size"));
  int dev_target = json_integer_value(json_object_get(dev_obj, "dev_port"));
  printf("dev_obj[%p]\n", dev_obj);

  // Create endpoint object for device in host
  json_t *endpoint_obj = json_object();
  char memdev_key[20];
  snprintf(memdev_key, sizeof(memdev_key), "mem- %d", dev_target);
  json_object_set_new(endpoint_obj, "memdev", json_string(memdev_key));
  json_object_set_new(endpoint_obj, "target", json_integer(dev_target));
  json_object_set_new(endpoint_obj, "mem_addr", json_string(dev_addr));
  json_object_set_new(endpoint_obj, "mem_size", json_string(dev_size));
  json_object_set_new(endpoint_obj, "dev_offset", json_string("0"));

  // check if target already exists in the enpoint array
  json_t *endpoint_array = json_object_get(host_obj, "endpoint");
  if (!endpoint_array) {
    endpoint_array = json_array();
    json_object_set_new(host_obj, "endpoint", endpoint_array);
  }

  json_t *existing_obj = NULL;
  int ep_found = 0;
  json_array_foreach(endpoint_array, index, existing_obj) {
    json_t *target_json = json_object_get(existing_obj, "target");
    if (target_json && json_integer_value(target_json) == dev_port) {
      // Target found, replace existing object
      json_array_set(endpoint_array, index, endpoint_obj);
      ep_found = 1;
      break;
    }
  }

  // If target not found, aapend the new endpoint object
  if (!ep_found) {
    json_array_append(endpoint_array, endpoint_obj);
  }

  // adjust_address(root);
  printf("device connected to host successfully. \n");
}

inline void disconnect(json_t *root, int host_port, int dev_port) {
  // Get the root arrays for "Hosts" and "Devices"
  json_t *hosts_array = json_object_get(root, "Hosts");

  // Initialize host and device object to null
  json_t *host_obj = NULL;
  // json_t *dev_obj = NULL;
  int obj_found = 0;

  // check if host port exists
  size_t index;
  json_array_foreach(hosts_array, index, host_obj) {
    json_t *host_port_json = json_object_get(host_obj, "host_port");
    if (host_port_json && json_integer_value(host_port_json) == host_port) {
      // Host port found
      obj_found = 1;
      break;
    }
  }

  // IF host port not found, print error and return
  if (!obj_found) {
    // printf("Host port %d not found. \n", host_port);
    return;
  }

  json_t *endpoint_array = json_object_get(host_obj, "endpoint");
  if (endpoint_array) {
    size_t endpoint_index;
    json_t *endpoint_obj;
    json_array_foreach(endpoint_array, endpoint_index, endpoint_obj) {
      json_t *dev_port_json = json_object_get(endpoint_obj, "target");
      if (dev_port_json && json_integer_value(dev_port_json) == dev_port) {
        // Device endpoint found, remove it from the endpoint array
        json_array_remove(endpoint_array, endpoint_index);
        // printf("Device endpoint removed from host succesfully\n");
        return;
      }
    }
  }

  // If device endpoint not found in the host's endpoint array
  // printf("Device port %d not found in host %d. \n", dev_port, host_port);
}

inline int exec_cmd_save_log(char *cmd) {
  int status = MBOX_SUCCESS;

#ifdef SWITCH_CMD_EXEC_LOGS_TO_FILE
  const char *log_file = SWITCH_CMD_EXEC_LOG_FILE;

  // Open the log file for writing
  int log_fd = open(log_file, O_WRONLY | O_APPEND);
  if (log_fd == -1) {
    perror("msl lab <-> Error opening file\n");
    return MBOX_FILE_OPEN_FAIL;
  }

  // Duplicate the file descriptor of the log file and assign it to stdout
  if (dup2(log_fd, STDOUT_FILENO) == -1) {
    perror("Error redirecting stdout\n");
    close(log_fd);
    return MBOX_FILE_REDIRECT_FAIL;
  }

  // Close the original file descriptor of the log file
  close(log_fd);
#endif

  // Execute the system command
  status = system(cmd);

#ifdef SWITCH_CMD_EXEC_LOGS_TO_FILE
  // Restore stdout (optional)
  fclose(stdout);
  freopen("/dev/tty", "w", stdout);  // Redirect back to the terminal
#endif

  return status;
}

inline int mbox_parse_static_board_config(json_t *board_obj,
                                          struct StaticBoardInfo *board_info) {
  board_info->port =
      json_integer_value(json_object_get(board_obj, "management_port"));

  const char *port_type_str =
      json_string_value(json_object_get(board_obj, "Mgmt_port_type"));
  if (port_type_str)
    memcpy(board_info->port_type, port_type_str, strlen(port_type_str));

  const char *switch_mode_str =
      json_string_value(json_object_get(board_obj, "switch_mode"));
  if (switch_mode_str)
    memcpy(board_info->switch_mode, switch_mode_str, strlen(switch_mode_str));

  const char *board_name =
      json_string_value(json_object_get(board_obj, "board_name"));
  if (board_name) memcpy(board_info->name, board_name, strlen(board_name));

  return 0;
}

inline int mbox_parse_static_dev_config(json_t *dev_array_obj,
                                        struct StaticDevInfo *dinfo,
                                        int *dev_cnt) {
  size_t index;
  json_t *dev_object;
  int idx = 0;

  if (!json_is_array(dev_array_obj)) {
    // printf("Error: 'Device' is not an array.\n");
    return 1;
  }

  for (int i = 0; i < 16; i++) {
    struct StaticDevInfo *dev_info = &dinfo[i];
    dev_info->port = 0xff;
  }

  json_array_foreach(dev_array_obj, index, dev_object) {
    struct StaticDevInfo *dev_info = &dinfo[idx++];

    dev_info->port =
        json_integer_value(json_object_get(dev_object, "dev_port"));
    dev_info->bus_speed =
        json_integer_value(json_object_get(dev_object, "dev_speed"));
    dev_info->bus_width =
        json_integer_value(json_object_get(dev_object, "dev_width"));

    const char *dev_addr_str =
        json_string_value(json_object_get(dev_object, "dev_addr"));
    if (dev_addr_str) sscanf(dev_addr_str, "%lx", &dev_info->mem_addr);

    const char *dev_size_str =
        json_string_value(json_object_get(dev_object, "dev_size"));
    if (dev_size_str) sscanf(dev_size_str, "%lx", &dev_info->mem_size);

    const char *port_type_str =
        json_string_value(json_object_get(dev_object, "dev_port_type"));
    if (port_type_str)
      memcpy(dev_info->port_type, port_type_str, strlen(port_type_str));

    const char *dev_name =
        json_string_value(json_object_get(dev_object, "dev_name"));
    if (dev_name) memcpy(dev_info->name, dev_name, strlen(dev_name));
  }
  *dev_cnt = idx;
  return 0;
}

inline int mbox_parse_static_host_config(json_t *host_array_obj,
                                         struct StaticHostInfo *hinfo,
                                         int *host_cnt) {
  size_t index;
  json_t *host_object;
  int host_idx = 0;

  if (!json_is_array(host_array_obj)) {
    // printf("Error: 'Hosts' is not an array.\n");
    return 1;
  }

  json_array_foreach(host_array_obj, index, host_object) {
    struct StaticHostInfo *host_info = &hinfo[host_idx++];

    host_info->class_code =
        json_integer_value(json_object_get(host_object, "classcode"));
    host_info->port =
        json_integer_value(json_object_get(host_object, "host_port"));
    host_info->bus_speed =
        json_integer_value(json_object_get(host_object, "host_speed"));
    host_info->bus_width =
        json_integer_value(json_object_get(host_object, "host_width"));

    const char *host_addr_str =
        json_string_value(json_object_get(host_object, "host_addr"));
    if (host_addr_str) sscanf(host_addr_str, "%lx", &host_info->mem_addr);

    const char *host_size_str =
        json_string_value(json_object_get(host_object, "host_size"));
    if (host_size_str) sscanf(host_size_str, "%lx", &host_info->mem_size);

    const char *port_type_str =
        json_string_value(json_object_get(host_object, "host_port_type"));
    if (port_type_str)
      memcpy(host_info->port_type, port_type_str, strlen(port_type_str));

    const char *host_name =
        json_string_value(json_object_get(host_object, "host_name"));
    if (host_name) memcpy(host_info->name, host_name, strlen(host_name));

    int dev_index;
    int dev_idx = 0;
    json_t *ep_obj;
    json_t *ep_array_obj = json_object_get(host_object, "endpoint");
    json_array_foreach(ep_array_obj, dev_index, ep_obj) {
      struct StaticEndpointInfo *ep = &host_info->ep[dev_idx++];

      const char *addr_str =
          json_string_value(json_object_get(ep_obj, "mem_addr"));
      if (addr_str) sscanf(addr_str, "%lx", &ep->mem_addr);

      const char *size_str =
          json_string_value(json_object_get(ep_obj, "mem_size"));
      if (size_str) sscanf(size_str, "%lx", &ep->mem_size);

      const char *mdev_str =
          json_string_value(json_object_get(ep_obj, "mmedev"));
      if (mdev_str) memcpy(ep->memdev_name, mdev_str, strlen(mdev_str));

      ep->port = json_integer_value(json_object_get(ep_obj, "target"));
    }
    host_info->ep_cnt = dev_idx;
  }
  *host_cnt = host_idx;
  return 0;
}

inline int update_json_and_install_on_switch(void) {
  int status = MBOX_SUCCESS;

#ifndef ENABLE_SIM
  char command[150];
  int timeout = 100;
  std::string ip_address;
  int ip_status = get_ip_address(CXL_CONF_FILE, ip_address);
  if (ip_status != 0) {
    return ip_status;
  }
  // copy file back to CXL switch(A1) server from local directory
  sprintf(command, "scp ./input.json root@%s:/etc/cxl/xc50256/",
          ip_address.c_str());
  status = exec_cmd_save_log(command);
  if (status) {
    return MBOX_CMD_EXEC_FAIL;
  }

  // compile and install json file on MX8 board
  // TODO: This can change board config. Will enable at the time of final
  // testing
  printf("Setup the config on board\n");
  sprintf(command,
          "ssh root@%s 'cd /etc/cxl/xc50256/ && json2config input.json && "
          "titan setup'",
          ip_address.c_str());
  status = exec_cmd_save_log(command);
  if (status) {
    return MBOX_CMD_EXEC_FAIL;
  }

  // reboot the switch
  //  printf("Rebooting the memory box\n");
  status = reboot_switch();
  // No need to check reboot status
  // if(status) {
  //	return status;
  // }

  sleep(5);

  // Check if switch is alive
  //  printf("check if memory box is alive with timeout %d sec\n",timeout);
  status = is_switch_alive(timeout);
  if (status) {
    return status;
  }

  // Wait for 10 sec
  sleep(10);

  // After reboot run the titan setup command again
  //  printf("After reboot again setup the config on box\n");
  sprintf(command, "ssh root@%s 'cd /etc/cxl/xc50256/ &&  titan setup'",
          ip_address.c_str());
  status = exec_cmd_save_log(command);
  if (status) {
    // printf("json setup failed on memory box after reboot\n");
    return MBOX_CMD_EXEC_FAIL;
  }

#endif
  return status;
}

#endif
