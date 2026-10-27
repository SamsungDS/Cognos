#include <errno.h>
#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include "sc_a1.h"
#include "sc_device.h"
#include "sc_host.h"
#include "sc_liqid.h"
#include "sc_mbox.h"
#include "sc_mld.h"
#include "sc_sld.h"

using ::testing::Return;
using namespace std;

int update_json_and_install() {
  // simulate success
  return 0;
}

class MockScLiqid : public sc_mbox {
 public:
  MockScLiqid(uint64_t mb_id, uint64_t mb_fm_id, sc_switch mb_switch)
      : sc_mbox(mb_id, mb_fm_id, mb_switch) {}
};

class ScLiqidTest : public ::testing::Test {
 protected:
  void SetUp() override {
    switch_instance = sc_switch(42);
    liqid = new sc_liqid(123, 456, switch_instance);
  }

  void TearDown() override { delete liqid; }

  sc_switch switch_instance;
  sc_liqid* liqid;
  MockScLiqid* mock_liqid;
};

TEST_F(ScLiqidTest, DefaultConstructorTest) {
  sc_liqid liqid;
  ASSERT_EQ(liqid.d_get_id().get_sc_id(), 0);
}

TEST_F(ScLiqidTest, ParameterizedConstructorTest) {
  ASSERT_EQ(liqid->d_get_id().get_sc_id(), 123);
}

TEST_F(ScLiqidTest, GetIdTest) {
  sc_liqid liqid(101, 202, 303);
  uint64_t result = liqid.d_get_id().get_sc_id();
  ASSERT_EQ(result, 101);
}

TEST_F(ScLiqidTest, GetCompositeObjTest) {
  sc_liqid liqid(101, 202, 303);

  sc_id result = liqid.d_get_id();

  ASSERT_EQ(result, sc_id(101));
}

TEST_F(ScLiqidTest, ListConnectedSldsTest) {
  sc_liqid liqid(1, 2, 3);
  sc_sld sld1(123, "TestDevice", 1024, 8080);
  sc_sld sld2(456, "TestDevice2", 1024, 8081);
  liqid.addSld(sld1);
  liqid.addSld(sld2);

  list<sc_sld> result = liqid.mbox_list_connected_slds();

  ASSERT_EQ(result.size(), 2);
}

TEST_F(ScLiqidTest, ListConnectedMldsTest) {
  sc_liqid liqid(1, 2, 3);
  sc_mld mld1(123, "TestDevice", 1024, 8080);
  sc_mld mld2(456, "TestDevice2", 1024, 8081);
  liqid.addMld(mld1);
  liqid.addMld(mld2);
  list<sc_mld> result = liqid.mbox_list_connected_mlds();
  ASSERT_EQ(result.size(), 2);
}

TEST_F(ScLiqidTest, CreateMldTest) {
  sc_liqid liqid(1, 2, 3);
  sc_mld result = liqid.mbox_create_mld(1024);
  ASSERT_NE(result, sc_mld{});
  ASSERT_TRUE(result.d_get_capacity() > 0);
}

TEST_F(ScLiqidTest, DeleteMldTest) {
  sc_liqid liqid(1, 2, 3);
  sc_mld mld(123, "TestDevice", 1024, 8080);
  liqid.addMld(mld);
  int result = liqid.mbox_delete_mld(mld);
  ASSERT_EQ(result, 0);
}

TEST_F(ScLiqidTest, CreateSldTest) {
  sc_liqid liqid(1, 2, 3);
  sc_sld result = liqid.mbox_create_sld(1024);
  ASSERT_NE(result, sc_sld{});
  ASSERT_TRUE(result.d_get_capacity() > 0);
}

TEST_F(ScLiqidTest, DeleteSldTest) {
  sc_liqid liqid(1, 2, 3);
  sc_sld sld(123, "TestDevice", 1024, 8080);
  liqid.addSld(sld);
  int result = liqid.mbox_delete_sld(sld);
  ASSERT_EQ(result, 0);
}

