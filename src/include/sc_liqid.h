#ifndef __CXL_PLUGIN_LIQID_H__
#define __CXL_PLUGIN_LIQID_H__

#include <cstdint>

#include "mbox_a1.h"
#include "sc_device.h"
#include "sc_mbox.h"
#include "sc_mld.h"
#include "sc_sld.h"

class sc_liqid : public sc_mbox {
 public:
  sc_liqid();

  /**
   * @brief parameterized MBOX constructor.
   * @details This constructor passes mb_switch to sc_switch class, mb_fm_id to
   * sc_id class, mb_id to sc_device class along with some literals.
   */
  sc_liqid(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch);

  ~sc_liqid();

  /* get sc_id class object */
  sc_id d_get_id() const override;

  /**
   * Override the method from sc_mbox
   * @brief attach device to host.
   * @param d_id upstream host id.
   * @param h_id downstream device id.
   * @param mode direct or shared.
   */
  int d_attach(uint64_t d_id, uint64_t h_id, std::string mode) override;

  /**
   * Override the method from sc_mbox`
   * @brief detach device to host.
   * @param d_id upstream host id.
   * @param h_id downstream device id.
   * @param mode direct or shared.
   */
  int d_detach(uint64_t d_id, uint64_t h_id, std::string mode) override;

  /**< get liqid_connected_slds*/
  std::unordered_map<sc_id, sc_sld, hash_sc_id> get_slds_map() const override;

  /**< get liqid_connected_mlds*/
  std::unordered_map<sc_id, sc_mld, hash_sc_id> get_mlds_map() const override;

  /**< get liqid_connected_hosts*/
  std::unordered_map<sc_id, sc_host, hash_sc_id> get_hosts_map() const override;
};

#endif
