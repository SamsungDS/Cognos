#include <typeinfo>
#include "jansson.h"
#include "sc_global.h"
#include "sc_mbox.h"
#include "sc_sld.h"
#include "sc_mld.h"
#include "sc_host.h"
#include <stdint.h>
#include <memory>
#include <errno.h>


using namespace std;

/**
* @brief create memory box as per the json configuration.
* @details This method takes struct portinfo as parameter
*          and parses board, list of devices, hosts & endpoints information.
* @param port_info memory box json struct reference.
* @param dsize number of devices in the memory box.
* @param hsize number of hosts in the memory box.
*/
int sc_global::g_create_mbox(struct StaticPortInfo * port_info){

    if (port_info == nullptr) {
        return -ENOENT; 
    }	

    uint32_t mb_id = 102;

    sc_switch sw(mb_id+102);   

    //@to-do fabric manager id = mb_id+101, sw= sc_switch object 
    sc_mbox* mb = new sc_mbox(mb_id, mb_id+101, sw); 
    
    for(int i=0; i<port_info->num_dev; i++) { 
 
        struct StaticDevInfo * dev_info = &port_info->dev[i];
 
	//@to-do even position of devices are slds and odd positions are mlds.
	if (i%2==0){ 
            sc_sld sld(dev_info->mem_addr, dev_info->name, dev_info->mem_size, dev_info->port);
	    mb->addSld(sld);
        }
        else{
            sc_mld mld(dev_info->mem_addr, dev_info->name, dev_info->mem_size, dev_info->port);
            mb->addMld(mld); 
        }
    }

     
    for(int i=0; i<port_info->num_host; i++) { 
    
        struct StaticHostInfo * host_info = &port_info->host[i];
   
        sc_host h(host_info->mem_addr);
        h.set_host_name(host_info->name);
        h.set_host_port(host_info->port);
        h.set_capacity(host_info->mem_size);
            
	for(int i=0;i<host_info->ep_cnt;i++){
            struct StaticEndpointInfo * ep_info = &host_info->ep[i];
            h.set_target_ports(ep_info->port);
        }
	mb->addHost(h);
    }

    sc_devices[mb_id+101]=mb;
    mb_objs.push_back(mb);

    return 0;	
}



//get sc_devices map
unordered_map<uint64_t, sc_mbox*>& sc_global::get_mbox_map() { return sc_devices; }


sc_mbox* sc_global::mbox_find(uint64_t fm_id){

    for(auto& pair: get_mbox_map()){
        if (pair.first == fm_id){
            sc_mbox* mb = pair.second;
            return mb;
        }
    }
    return nullptr;
}


/**
* @details This method invokes sc_mbox class d_connect method which basically 
*          attaches device to the host.
*/
size_t sc_global::dev_attach(uint64_t d_id, uint64_t h_id, string mode, uint64_t fm_id, string &buffer){

    int rc;	 
    sc_mbox *mb = mbox_find(fm_id);
    if (mb == NULL)
        rc = -ENOENT;
    else
        rc = mb->d_attach(d_id, h_id, mode);
    return to_json(rc, buffer);
}


/**
* @details This method invokes sc_mbox class d_disconnect method which basically 
*          detaches device from the host.
*/
size_t sc_global::dev_detach(uint64_t d_id, uint64_t h_id, string mode, uint64_t fm_id, string &buffer){

    int rc;	 
    sc_mbox *mb = mbox_find(fm_id);
    if (mb == NULL)
        rc = -ENOENT;
    else
        rc = mb->d_detach(d_id, h_id, mode);
    return to_json(rc, buffer);
}


/**
 * @details create json object using the input provided.
 */ 
size_t sc_global::to_json(int ret, string &buffer){

    json_t* root = json_object();
    json_t* jtemp = json_integer(ret);
    json_object_set_new(root, "rc", jtemp);

    // Dump the JSON object to the buffer
    size_t bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));


    if (bytes_written == 0 || bytes_written >= buffer.size()) {
        size_t buffer_size = bytes_written + 1;
        buffer.resize(buffer_size);
        bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));
    }

    // Clean up
    json_decref(root);
    return bytes_written;

}

/**
 * @brief create json response by iterating over persisted device objects.
 */