TEST_F(ScLiqidTest, DeleteSldTest_neg) {
  sc_liqid liqid(1, 2, 3);
  sc_sld sld(123, "TestDevice", 1024, 8080);
  liqid.addSld(sld);

  // Test case 1: Deleting a non-existent sc_sld
  sc_sld nonExistentSld(456, "NonExistentDevice", 2048, 9090);
  int result1 = liqid.mbox_delete_sld(nonExistentSld);
  ASSERT_EQ(result1, -ENOENT);

  // Test case 4: Deleting the originally added sc_sld (success case)
  int result4 = liqid.mbox_delete_sld(sld);
  ASSERT_EQ(result4, 0);
}

TEST_F(ScLiqidTest, DeviceIdExistsInSlds) {
  sc_sld sld(123, "TestDevice", 1024, 8080);
  liqid->addSld(sld);
  int result = liqid->fetch_device_port(sld.d_get_id().get_sc_id());
  ASSERT_EQ(result, sld.d_get_port());
}

TEST_F(ScLiqidTest, DeviceIdExistsInMlds) {
  sc_mld mld(456, "AnotherDevice", 2048, 9090);
  liqid->addMld(mld);
  int result = liqid->fetch_device_port(mld.d_get_id().get_sc_id());
  ASSERT_EQ(result, mld.d_get_port());
}

