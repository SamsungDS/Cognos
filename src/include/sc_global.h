#ifndef __CXL_PLUGIN_SC_GLOBAL_H__
#define __CXL_PLUGIN_SC_GLOBAL_H__

#include <memory>
#include "sc_device.h"
#include "sc_fm.h"

class sc_mbox;

/**
* @brief global class
* @details This class encapsulates device & host object.
*/
class sc_global
{

    public:

	/**
        * @brief Default constructor
        * @details Simple constructor that creates a global object.
        */
        sc_global() =default;

	~sc_global();

        /**
        * @brief create memory box as per the json configuration.
        * @details This method takes struct portinfo as parameter
        *          and parses board, list of devices, hosts & endpoints information.
        */
        int g_create_mbox(struct StaticPortInfo * port_info);

	/**
        * @brief attach device to host.
        * @param d_id device id.
        * @param h_id host id.
        * @param mode device shared/direct connect.
        */
        size_t dev_attach(uint64_t d_id, uint64_t h_id, std::string mode, uint64_t fm_id, std::string &buffer); 

        /**
        * @brief detach device from host.
        * @param d_id device id.
        * @param h_id host id.
        * @param mode device shared/direct connect.
        */
        size_t dev_detach(uint64_t d_id, uint64_t h_id, std::string mode, uint64_t fm_id, std::string &buffer);

        /** get sc_mbox */  
	std::unordered_map<uint64_t, sc_mbox*>& get_mbox_map(); 

        /** 
	* @brief convert device object to json 
	*/	
	size_t to_device_json(std::string &buffer);

        /** 
	* @brief convert host object to json. 
	*/	
	size_t to_host_json(std::string &buffer);

	size_t to_setup_json(std::string &buffer);

        /** 
	* @brief generate json using input parameter. for ex: {"rc":0} 
	*/	
	size_t to_json(int ret,std::string &buffer);

	/** 
	 * @brief list out all persisted memory devices.
	*/
	size_t list_devices(std::string& buffer);

	/** 
	 * @brief list out all persisted hosts.
	*/
	size_t list_hosts(std::string &buffer);

	sc_mbox* mbox_find(uint64_t fm_id);

	/** 
	 * @brief fetch persisted data.
	*/
	size_t fetch_setup_info(std::string &buffer);

	/** 
	 * @brief delete dynamically allocated mbox objects.
	*/
	void clear_mbox_objects();

	/*
	 * @brief Retrieve a pointer to the FabricManager associated with the given sc_id
	 */
        FabricManager* find_fm(const sc_id& id);

	/**
	 * @brief Add a FabricManager by reference associated with an sc_id to the map
	 */
        void add_fm(const sc_id& id, FabricManager& manager);

	/**
	 * @brief remove the FabricManager pointer associated 
	 *        with the given sc_id from fm_map
	 */
	void del_fm(const sc_id& id);

	/**
	 * @brief get all keys (sc_id) as a list
	 */
	std::vector<sc_id> get_fm_keys() const; 

    private:
	std::unordered_map<uint64_t, sc_mbox*> sc_devices;
	std::vector<sc_mbox*> mb_objs;
        
	/**
	 * Map storing pointers to FabricManager objects
	 */
        std::unordered_map<sc_id, FabricManager*, hash_sc_id> fm_map;
	
	/**
	 * @brief Cleanup dynamically allocated FabricManager objects
	 */
        void cleanup_fm_map();
};

/**< global object */
extern sc_global cxl_global; 

#endif