size_t sc_global::to_device_json(string &buffer){

    json_t* root = json_object();
    json_t* temp = json_array();
    json_object_set_new(root, "devices", temp);

    for(const auto& pair: get_mbox_map())
    {
        sc_mbox* mb = pair.second;

        for (auto& sld:mb->mbox_list_connected_slds()){


            json_t* jroot = json_object();
            json_t* jtemp = NULL;

            jtemp = json_integer(sld.d_get_id().get_sc_id());
            json_object_set_new(jroot, "dev_id", jtemp);
            jtemp = json_integer(sld.d_get_capacity());
            json_object_set_new(jroot, "dev_capacity", jtemp);

            jtemp = json_integer(sld.d_get_port());
            json_object_set_new(jroot, "dev_port", jtemp);

            jtemp = json_array();
            json_object_set_new( jroot, "hosts_attached", jtemp);
            list<sc_id>& hl = mb->get_phost()[sld.d_get_port()]; 
	    for (auto& sc_h:hl){
                json_array_append_new(jtemp, json_string(mb->get_hosts_map()[sc_h].get_host_name().c_str()));
	    }
            json_array_append(temp, jroot);
        }

        for (auto& mld:mb->mbox_list_connected_mlds()){

            json_t* jroot = json_object();
            json_t* jtemp = NULL;

            jtemp = json_integer(mld.d_get_id().get_sc_id());
            json_object_set_new(jroot, "dev_id", jtemp);
            jtemp = json_integer(mld.d_get_capacity());
            json_object_set_new(jroot, "dev_capacity", jtemp);

            jtemp = json_integer(mld.d_get_port());
            json_object_set_new(jroot, "dev_port", jtemp);
	    
            jtemp = json_array();
            json_object_set_new( jroot, "hosts_attached", jtemp);
            list<sc_id>& hl = mb->get_phost()[mld.d_get_port()]; 
	    for (auto& sc_h:hl){
                json_array_append_new(jtemp, json_string(mb->get_hosts_map()[sc_h].get_host_name().c_str()));
	    }
            json_array_append(temp, jroot);
        }
       
    }

    // Dump the JSON object to the buffer
    size_t bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));    

    // Check if buffer size was sufficient
    if (bytes_written == 0 || bytes_written >= buffer.size()) {
        // If buffer was too small, resize and try again, +1 for null terminator
        size_t buffer_size = bytes_written + 1; 
        buffer.resize(buffer_size);
        bytes_written = json_dumpb(root, &buffer[0], buffer_size, JSON_INDENT(0));
    }

    // Clean up
    json_decref(root);
    return bytes_written;
}


/**
 * @brief create json response by iterating over persisted host objects.
 * */
size_t sc_global::to_host_json(string &buffer){

    json_t* root = json_object();
    json_t* temp = json_array();
    json_object_set_new(root, "hosts", temp);

    for(const auto& pair: get_mbox_map())
    {
        sc_mbox* mb = pair.second;
        
        for (auto& h:mb->mbox_list_connected_hosts()){

            json_t* jroot = json_object();
            json_t* jtemp = NULL;

            jtemp = json_integer(h.get_id());
            json_object_set_new(jroot, "id", jtemp);

            jtemp = json_string(h.get_host_name().c_str());
            json_object_set_new(jroot, "name", jtemp);

            jtemp = json_integer(h.get_capacity());
            json_object_set_new(jroot, "mem_capacity", jtemp);

            jtemp = json_array();
            json_object_set_new( jroot, "host_target_ports", jtemp);

	    for (auto& v: h.get_target_ports()){
                json_array_append_new(jtemp, json_integer(v));
            }		

            json_array_append(temp, jroot);

	}    
        
    }

    // Dump the JSON object to the buffer
    size_t bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));

    // Check if buffer size was sufficient
    if (bytes_written == 0 || bytes_written >= buffer.size()) {
        // If buffer was too small, resize and try again, +1 for null terminator
        size_t buffer_size = bytes_written + 1;
        buffer.resize(buffer_size);
        bytes_written = json_dumpb(root, &buffer[0], buffer_size, JSON_INDENT(0));
    }

    // Clean up
    json_decref(root);
    return bytes_written;
}


size_t sc_global::to_setup_json(string &buffer){ 

    json_t *root;
    json_error_t error;

    root = json_load_file("input.json", 0, &error);

    // Dump the JSON object to the buffer
    size_t bytes_written = json_dumpb(root, &buffer[0], buffer.size(), JSON_INDENT(0));

    // Check if buffer size was sufficient
    if (bytes_written == 0 || bytes_written >= buffer.size()) {
        // If buffer was too small, resize and try again
        size_t buffer_size = bytes_written + 1;
        buffer.resize(buffer_size);
        bytes_written = json_dumpb(root, &buffer[0], buffer_size, JSON_INDENT(0));
    }

    // Clean up
    json_decref(root);
    return bytes_written;
}


size_t sc_global::fetch_setup_info(string &buffer){ return to_setup_json(buffer);	}

size_t sc_global::list_devices(string &buffer){ return to_device_json(buffer); }

size_t sc_global::list_hosts(string &buffer){ return to_host_json(buffer); }

void sc_global::clear_mbox_objects(){ mb_objs.clear(); } 