// Test case: Get switch information
TEST_F(ScLiqidTest, GetSwitchInfoTest) {
  string result = liqid->mbox_get_switch_info();

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

TEST_F(ScLiqidTest, AttachDeviceToHostTest) {
  sc_sld sld(123, "DEV_11-256G", 1024, 11);
  sc_host host(456);
  host.set_host_name("Host 1 LNK0");
  host.set_host_port(2);
  liqid->addSld(sld);
  liqid->addHost(host);
  int result = liqid->d_attach(sld.d_get_id().get_sc_id(),
                               host.d_get_id().get_sc_id(), "test");
  ASSERT_EQ(result, 0);
  auto hosts_map = liqid->get_hosts_map();
  ASSERT_TRUE(hosts_map.find(host.d_get_id()) != hosts_map.end());
}

TEST_F(ScLiqidTest, AttachDeviceToHostTestNeg) {
  sc_sld sld(123, "DEV_11-256G", 1024, 11);
  sc_host host(456);
  host.set_host_name("Host 1 LNK0");
  host.set_host_port(2);
  liqid->addSld(sld);
  liqid->addHost(host);
  int result = liqid->d_attach(555, host.d_get_id().get_sc_id(), "test");
  ASSERT_EQ(result, -2);
  int result1 = liqid->d_attach(sld.d_get_id().get_sc_id(), 555, "test");
  ASSERT_EQ(result1, -2);
}

TEST_F(ScLiqidTest, DetachDeviceToHostTest) {
  sc_sld sld(123, "DEV_11-256G", 1024, 11);
  sc_host host(456);
  host.set_host_name("Host 1 LNK0");
  host.set_host_port(2);
  liqid->addSld(sld);
  liqid->addHost(host);
  liqid->d_attach(sld.d_get_id().get_sc_id(), host.d_get_id().get_sc_id(),
                  "test");
  int result = liqid->d_detach(sld.d_get_id().get_sc_id(),
                               host.d_get_id().get_sc_id(), "test");
  ASSERT_EQ(result, 0);
  auto hosts_map = liqid->get_hosts_map();
  ASSERT_TRUE(hosts_map.find(host.d_get_id()) != hosts_map.end());
}

TEST_F(ScLiqidTest, DetachDeviceToHostTestNeg) {
  sc_sld sld(123, "DEV_11-256G", 1024, 11);
  sc_host host(456);
  host.set_host_name("Host 1 LNK0");
  liqid->addSld(sld);
  liqid->addHost(host);
  liqid->d_attach(sld.d_get_id().get_sc_id(), host.d_get_id().get_sc_id(),
                  "test");
  int result = liqid->d_detach(sld.d_get_id().get_sc_id(), 777, "test");
  ASSERT_EQ(result, -2);
}

TEST_F(ScLiqidTest, GetSldsMap) {
  sc_sld sld(789, "DEV_11-256G", 1024, 11);
  sc_id sld_id = sld.d_get_id();
  liqid->addSld(sld);
  auto slds_map = liqid->get_slds_map();
  ASSERT_EQ(slds_map[sld_id].d_get_id(), sld.d_get_id());
}

TEST_F(ScLiqidTest, GetMldsMap) {
  sc_mld mld(789, "DEV_11-256G", 1024, 11);
  sc_id mld_id = mld.d_get_id();
  liqid->addMld(mld);
  auto mlds_map = liqid->get_mlds_map();
  ASSERT_EQ(mlds_map[mld_id].d_get_id(), mld.d_get_id());
}

TEST_F(ScLiqidTest, GetPDevMap) {
  sc_sld sld(789, "DEV_11-256G", 1024, 11);
  liqid->addSld(sld);
  sc_id sld_id = sld.d_get_id();
  uint32_t port = sld.d_get_port();
  auto pdev_map = liqid->get_pdev();
  ASSERT_EQ(pdev_map[port].get_sc_id(), sld_id.get_sc_id());
}

TEST_F(ScLiqidTest, GetPHostMap) {
  sc_id s_id(789);
  uint32_t host_key = 1;
  liqid->get_phost()[host_key].push_back(s_id);
  auto phost_map = liqid->get_phost();
  ASSERT_EQ(phost_map[host_key].front().get_sc_id(), s_id.get_sc_id());
}

TEST_F(ScLiqidTest, GetDIdsMap) {
  sc_sld sld(789, "DEV_11-256G", 1024, 11);
  liqid->addSld(sld);
  auto d_ids_map = liqid->get_d_ids();
  ASSERT_EQ(d_ids_map[789].get_sc_id(), sld.d_get_id().get_sc_id());
}

TEST_F(ScLiqidTest, DeleteDIdsFailure) {
  sc_device dobj(789, "DEV_11-256G", 1024, 11);
  int result = liqid->delete_d_ids(dobj);
  EXPECT_EQ(result, -ENOENT);
}

TEST_F(ScLiqidTest, DeletePDevFailure) {
  sc_device dobj(799, "DEV_11-256G", 1024, 11);
  int result = liqid->delete_pdev(dobj);
  EXPECT_EQ(result, -ENOENT);
}

TEST_F(ScLiqidTest, DeletePDevSuccess) {
  sc_sld sld(799, "DEV_11-256G", 1024, 11);
  liqid->addSld(sld);
  int result = liqid->delete_pdev(sld);
  EXPECT_EQ(result, 0);
}

TEST_F(ScLiqidTest, DeleteDIdsSuccess) {
  sc_sld sld(789, "DEV_11-256G", 1024, 11);
  liqid->addSld(sld);
  int result = liqid->delete_d_ids(sld);
  EXPECT_EQ(result, 0);
}

TEST_F(ScLiqidTest, DeleteMldTest_neg) {
  sc_liqid liqid(1, 2, 3);
  sc_mld mld(876, "TestDevice", 1024, 8080);
  liqid.addMld(mld);

  // Test case 1: Deleting a non-existent sc_sld
  sc_mld nonExistentMld(456, "NonExistentDevice", 2048, 9090);
  int result1 = liqid.mbox_delete_mld(nonExistentMld);
  ASSERT_EQ(result1, -ENOENT);

  // Test case 4: Deleting the originally added sc_sld (success case)
  int result4 = liqid.mbox_delete_mld(mld);
  ASSERT_EQ(result4, 0);
}
