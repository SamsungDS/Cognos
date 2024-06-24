#include "sc_mbox.h"
#include <errno.h>


using namespace std;

sc_mbox::sc_mbox():sc_mbox(0,0,0){}

/**
 * @brief creates a sc_mox object with the given parameters.
 * @details This constructor passes mb_switch to sc_switch class, mb_fm_id to sc_id class,
 *          mb_id to sc_device class along with some literals.   
*/
sc_mbox::sc_mbox(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch): 
        sc_device(mb_id, "mbox1", 0,  INVALID_DEV_PORT),  mbox_fm_id(mb_fm_id), mbox_switch(mb_switch) {}


sc_mbox::~sc_mbox(){}


int sc_mbox::check_d_ids(sc_device dobj){

    // Remove the d_id from d_ids
    auto d_id_it = d_ids.find(dobj.d_get_id().get_sc_id());
    if (d_id_it != d_ids.end()) {
        d_ids.erase(d_id_it);
    } else {
        // d_id not found
        return -ENOENT; // Error
    }

    return 0;    

}

int sc_mbox::check_pdev(sc_device dobj){

    // Remove the d_id from pdev
    auto pdev_it = pdev.find(dobj.d_get_port()); 
    if (pdev_it != pdev.end()) {
        pdev.erase(pdev_it);
    } else {
        // d_id not found in pdev
        return -ENOENT; // Error
    }

    return 0;
}


int sc_mbox::mbox_delete_sld(sc_sld sld) { 
	
    // Remove the sc_sld from mbox_connected_slds
    auto sld_it = mbox_connected_slds.find(sld.d_get_id());
    if (sld_it != mbox_connected_slds.end()) {
        mbox_connected_slds.erase(sld_it);
    } else {
        // SLD with the specified d_id not found
        return -ENOENT; // Error
    }


    if (check_d_ids(sld) < 0) {
        return 1;
    }

    if (check_pdev(sld) < 0) {
        return 1;
    }


    return 0; // Success
}

int sc_mbox::mbox_delete_mld(sc_mld mld) { 
	
    // Remove the sc_mld from mbox_connected_slds
    auto mld_it = mbox_connected_mlds.find(mld.d_get_id());
    if (mld_it != mbox_connected_mlds.end()) {
        mbox_connected_mlds.erase(mld_it);
    } else {
        // MLD with the specified d_id not found
        return -ENOENT; // Error
    }


    if (check_d_ids(mld) < 0) {
        return 1;
    }

    if (check_pdev(mld) < 0) {
        return 1;
    }

    return 0; 
}

/**
* @brief get memory box switch information.
* @details return switch info.
*/
string sc_mbox::mbox_get_switch_info() { return mbox_switch.to_json(); }

/** 
 * @details iterate over mbox_connected_slds to list out the persisted sld objects 
 * */
list<sc_sld> sc_mbox::mbox_list_connected_slds() {
    list<sc_sld> values;
    transform(mbox_connected_slds.begin(), mbox_connected_slds.end(), back_inserter(values),
	      []( const pair<sc_id, sc_sld> &pair){
                  return pair.second; 
              });
    return values;};

/** 
 * @details iterate over mbox_connected_mlds to list out the persisted mld objects. 
 * */
list<sc_mld> sc_mbox::mbox_list_connected_mlds() {
    list<sc_mld> values;
    transform(mbox_connected_mlds.begin(), mbox_connected_mlds.end(), back_inserter(values),
	      []( const pair<sc_id, sc_mld> &pair){
                  return pair.second; 
              });
    return values;};

/** 
 * @details iterate over mbox_connected_mlds to list out the persisted mld objects. 
 * */
list<sc_host> sc_mbox::mbox_list_connected_hosts() {
    list<sc_host> values;
    transform(mbox_connected_hosts.begin(), mbox_connected_hosts.end(), back_inserter(values),
	      []( const pair<sc_id, sc_host> &pair){
                  return pair.second; 
              });
    return values;};



/** create sld */
sc_sld sc_mbox::mbox_create_sld(uint64_t capacity) {
    //@to-do 
    sc_sld sld;
    sld.d_set_capacity(capacity);
    return sld;}; 

/** create mld */
sc_mld sc_mbox::mbox_create_mld(uint64_t capacity) {
    //@to-do 
    sc_mld mld;
    mld.d_set_capacity(capacity);
    return mld;};


/* override d_get_id */
sc_id sc_mbox::d_get_id() const { return sc_device::d_get_id(); }

/** 
 * @brief add sld object to mbox_connected_slds, d_ids & pdev. 
 */
void sc_mbox::addSld(sc_sld& sld) {
    mbox_connected_slds[sld.d_get_id()]=sld;
    d_ids[sld.d_get_id().get_sc_id()]=sld.d_get_id();
    pdev[sld.d_get_port()]=sld.d_get_id();
}

/** 
 * @details add mld object to mbox_connected_mlds, d_ids & pdev. 
 */
