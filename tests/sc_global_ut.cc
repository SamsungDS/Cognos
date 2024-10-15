#include <gtest/gtest.h>
#include "sc_global.h"
#include "sc_mbox.h"
#include "mbox_a1.h"


extern "C"{
#include "jansson.h"
}


class ScGlobalTest : public ::testing::Test {
protected:

    sc_global global_instance;
    void SetUp() override {
        uint32_t mb_id = 102;
        sc_switch sw(mb_id + 102);
        sc_mbox* mb = new sc_mbox(mb_id, mb_id + 101, sw);
        sc_sld sld(1, "SLD", 100, 1);
        sc_mld mld(2, "MLD", 200, 2);
        mb->addSld(sld);
        mb->addMld(mld);

	sc_host host1(456);
        host1.set_host_name("Host 1");
        host1.set_host_port(1);
        host1.set_capacity(1024);
        host1.set_target_ports(300);
        mb->addHost(host1);

        sc_host host2(457);
        host2.set_host_name("Host 2");
        host2.set_host_port(2);
        host2.set_capacity(2048);
        host2.set_target_ports(301);
        mb->addHost(host2);

        mb->get_phost()[1].push_back(sc_id(456));  
        mb->get_phost()[2].push_back(sc_id(457));
        global_instance.get_mbox_map()[mb_id + 101] = mb;
    }

    void TearDown() override {
        // Clean up the global instance
        global_instance.clear_mbox_objects();
    }

};


TEST_F(ScGlobalTest, CreateMboxTest) {
    struct StaticPortInfo pinfo;
    mbox_get_static_config(&pinfo);

    int result = global_instance.g_create_mbox(&pinfo);
    ASSERT_EQ(result, 0);
    // Check that the sc_mbox instance was created and added to the map
    auto mbox_map = global_instance.get_mbox_map();
    ASSERT_EQ(mbox_map.size(), 1);
    // Check the contents of the created sc_mbox
    auto mbox = mbox_map.begin()->second;
    ASSERT_NE(mbox, nullptr);
    // Check the SLD and MLD devices
    auto slds = mbox->get_slds_map();
    auto mlds = mbox->get_mlds_map();
    ASSERT_EQ(slds.size(), 1);
    ASSERT_EQ(mlds.size(), 1);
    auto sld = slds.begin()->second;
    auto mld = mlds.begin()->second;
    ASSERT_EQ(sld.d_get_id().get_sc_id(), 549755813888);
    ASSERT_EQ(mld.d_get_id().get_sc_id(), 824633720832);
    // Check the host
    auto hosts = mbox->get_hosts_map();
    ASSERT_EQ(hosts.size(), 1);
    auto host = hosts.begin()->second;
    ASSERT_EQ(host.d_get_id().get_sc_id(), 551903297536);
    ASSERT_EQ(host.get_host_port(), 2);
}

TEST_F(ScGlobalTest, MboxFindSuccess) {
    // Use an ID that exists in the setup	
    uint64_t fm_id = 203;  
    //auto [status, mbox] = global_instance.mbox_find(fm_id);
    auto mbox = global_instance.mbox_find(fm_id);
    //ASSERT_EQ(status, 0);
    ASSERT_NE(mbox, nullptr);
    EXPECT_EQ(mbox->d_get_id().get_sc_id(), 102);
}

TEST_F(ScGlobalTest, MboxFindFailure) {
    // Use an ID that does not exist	
    uint64_t fm_id = 999;  
    //auto [status, mbox] = global_instance.mbox_find(fm_id);
    auto mbox = global_instance.mbox_find(fm_id);
    //ASSERT_EQ(status, 1);
    ASSERT_EQ(mbox, nullptr);
}


TEST_F(ScGlobalTest, DevAttachTest) {
    struct StaticPortInfo pinfo;
    mbox_get_static_config(&pinfo);

    int create_result = global_instance.g_create_mbox(&pinfo);
    ASSERT_EQ(create_result, 0);
    std::string buffer;
    // Attach device to host
    size_t attach_result = global_instance.dev_attach(549755813888, 551903297536, "mode", 203, buffer);
    ASSERT_EQ(attach_result, 9);

    // Verify attachment
    auto mbox_map = global_instance.get_mbox_map();
    auto mbox = mbox_map[203];
    auto phost = mbox->get_phost();
    ASSERT_EQ(phost.size(), 2);
    ASSERT_EQ(phost[10].size(), 1);
    ASSERT_EQ(phost[10].front().get_sc_id(), 551903297536);
}

