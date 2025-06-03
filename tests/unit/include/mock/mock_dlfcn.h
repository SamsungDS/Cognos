#ifndef _MOCK_DLFCN__H_
#define _MOCK_DLFCN__H_

#include <stdlib.h>
#include <string.h>

#include <cstdint>
#include <iostream>

#include "mock.h"

static char mock_dlopen_dummy_handle;
static void *mock_dlopen_dummy_ptr = &mock_dlopen_dummy_handle;

DEFINE_RETURN_MOCK(dlopen, void *);
void *dlopen(const char *filename, int flags) {
  const char *env_string;
  env_string = getenv("MOCK_DLOPEN_SUCCESS");
  if (env_string && strcmp(env_string, "true") == 0) {
    // Return some valid pointer for simulation purpose
    std::cout << "Returning dummy pointer from dlopen" << std::endl;
    return mock_dlopen_dummy_ptr;
  }

  return nullptr;
}

DEFINE_RETURN_MOCK(dlclose, int);
int dlclose(void *handle) {
  const char *env_string;
  env_string = getenv("MOCK_DLCLOSE_FAIL");
  if (env_string && strcmp(env_string, "true") == 0) {
    // Return some valid pointer for simulation purpose
    return -1;
  }

  return 0;
}

void *get_ptr_from_string(const char *hex_str) {
  char *endptr;
  uintptr_t ptr_value;

  // Parse the hexadecimal string
  // Note: Assumes address is 64bit max
  ptr_value = strtoul(hex_str, &endptr, 16);

  if (*endptr != '\0') {
    std::cout << "Invalid input" << std::endl;
    return nullptr;
  }

  void *ptr = (void *)ptr_value;
  return ptr;
}

DEFINE_RETURN_MOCK(dlsym, void *);
void *dlsym(void *handle, const char *symbol) {
  const char *env_string_return_pointer;

  env_string_return_pointer = std::getenv("MOCK_DLSYM_RETURN_PTR");

  if (env_string_return_pointer) {
    return get_ptr_from_string(env_string_return_pointer);
  }

  std::cout << "No mock values detected" << std::endl;

  return nullptr;
}

#endif  // _MOCK_DLFCN__H_