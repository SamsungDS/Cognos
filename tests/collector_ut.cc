#include <gtest/gtest.h>
#include <gmock/gmock.h>

#include "collector.h"

using namespace std;

class CollectorTest : public ::testing::Test
{
	protected:
		Collector c;
 
		void SetUp() override
		{
			c = Collector();
  		}
};

TEST_F(CollectorTest, CheckBindAddr)
{
	// Test wrong conf filename
  	EXPECT_EQ(get_zmq_bindaddr("invalid_json"), "");
  	EXPECT_NE(get_zmq_bindaddr("zmq_config.json"), "");
	EXPECT_EQ(get_zmq_bindaddr("zmq_config.json"), "tcp://127.0.0.1:5555");
}

TEST_F(CollectorTest, CheckConstructor)
{
	EXPECT_THROW(Collector("", "Collector", _run), std::runtime_error);
	EXPECT_THROW(Collector("tcp://localhost:5555", "Collector", _run), std::runtime_error);
	EXPECT_NO_THROW(Collector("tcp://127.0.0.1:5555", "Collector", _run));
}

TEST_F(CollectorTest, CheckRun)
{
	EXPECT_EQ(_run(nullptr), nullptr);
	Collector cc = Collector("tcp://127.0.0.1:5555", "Collector", _run);
	try
	{
		_run((void*)&(cc));
	}
	catch(const std::exception& e)
	{
		EXPECT_STREQ("test", e.what());
	}
        
        cc.c_pub = nullptr;
        EXPECT_THROW(_run((void*)&(cc)),  std::runtime_error);    
}

TEST_F(CollectorTest, CheckSvcRegistration)
{
       	EXPECT_EQ(register_svk_service(nullptr), -1);
	namespace pt = boost::property_tree;
	pt::ptree root;
	pt::read_json(SVK_CXL_HOST_IP_CONFIG_TEST, root);
	pt::ptree host_ip_info = root.get_child(SVK_CXL_HOST_TAG);
	host_ip_info.put("ip", "0.0.0.0");
	EXPECT_EQ(register_svk_service(nullptr), -2);
	host_ip_info.put("ip", "127.0.0.1");
}

TEST_F(CollectorTest, CheckSvc)
{
	try
	{
		c.ServiceStart();
	}
	catch(const std::exception& e)
	{
		EXPECT_STREQ("test_ServiceStart", e.what());
	}

	try
	{
		c.ServiceStop();
	}
	catch(const std::exception& e)
	{
		EXPECT_STREQ("test_ServiceStop", e.what());
	}
}
