#include <RequestProcessor.h>  // Include the RequestManager class
#include <gtest/gtest.h>

class TestRequest {
 public:
  TestRequest(int data) : data_(data) {}

  int getData() const { return data_; }

 private:
  int data_;
};

#define TEST_DATA 100
void cb(TestRequest* req) {
  int cb_data = req->getData();
  ASSERT_EQ(cb_data, TEST_DATA);
}

TEST(RequestProcessorTest, TestClass) {
  RequestProcessor<TestRequest> rp(cb);
  TestRequest req(TEST_DATA);
  rp.submitRequest(&req);
  std::this_thread::sleep_for(std::chrono::milliseconds(1000));
}