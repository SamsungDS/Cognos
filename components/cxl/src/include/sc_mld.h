#ifndef __CXL_PLUGIN_MLD_DEVICES_H__
#define __CXL_PLUGIN_MLD_DEVICES_H__

#include "sc_device.h"

/**
 * @brief sc_mld class
 * @details This class holds mld device related information.
 */
class sc_mld : public sc_device {
 public:
  sc_mld();

  /**
   * @brief parameterized sc_mld constructor.
   * @details This constructor delegates all the parameters to sc_device
   * constructor, from sc_device class d_id is delegated to sc_id constructor.
   */
  sc_mld(uint64_t d_id, std::string d_name, uint64_t capacity, uint32_t port);

  ~sc_mld();

  /**
   * @brief override set device port.
   */
  void d_set_port(uint32_t port) override;

  /**
   * @brief override set device capacity.
   */
  void d_set_capacity(uint64_t capacity) override;

  /**
   * @brief override set device name.
   */
  void d_set_dev_name(std::string d_name) override;

  /**
   * @brief override get device capacity.
   */
  uint64_t d_get_capacity() const override;

  /**
   * @brief override get device name
   */
  std::string d_get_dev_name() const override;

  /**
   * @brief override get device port.
   */
  uint32_t d_get_port() const override;

  sc_id d_get_id() const override;

  /**
   * @brief list mld devices.
   */
  std::list<sc_device> list_mld_devices();

  /*
   * @brief create ld
   */
  int mld_id(uint64_t ldId);

  /*
   * @brief delete ld
   */
  int md_delete_ld(uint64_t ldId);

  bool operator!=(const sc_mld& other) const {
    return (d_get_capacity() != other.d_get_capacity());
  }

 private:
  /**< dictionary of derived logical devices */
  std::unordered_map<sc_id, sc_device, hash_sc_id> md_lds;
};

#endif
