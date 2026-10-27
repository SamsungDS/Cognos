#include "sc_a1.h"

#include <iostream>

char ip_switch[20];

#ifdef SWITCH_CMD_EXEC_LOGS_TO_FILE
#define SWITCH_CMD_EXEC_LOG_FILE "switch_log.txt"
#endif

int mbox_get_static_config(const char *inp_file,
                           struct StaticPortInfo *port_info) {
  int dev_cnt = 0;
  int host_cnt = 0;

  FILE *input_file = fopen(inp_file, "r");
  if (!input_file) {
    // fprintf(stderr, "Error opening input file. \n");
    return 1;
  }

  json_error_t error;
  json_t *root = json_loadf(input_file, 0, &error);
  fclose(input_file);
  if (!root) {
    // fprintf(stderr, "Error parsing JSON: %s\n",error.text);
    return 1;
  }

  mbox_parse_static_host_config(json_object_get(root, "Hosts"),
                                &port_info->host[0], &host_cnt);

  port_info->num_host = host_cnt;

  mbox_parse_static_dev_config(json_object_get(root, "Devices"),
                               &port_info->dev[0], &dev_cnt);

  port_info->num_dev = dev_cnt;

  mbox_parse_static_board_config(json_object_get(root, "Board"),
                                 &port_info->board);

  return 0;
}

int mbox_A1_connect_by_hostport(int host_port, int dev_port) {
  // open input file
  FILE *input_file = fopen("input.json", "r");
  if (!input_file) {
    // fprintf(stderr, "Error opening input file. \n");
    return 1;
  }

  json_error_t error;
  json_t *root = json_loadf(input_file, 0, &error);
  fclose(input_file);
  if (!root) {
    // fprintf(stderr, "Error parsing JSON: %s\n",error.text);
    return 1;
  }

  // Add connect entry to Json file
  connect_by_hostport(root, host_port, dev_port);

  // write updated root to JSON file
  FILE *output_file = fopen("input.json", "w");
  json_dumpf(root, output_file, JSON_INDENT(4));
  fclose(output_file);

  json_decref(root);

  return 0;
}

int mbox_A1_disconnect(int host_port, int dev_port) {
  // open input file
  FILE *input_file = fopen("input.json", "r");
  if (!input_file) {
    // fprintf(stderr, "Error opening input file. \n");
    return 1;
  }

  json_error_t error;
  json_t *root = json_loadf(input_file, 0, &error);
  fclose(input_file);
  if (!root) {
    // fprintf(stderr, "Error parsing JSON: %s\n",error.text);
    return 1;
  }

  // Add connect entry to Json file
  disconnect(root, host_port, dev_port);

  // write updated root to JSON file
  FILE *output_file = fopen("input.json", "w");
  json_dumpf(root, output_file, JSON_INDENT(4));
  fclose(output_file);
  json_decref(root);

  return 0;
}

int init(const char *inp_file) {
  int status = MBOX_SUCCESS;

  // copy file from CXL_switch(A1) to local directory
  FILE *f = fopen(inp_file, "r");
  if (NULL == f) {
    // if file does not exist, scp the json file.
    char command[150];
    sprintf(command, "scp root@%s:/etc/cxl/xc50256/input.json .", ip_switch);
    status = exec_cmd_save_log(command);
    if (status) {
      return MBOX_CMD_EXEC_FAIL;
    }
  } else {
    // perror("inside else fclose\n");
    fclose(f);
  }

  return status;
}

int set_ip(const char *ip_addr) {
  if (ip_addr) {
    memcpy(ip_switch, ip_addr, strlen(ip_addr) + 1);
  } else {
    return MBOX_NULL_POINTER;
  }

  return MBOX_SUCCESS;
}

int reboot_switch(void) {
  char command[150];
  sprintf(command, "ssh root@%s 'sudo reboot'", ip_switch);

  int ret_val = exec_cmd_save_log(command);

  if (ret_val == 0) {
    return MBOX_SUCCESS;
  }

  // printf("Memory box reboot failed\n");
  return MBOX_REBOOT_FAIL;
}

int is_switch_alive(int timeout) {
  char command[100];
  int status = 0;
  int cnt = 0;
  do {
    sprintf(command, "ping -c 1 %s", ip_switch);

    status = exec_cmd_save_log(command);
    if (status == 0) {
      printf("\nPing success\n");
    } else {
      // printf("Ping fail\n");
      printf("..");
    }
    cnt++;

  } while (status != 0 && cnt < timeout);

  printf("\n");

  if (status) {
    // printf("Ping to memory box fail with timeout[%d]\n",timeout);
    return MBOX_PING_FAIL;
  }

  return status;
}

int update_json_and_install(void) {
  int status = MBOX_SUCCESS;

  status = update_json_and_install_on_switch();

  return status;
}
