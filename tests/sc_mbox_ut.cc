#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include <errno.h>
#include "sc_mbox.h" 
#include "sc_device.h"
#include "sc_sld.h"
#include "sc_mld.h"
#include "sc_host.h"

using ::testing::Return;
using namespace std;


class MockScMbox : public sc_mbox {
public:
    MockScMbox(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch) : sc_mbox(mb_id, mb_fm_id, mb_switch) {}
    MOCK_METHOD(int, update_json_and_install, (), ());
};



class ScMboxTest : public ::testing::Test {
protected:
    void SetUp() override {
        switch_instance = sc_switch(42); 
        mbox = new sc_mbox(123, 456, switch_instance);
    }

    void TearDown() override {
        delete mbox;
    }

    sc_switch switch_instance; 
    sc_mbox* mbox;
    MockScMbox* mock_mbox; 

};


TEST_F(ScMboxTest, DefaultConstructorTest) {
    sc_mbox mbox;	
    ASSERT_EQ(mbox.d_get_id().get_sc_id(), 0);
}


TEST_F(ScMboxTest, ParameterizedConstructorTest) {
    ASSERT_EQ(mbox->d_get_id().get_sc_id(), 123);
}

TEST_F(ScMboxTest, GetIdTest) {
       sc_mbox mbox(101, 202, 303);
       uint64_t result = mbox.d_get_id().get_sc_id();
       ASSERT_EQ(result, 101);
}


TEST_F(ScMboxTest, GetCompositeObjTest) {
       sc_mbox mbox(101, 202, 303);

       sc_id result = mbox.d_get_id();

       ASSERT_EQ(result, sc_id(101));
}

TEST_F(ScMboxTest, ListConnectedSldsTest) {
       sc_mbox mbox(1, 2, 3);
       sc_sld sld1(123, "TestDevice", 1024, 8080);
       sc_sld sld2(456, "TestDevice2", 1024, 8081);
       mbox.addSld(sld1);
       mbox.addSld(sld2);

       list<sc_sld> result = mbox.mbox_list_connected_slds();

       ASSERT_EQ(result.size(), 2);
}

TEST_F(ScMboxTest, ListConnectedMldsTest) {
       sc_mbox mbox(1, 2, 3);
       sc_mld mld1(123, "TestDevice", 1024, 8080);
       sc_mld mld2(456, "TestDevice2", 1024, 8081);
       mbox.addMld(mld1);
       mbox.addMld(mld2);
       list<sc_mld> result = mbox.mbox_list_connected_mlds();
       ASSERT_EQ(result.size(), 2);
}


TEST_F(ScMboxTest, CreateMldTest) {
       sc_mbox mbox(1, 2, 3);
       sc_mld result = mbox.mbox_create_mld(1024);
       ASSERT_NE(result, sc_mld{});
       ASSERT_TRUE(result.d_get_capacity() > 0);
}


TEST_F(ScMboxTest, DeleteMldTest) {
       sc_mbox mbox(1, 2, 3);
       sc_mld mld(123, "TestDevice", 1024, 8080);
       mbox.addMld(mld);
       int result = mbox.mbox_delete_mld(mld);
       ASSERT_EQ(result, 0);
}



TEST_F(ScMboxTest, CreateSldTest) {
       sc_mbox mbox(1, 2, 3);
       sc_sld result = mbox.mbox_create_sld(1024);
       ASSERT_NE(result, sc_sld{});
       ASSERT_TRUE(result.d_get_capacity() > 0);
}


TEST_F(ScMboxTest, DeleteSldTest) {
       sc_mbox mbox(1, 2, 3);
       sc_sld sld(123, "TestDevice", 1024, 8080);
       mbox.addSld(sld);
       int result = mbox.mbox_delete_sld(sld);
       ASSERT_EQ(result, 0);
}


