#include <gtest/gtest.h>
#include "sc_endpoint.h" 

class EndpointTest : public ::testing::Test {
protected:
    endpoint ep;

    void SetUp() override {
        ep.set_endpoint("http://example.com");
    }
};

// Test the get_endpoint() function
TEST_F(EndpointTest, GetEndpoint) {
    EXPECT_EQ(ep.get_endpoint(), "http://example.com");
}

// Test the set_endpoint() function
TEST_F(EndpointTest, SetEndpoint) {
    ep.set_endpoint("https://api.example.com");
    EXPECT_EQ(ep.get_endpoint(), "https://api.example.com");
}
