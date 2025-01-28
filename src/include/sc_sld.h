#ifndef __CXL_PLUGIN_SLD_DEVICES_H__
#define __CXL_PLUGIN_SLD_DEVICES_H__

#include "sc_device.h"

/**
 * @brief sld device class.
 * @details This class holds sld device related information.
 */
class sc_sld : public sc_device {
 public:
  sc_sld();

  /**
   * @brief parameterized sc_sld constructor.
   * @details This constructor delegates all the parameters to sc_device
   * constructor and from sc_device class d_id is delegated to sc_id
   * constructor.
   */
  sc_sld(uint64_t d_id, std::string d_name, uint64_t capacity, uint32_t port);

  ~sc_sld();

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

  /* get sc_id class object */
  sc_id d_get_id() const override;

  /**
   * @brief list of logical devices.
   */
  std::list<sc_device> list_sld_devices();

  /*
   * @brief create ld
   */
  int sld_id(uint64_t ldId);

  /*
   * @brief delete ld
   */
  int sd_delete_ld(uint64_t ldId);

  // Overload the != operator
  bool operator!=(const sc_sld& other) const {
    return (d_get_capacity() != other.d_get_capacity());
  }

 private:
  /**< dictionary of derived logical devices */
  std::unordered_map<sc_id, sc_device, hash_sc_id> sd_lds;
};

#endif
