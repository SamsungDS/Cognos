#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <chrono>
#include <fstream>
#include <future>

#include "collector.h"

using namespace std;

// Helper function to create temporary files
void create_file(const std::string& file_name, const std::string& content) {
  std::ofstream file(file_name);
  file << content;
  file.close();
}

class CollectorTest : public ::testing::Test {
 protected:
  Collector c;

  void SetUp() override {
    c = Collector();
    string zmq_config = R"({
  "svk_cxl_host_node":
      {
        "ip": "127.0.0.1",
        "port": "5556"
      }
  })";
    create_file("zmq_config.json", zmq_config);
    string zmq_config_prob = R"({
  "svk_cxl_host_node":
      {
        "ip": "127.0.0.1",
        "port": "5555"
      }
  })";
    create_file("zmq_config_prob.json", zmq_config_prob);
  }
};

// Helper worker function for polling an atomic variable
void w1(int& v) {
  while (1) {
    // Access the global variable safely
    v = c_flag.load();
    if (v > 0) return;

    // Sleep to avoid CPU usage at 100%
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }
}

TEST_F(CollectorTest, CheckBindAddr) {
  // Test wrong conf filename
  EXPECT_EQ(get_zmq_bindaddr("invalid_json"), "");
  EXPECT_NE(get_zmq_bindaddr("zmq_config.json"), "");
  EXPECT_EQ(get_zmq_bindaddr("zmq_config.json"), "tcp://127.0.0.1:5556");
}

TEST_F(CollectorTest, CheckConstructorAndRun) {
  EXPECT_THROW(Collector("", "Collector", _run), std::runtime_error);

  string addr = get_zmq_bindaddr(SVK_CXL_HOST_IP_CONFIG_TEST);
  auto r = Collector(addr.c_str(), "Collector", _run);
  EXPECT_TRUE((is_same_v<decltype(r), Collector>));

  int val = 0;
  c_flag.store(val);
  thread t2(_run, (void*)(&r));
  thread t1(w1, ref(val));
  t2.detach();
  t1.join();
  EXPECT_NE(val, 0);
}

TEST_F(CollectorTest, CheckConstructorAndRun2) {
  c_flag.store(0);
  thread t1(_run, (void*)(nullptr));
  t1.join();
  int val = c_flag.load();
  EXPECT_EQ(val, 0);
}

TEST_F(CollectorTest, CheckConstructorAndRun3) {
  string addr = get_zmq_bindaddr(SVK_CXL_HOST_IP_CONFIG_TEST);
  auto r = Collector(addr.c_str(), "Collector", _run);
  EXPECT_TRUE((is_same_v<decltype(r), Collector>));

  r.c_pub = nullptr;
  int val = 0;
  c_flag.store(val);
  thread t2(_run, (void*)(&r));
  thread t1(w1, ref(val));
  t2.detach();
  t1.join();
  EXPECT_NE(val, 0);
}

TEST_F(CollectorTest, CheckConstructorAndRun4) {
  string b_addr = get_zmq_bindaddr("zmq_config_prob.json");
  auto c1 = Collector(b_addr.c_str(), "Collector", _run);
  EXPECT_TRUE((is_same_v<decltype(c1), Collector>));

  int val = 0;
  c_flag.store(val);
  thread t2(_run, (void*)(&c1));
  thread t1(w1, ref(val));
  t2.detach();
  t1.join();
  EXPECT_NE(val, 0);
}

/*TEST_F(CollectorTest, CheckSvcRegistration) {
  EXPECT_EQ(register_svk_service(nullptr), -1);
  namespace pt = boost::property_tree;
  pt::ptree root;
  pt::read_json(SVK_CXL_HOST_IP_CONFIG_TEST, root);
  pt::ptree host_ip_info = root.get_child(SVK_CXL_HOST_TAG);
  host_ip_info.put("ip", "0.0.0.0");
  EXPECT_EQ(register_svk_service(nullptr), -2);
  host_ip_info.put("ip", "127.0.0.1");
}*/

TEST_F(CollectorTest, CheckSvc) {
  try {
    c.ServiceStart();
  } catch (const std::exception& e) {
    EXPECT_STREQ("test_ServiceStart", e.what());
  }

  try {
    c.ServiceStop();
  } catch (const std::exception& e) {
    EXPECT_STREQ("test_ServiceStop", e.what());
  }
}