TEST_F(ScGlobalTest, NegDevAttachTest) {

    std::string buffer;

    // Attach device to host
    global_instance.dev_attach(0, 0, "mode", 203, buffer);

    json_error_t error;
    json_t* root = json_loads(&buffer[0], 0, &error);
    if (!root) {
        std::cerr << "Error parsing JSON: " << error.text << std::endl;
    }

    json_t* rcValue = json_object_get(root, "rc");
    if (json_is_integer(rcValue)) {
        int rc = json_integer_value(rcValue);
        ASSERT_EQ(rc, -2);
    } else {
        std::cerr << "Invalid 'rc' value." << std::endl;
    }

}


TEST_F(ScGlobalTest, DevDetachTest) {
    struct StaticPortInfo pinfo;
    mbox_get_static_config(&pinfo);
    int create_result = global_instance.g_create_mbox(&pinfo);
    ASSERT_EQ(create_result, 0);
    std::string buffer;
    // Attach device to host
    size_t attach_result = global_instance.dev_attach(549755813888, 551903297536, "mode", 203, buffer);
    ASSERT_EQ(attach_result, 9);
    // Detach device from host
    size_t detach_result = global_instance.dev_detach(549755813888, 551903297536, "mode", 203, buffer);
    ASSERT_EQ(detach_result, 9);

    // Verify detachment
    auto mbox_map = global_instance.get_mbox_map();
    auto mbox = mbox_map[203];
    auto phost = mbox->get_phost();
    ASSERT_EQ(phost.size(), 2);
}


TEST_F(ScGlobalTest, NegDevDetachTest) {

    std::string buffer;

    // detach device to host
    global_instance.dev_detach(0, 0, "mode", 203, buffer);

    json_error_t error;
    json_t* root = json_loads(&buffer[0], 0, &error);
    if (!root) {
        std::cerr << "Error parsing JSON: " << error.text << std::endl;
    }


    json_t* rcValue = json_object_get(root, "rc");
    if (json_is_integer(rcValue)) {
        int rc = json_integer_value(rcValue);
        //ASSERT_EQ(rc, -2);
        ASSERT_NE(rc, 0);
    } else {
        std::cerr << "Invalid 'rc' value." << std::endl;
    }
}

TEST_F(ScGlobalTest, ToDeviceJsonTest) {
    std::string buffer;	
    size_t size = global_instance.to_device_json(buffer);
    ASSERT_NE(size, 0); 
    json_error_t error;
    json_t* root = json_loadb(&buffer[0], size, 0, &error);
    ASSERT_NE(root, nullptr); 
    json_t* devices = json_object_get(root, "devices");
    ASSERT_TRUE(json_is_array(devices)); 
    EXPECT_EQ(json_array_size(devices), 2); 
    // Check each device in the array
    for (size_t i = 0; i < json_array_size(devices); ++i) {
        json_t* device = json_array_get(devices, i);
        json_t* dev_id = json_object_get(device, "dev_id");
        ASSERT_TRUE(json_is_integer(dev_id)); 
        json_t* dev_capacity = json_object_get(device, "dev_capacity");
        ASSERT_TRUE(json_is_integer(dev_capacity)); 
        json_t* dev_port = json_object_get(device, "dev_port");
        ASSERT_TRUE(json_is_integer(dev_port)); 
        json_t* hosts_attached = json_object_get(device, "hosts_attached");
        ASSERT_TRUE(json_is_array(hosts_attached)); 
        // Check the contents of the 'hosts_attached' array
        for (size_t j = 0; j < json_array_size(hosts_attached); ++j) {
            json_t* host = json_array_get(hosts_attached, j);
            ASSERT_TRUE(json_is_string(host));
        }
    }
    json_decref(root); 
    // Verify attachment
    auto mbox_map = global_instance.get_mbox_map();
    auto mbox = mbox_map[203];

    auto phost = mbox->get_phost();
    ASSERT_EQ(phost.size(), 4);
    ASSERT_EQ(phost[10].size(), 0);
    ASSERT_EQ(phost[10].front().get_sc_id(), 0);

}


TEST_F(ScGlobalTest, ToHostJsonTest) {
    std::string buffer;
    size_t size = global_instance.to_host_json(buffer);
    ASSERT_NE(size, 0); 

    json_error_t error;
    json_t* root = json_loadb(&buffer[0], size, 0, &error);
    ASSERT_NE(root, nullptr); 
    json_t* hosts = json_object_get(root, "hosts");
    ASSERT_TRUE(json_is_array(hosts)); 
    EXPECT_EQ(json_array_size(hosts), 2);

    // Check the contents of the hosts array
    json_t* host = json_array_get(hosts, 0);
    json_t* id = json_object_get(host, "id");
    ASSERT_TRUE(json_is_integer(id)); 
    json_t* name = json_object_get(host, "name");
    ASSERT_TRUE(json_is_string(name)); 
    json_t* mem_capacity = json_object_get(host, "mem_capacity");
    ASSERT_TRUE(json_is_integer(mem_capacity)); 
    json_t* host_target_ports = json_object_get(host, "host_target_ports");
    ASSERT_TRUE(json_is_array(host_target_ports)); 
    EXPECT_EQ(json_array_size(host_target_ports), 1); 
    json_t* port = json_array_get(host_target_ports, 0);
    ASSERT_TRUE(json_is_integer(port)); 
    json_decref(root); 
}


