#include <gtest/gtest.h>
#include "sc_switch.h"

TEST(ScSwitchTest, DefaultConstructor) {
    sc_switch mySwitch;
    // Verify that default properties are set correctly
    EXPECT_EQ(mySwitch.to_json(), "{\n  \"SwitchID\": 0,\n  \"Manufacturer\": \"\",\n  \"UpstreamPorts\": 0,\n  \"DownstreamPorts\": 0,\n  \"ManagementPort\": 0\n}");
}

TEST(ScSwitchTest, ParameterizedConstructor) {
    uint64_t switchId = 12345;
    sc_switch mySwitch(switchId);
    // Verify that switch ID is correctly set
    EXPECT_EQ(mySwitch.to_json(), "{\n  \"SwitchID\": 12345,\n  \"Manufacturer\": \"\",\n  \"UpstreamPorts\": 0,\n  \"DownstreamPorts\": 0,\n  \"ManagementPort\": 0\n}");
}

TEST(ScSwitchTest, ToJson) {
    sc_switch mySwitch(9876);
    mySwitch.set_manufacturer("MyCompany");
    mySwitch.set_upstream_ports(4);
    mySwitch.set_downstream_ports(8);
    mySwitch.set_mgmt_port(8080);

    // Verify that JSON representation is correct
    EXPECT_EQ(mySwitch.to_json(), "{\n  \"SwitchID\": 9876,\n  \"Manufacturer\": \"MyCompany\",\n  \"UpstreamPorts\": 4,\n  \"DownstreamPorts\": 8,\n  \"ManagementPort\": 8080\n}");
}

TEST(ScSwitchTest, GetManufacturer) {
    sc_switch mySwitch;
    mySwitch.set_manufacturer("MyCompany");
    EXPECT_EQ(mySwitch.get_manufacturer(), "MyCompany");
}

TEST(ScSwitchTest, GetUpstreamPorts) {
    sc_switch mySwitch;
    mySwitch.set_upstream_ports(4);
    EXPECT_EQ(mySwitch.get_upstream_ports(), 4);
}


TEST(ScSwitchTest, GetDownstreamPorts) {
    sc_switch mySwitch;
    mySwitch.set_downstream_ports(8);
    EXPECT_EQ(mySwitch.get_downstream_ports(), 8);
}

TEST(ScSwitchTest, GetMgmtPort) {
    sc_switch mySwitch;
    mySwitch.set_mgmt_port(8080);
    EXPECT_EQ(mySwitch.get_mgmt_port(), 8080);
}