TEST_F(ScMboxTest, DeleteSldTest_neg) {
    sc_mbox mbox(1, 2, 3);
    sc_sld sld(123, "TestDevice", 1024, 8080);
    mbox.addSld(sld);

    // Test case 1: Deleting a non-existent sc_sld
    sc_sld nonExistentSld(456, "NonExistentDevice", 2048, 9090);
    int result1 = mbox.mbox_delete_sld(nonExistentSld);
    ASSERT_EQ(result1, -ENOENT);

    // Test case 4: Deleting the originally added sc_sld (success case)
    int result4 = mbox.mbox_delete_sld(sld);
    ASSERT_EQ(result4, 0);
}

TEST_F(ScMboxTest, DeviceIdExistsInSlds) {
    sc_sld sld(123, "TestDevice", 1024, 8080);
    mbox->addSld(sld);
    int result = mbox->fetch_device_port(sld.d_get_id().get_sc_id());
    ASSERT_EQ(result, sld.d_get_port());
}

TEST_F(ScMboxTest, DeviceIdExistsInMlds) {
    sc_mld mld(456, "AnotherDevice", 2048, 9090);
    mbox->addMld(mld);
    int result = mbox->fetch_device_port(mld.d_get_id().get_sc_id());
    ASSERT_EQ(result, mld.d_get_port());
}

// Test case: Get switch information
TEST_F(ScMboxTest, GetSwitchInfoTest) {

    string result = mbox->mbox_get_switch_info();

    // Expected switch information (JSON-like format)
    string expectedInfo = R"({
        "SwitchID": 42,
        "Manufacturer": "Unknown",
        "UpstreamPorts": 0,
        "DownstreamPorts": 0,
        "ManagementPort": 0
    })";


    // Normalize spacing (remove extra spaces and newlines)
    std::string normalizedExpectedInfo;
    for (char c : expectedInfo) {
        if (!std::isspace(c)) {
            normalizedExpectedInfo += c;
        }
    }

    // Normalize spacing (remove extra spaces and newlines)
    std::string normalizedResult;
    for (char c : result) {
        if (!std::isspace(c)) {
            normalizedResult += c;
        }
    }

    ASSERT_EQ(normalizedResult, normalizedExpectedInfo);
}


TEST_F(ScMboxTest, AttachDeviceToHostTest) {
    sc_sld sld(123, "DEV_11-256G", 1024, 11);
    sc_host host(456);
    host.set_host_name("Host 1 LNK0");
    host.set_host_port(2);
    mbox->addSld(sld);
    mbox->addHost(host);
    int result = mbox->d_attach(sld.d_get_id().get_sc_id(), host.d_get_id().get_sc_id(), "mode");
    ASSERT_EQ(result, 0);
    auto hosts_map = mbox->get_hosts_map();
    ASSERT_TRUE(hosts_map.find(host.d_get_id()) != hosts_map.end());
}

TEST_F(ScMboxTest, AttachDeviceToHostTestNeg) {
    sc_sld sld(123, "DEV_11-256G", 1024, 11);
    sc_host host(456);
    host.set_host_name("Host 1 LNK0");
    host.set_host_port(2);
    mbox->addSld(sld);
    mbox->addHost(host);
    int result = mbox->d_attach(555, host.d_get_id().get_sc_id(), "mode");
    ASSERT_EQ(result, -2);
    int result1 = mbox->d_attach(sld.d_get_id().get_sc_id(), 555, "mode");
    ASSERT_EQ(result1, -2);
}



TEST_F(ScMboxTest, DetachDeviceToHostTest) {
    sc_sld sld(123, "DEV_11-256G", 1024, 11);
    sc_host host(456);
    host.set_host_name("Host 1 LNK0");
    host.set_host_port(2);
    mbox->addSld(sld);
    mbox->addHost(host);
    mbox->d_attach(sld.d_get_id().get_sc_id(), host.d_get_id().get_sc_id(), "mode");
    int result = mbox->d_detach(sld.d_get_id().get_sc_id(), host.d_get_id().get_sc_id(), "mode");
    ASSERT_EQ(result, 0);
    auto hosts_map = mbox->get_hosts_map();
    ASSERT_TRUE(hosts_map.find(host.d_get_id()) != hosts_map.end());
}