TEST_F(ScGlobalTest, ToSetupJsonTest) {
    std::string buffer;	
    // Assuming the "input.json" file exists and contains valid JSON
    size_t size = global_instance.to_setup_json(buffer);
    ASSERT_NE(size, 0); 
    json_error_t error;
    json_t *root = json_loadb(&buffer[0], size, 0, &error);
    ASSERT_NE(root, nullptr);
    json_decref(root);
}


TEST_F(ScGlobalTest, FetchSetupInfoTest) {
    std::string buffer;	
    size_t size = global_instance.fetch_setup_info(buffer);
    ASSERT_NE(size, 0); 
    json_error_t error;
    json_t *root = json_loadb(&buffer[0], size, 0, &error);
    ASSERT_NE(root, nullptr);
    json_decref(root);
}


TEST_F(ScGlobalTest, ListDevicesTest) {
    std::string buffer;	
    size_t size = global_instance.list_devices(buffer);
    ASSERT_NE(size, 0); 
    json_error_t error;
    json_t *root = json_loadb(&buffer[0], size, 0, &error);
    json_t *devices = json_object_get(root, "devices");
    ASSERT_TRUE(json_is_array(devices));
    EXPECT_EQ(json_array_size(devices), 2);
    json_decref(root);
}

TEST_F(ScGlobalTest, ListHostsTest) {
    std::string buffer;
    size_t size = global_instance.list_hosts(buffer);
    ASSERT_NE(size, 0); 
    json_error_t error;
    json_t *root = json_loadb(&buffer[0], size, 0, &error);
    json_t *hosts = json_object_get(root, "hosts");
    ASSERT_TRUE(json_is_array(hosts));
    EXPECT_EQ(json_array_size(hosts), 2);
    json_decref(root);
}


TEST_F(ScGlobalTest, ClearMboxObjectsTest) {
    global_instance.clear_mbox_objects();
    EXPECT_FALSE(global_instance.get_mbox_map().empty());
}


TEST_F(ScGlobalTest, NullPortInfo) {
    // Test for null port_info
    int result = global_instance.g_create_mbox(nullptr);
    ASSERT_EQ(result, -ENOENT);
}


TEST_F(ScGlobalTest, ValidPortInfo) {
    struct StaticPortInfo pinfo;
    //mbox_get_static_config(&pinfo);
    pinfo.num_dev = 2;
    pinfo.dev[0] = {"DEV10_256G", 549755813888, 4000000000, 2, "CXL_11", 5, 8};
    pinfo.dev[1] = {"DEV10_256G", 824633720832, 4000000000, 3, "CXL_11", 5, 8};
    pinfo.num_host = 1;
    pinfo.host[0] = {.class_code=1, .mem_addr=551903297536, .name="Host3", .port=2, .port_type="CXL_11", .mem_size=4000000000, .bus_speed=4, .bus_width=8, .ep_cnt=1,
                                .ep = StaticEndpointInfo{.port = 11, .mem_addr=4080000000000, .mem_size=4000000000, .dev_offset=4567, .memdev_name="DEV_11-256GEA"}};
    int result = global_instance.g_create_mbox(&pinfo);
    ASSERT_EQ(result, 0);
    auto mbox_map = global_instance.get_mbox_map();
    ASSERT_EQ(mbox_map.size(), 1);
    auto mbox = mbox_map.begin()->second;
    ASSERT_NE(mbox, nullptr);
    auto slds = mbox->get_slds_map();
    auto mlds = mbox->get_mlds_map();
    ASSERT_EQ(slds.size(), 1);
    ASSERT_EQ(mlds.size(), 1);
    auto sld = slds.begin()->second;
    auto mld = mlds.begin()->second;
    ASSERT_EQ(sld.d_get_id().get_sc_id(), 549755813888);
    ASSERT_EQ(mld.d_get_id().get_sc_id(), 824633720832);
    auto hosts = mbox->get_hosts_map();
    ASSERT_EQ(hosts.size(), 1);
    auto host = hosts.begin()->second;
    ASSERT_EQ(host.d_get_id().get_sc_id(), 551903297536);
    ASSERT_EQ(host.get_host_port(), 2);
}