void sc_mbox::addMld(sc_mld& mld) {
    //create mld object id -> mld object map 	
    mbox_connected_mlds[mld.d_get_id()]=mld;
    //create mld int id -> mld object id map 
    d_ids[mld.d_get_id().get_sc_id()]=mld.d_get_id();
    //create mld port to mld object id map
    pdev[mld.d_get_port()]=mld.d_get_id();
}

/** 
 * @details add host object to mbox_connected_hosts, h_ids & phost. 
 */
void sc_mbox::addHost(sc_host& host) {
    
    mbox_connected_hosts[host.d_get_id()]=host;
    h_ids[host.d_get_id().get_sc_id()]=host.d_get_id();
    for(auto& p:host.get_target_ports()){
        phost[p].push_back(host.d_get_id());
    }
}


/**
 * @details search for d_id in sld/mld maps to fetch the respective d_port.  
 */
int sc_mbox::check_d_ports(uint64_t d_id){

    uint32_t d_port = 0;

    //check if device id exists in sld persistent object
    if (mbox_connected_slds.find(d_ids[d_id]) != mbox_connected_slds.end()) {
        d_port = mbox_connected_slds[d_ids[d_id]].d_get_port();
    }

    //check if device id exists in mld persistent object
    else if (mbox_connected_mlds.find(d_ids[d_id]) != mbox_connected_mlds.end()) {
        d_port = mbox_connected_mlds[d_ids[d_id]].d_get_port();
    }
    else{
       // device does not exists
       return -ENOENT;
    }

    return d_port;

}


/**
* @details This function invokes STG API to attach device to host.
*/
int sc_mbox::d_attach(uint64_t d_id, uint64_t h_id, string mode){

    uint32_t d_port = check_d_ports(d_id);

    if (d_port<=0) {
	//device port does not exist   
	return 1; 
    }  	

    if (mbox_connected_hosts.find(h_ids[h_id]) != mbox_connected_hosts.end()){
	
	bool na = false; // device not attached     

	//check for device port in phost 
        if (phost.find(d_port)!=phost.end()) { 
	    //check if device already attached
	    list<sc_id>& hl = phost[d_port];
            for (auto& h:hl){
                if (mbox_connected_hosts[h].get_id()==h_id){
                    return 0;  
                }
            }
	    //port exist but not attached to current host 
	    na=true;
        }

	//port does not exist or port exist but not attached to current host
	if (na or phost.find(d_port)==phost.end()){
            //invoke STG API with host_port and dev_port
	    int ret = mbox_A1_connect_by_hostport(mbox_connected_hosts[h_ids[h_id]].get_host_port(), d_port);
            int uret=update_json_and_install();
	    if(uret>0){
	        return uret;
	    }
            if (ret == 0){
                //update data structures 		    
                mbox_connected_hosts[h_ids[h_id]].set_target_ports(d_port);
                phost[d_port].push_back(h_ids[h_id]);	
	    }
	    return ret; 
            	    
	}
	
    }

    //host does not exist 
    return 1; 

}


/**
* @details This function invokes STG API to detach device from host.
*/
int sc_mbox::d_detach(uint64_t d_id, uint64_t h_id, string mode){

    uint32_t d_port = check_d_ports(d_id);

    if (d_port<0) {
        //device port does not exist
        return 1; 
    }

    //check if device is already connected to host
    if (phost.find(d_port) != phost.end()) {
	
	int ret = 1;     
        for (auto& h:phost[d_port]){
            if (mbox_connected_hosts[h].get_id()==h_id){
                // invoke STG API
		ret = mbox_A1_disconnect(mbox_connected_hosts[h_ids[h_id]].get_host_port(),d_port);
		int uret=update_json_and_install();
		if(uret>0){
		    return uret;
	        }
		if (ret==0){
	            phost[d_port].remove(h);
                    mbox_connected_hosts[h_ids[h_id]].get_target_ports().remove(d_port);
		    break;
		}
	    }
	}	

	if (phost[d_port].empty()) { phost.erase(d_port); } 

	return ret;
    }
    else{
        // device not attached to device. 
        return 1; 
    }

}


//get mbox_connected_slds
unordered_map<sc_id, sc_sld, hash_sc_id> sc_mbox::get_slds_map()  { return mbox_connected_slds; }

//get mbox_connected_mlds
unordered_map<sc_id, sc_mld, hash_sc_id> sc_mbox::get_mlds_map()  { return mbox_connected_mlds; }

//get mbox_connected_hosts
unordered_map<sc_id, sc_host, hash_sc_id> sc_mbox::get_hosts_map() { return mbox_connected_hosts; }

unordered_map<uint64_t, sc_id> sc_mbox::get_d_ids() { return d_ids; }

unordered_map<uint32_t,sc_id> sc_mbox::get_pdev() { return pdev; }

unordered_map<uint32_t,list<sc_id>>& sc_mbox::get_phost() { return phost; } 