TEST_F(ScMboxTest, DetachDeviceToHostTestNeg) {
    sc_sld sld(123, "DEV_11-256G", 1024, 11);
    sc_host host(456);
    host.set_host_name("Host 1 LNK0");
    mbox->addSld(sld);
    mbox->addHost(host);
    mbox->d_attach(sld.d_get_id().get_sc_id(), host.d_get_id().get_sc_id(), "mode");
    int result = mbox->d_detach(sld.d_get_id().get_sc_id(), 777, "mode");
    ASSERT_EQ(result, -2);
}



TEST_F(ScMboxTest, GetSldsMap) {
    sc_sld sld(789, "DEV_11-256G", 1024, 11);
    sc_id sld_id = sld.d_get_id();
    mbox->addSld(sld);
    auto slds_map = mbox->get_slds_map();
    ASSERT_EQ(slds_map[sld_id].d_get_id(), sld.d_get_id());
}

TEST_F(ScMboxTest, GetMldsMap) {
    sc_mld mld(789, "DEV_11-256G", 1024, 11);
    sc_id mld_id = mld.d_get_id();
    mbox->addMld(mld);
    auto mlds_map = mbox->get_mlds_map();
    ASSERT_EQ(mlds_map[mld_id].d_get_id(), mld.d_get_id());
}

TEST_F(ScMboxTest, GetPDevMap) {
    sc_sld sld(789, "DEV_11-256G", 1024, 11);
    mbox->addSld(sld);
    sc_id sld_id = sld.d_get_id();
    uint32_t port = sld.d_get_port();
    auto pdev_map = mbox->get_pdev();
    ASSERT_EQ(pdev_map[port].get_sc_id(), sld_id.get_sc_id());
}

TEST_F(ScMboxTest, GetPHostMap) {
    sc_id s_id(789);
    uint32_t host_key = 1;
    mbox->get_phost()[host_key].push_back(s_id);
    auto phost_map = mbox->get_phost();
    ASSERT_EQ(phost_map[host_key].front().get_sc_id(), s_id.get_sc_id());
}


TEST_F(ScMboxTest, GetDIdsMap) {
    sc_sld sld(789, "DEV_11-256G", 1024, 11);
    mbox->addSld(sld);
    auto d_ids_map = mbox->get_d_ids();
    ASSERT_EQ(d_ids_map[789].get_sc_id(), sld.d_get_id().get_sc_id());
}


TEST_F(ScMboxTest, DeleteDIdsFailure) {
    sc_device dobj(789, "DEV_11-256G", 1024, 11);
    int result = mbox->delete_d_ids(dobj);
    EXPECT_EQ(result, -ENOENT); 
}

TEST_F(ScMboxTest, DeletePDevFailure) {
    sc_device dobj(799, "DEV_11-256G", 1024, 11);
    int result = mbox->delete_pdev(dobj);
    EXPECT_EQ(result, -ENOENT); 
}

TEST_F(ScMboxTest, DeletePDevSuccess) {
    sc_sld sld(799, "DEV_11-256G", 1024, 11);
    mbox->addSld(sld); 
    int result = mbox->delete_pdev(sld);
    EXPECT_EQ(result, 0); 
}

TEST_F(ScMboxTest, DeleteDIdsSuccess) {
    sc_sld sld(789, "DEV_11-256G", 1024, 11);
    mbox->addSld(sld); 
    int result = mbox->delete_d_ids(sld);
    EXPECT_EQ(result, 0); 
}

TEST_F(ScMboxTest, DeleteMldTest_neg) {
    sc_mbox mbox(1, 2, 3);
    sc_mld mld(876, "TestDevice", 1024, 8080);
    mbox.addMld(mld);

    // Test case 1: Deleting a non-existent sc_sld
    sc_mld nonExistentMld(456, "NonExistentDevice", 2048, 9090);
    int result1 = mbox.mbox_delete_mld(nonExistentMld);
    ASSERT_EQ(result1, -ENOENT);

    // Test case 4: Deleting the originally added sc_sld (success case)
    int result4 = mbox.mbox_delete_mld(mld);
    ASSERT_EQ(result4, 0);
}

