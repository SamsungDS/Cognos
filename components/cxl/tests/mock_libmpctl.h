#ifndef MOCK_LIBMPCTL_H
#define MOCK_LIBMPCTL_H

#include <vector>

#include "libmpctl.h"

/**
 * @brief In-memory replacement for libmpctl used by the unit tests.
 *
 * mock_libmpctl.cc implements the libmpctl.h API on top of this state, so
 * DevCMMMP can be tested without CMM-MP hardware. Device and MPN ids are
 * indexes into the vectors, as in libmpctl v0.3.
 */
namespace mock_mpctl {

struct State {
  // return code of mpctl_init()
  int init_rc = MPCTL_RC_SUCCESS;
  // return code of lifecycle / pool operations
  int op_rc = MPCTL_RC_SUCCESS;
  // make every *_get_info() call return NULL
  bool fail_get_info = false;
  // NUMA node reported after mpctl_mpn_online()
  int online_numa_node = -1;

  mpctl_pool pool{};
  std::vector<mpctl_mpdev> mpdevs;
  std::vector<mpctl_mpn> mpns;

  int init_calls = 0;
  int close_calls = 0;
  int host_init_calls = 0;
  int pool_create_calls = 0;
  int pool_add_calls = 0;
  unsigned int last_pool_add_id = 0;
  int online_calls = 0;
  int offline_calls = 0;
  int enable_dax_calls = 0;
  int open_contexts = 0;
};

/** Returns the global mock state. */
State& state();

/** Resets the mock state to an empty, ready pool. */
void reset();

/** Adds an MP device and updates the pool counts. */
mpctl_mpdev& add_mpdev(unsigned int slot_id, bool local, bool pooled,
                       uint16_t size_gb, uint32_t chip_id);

/** Adds an offline MPN and updates the pool counts. */
mpctl_mpn& add_mpn(uint32_t size_gb, uint16_t slot_id, int location);

}  // namespace mock_mpctl

#endif
