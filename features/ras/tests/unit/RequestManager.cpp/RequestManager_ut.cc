#include <RequestManager.h>  // Include the RequestManager class
#include <gtest/gtest.h>
#include <unistd.h>

#include <thread>

class TestRequest {
 public:
  TestRequest(int data) : data_(data) {}

  int getData() const { return data_; }

 private:
  int data_;
};

TEST(RequestManagerTest, EnqueueIntoRing) {
  RequestManager<TestRequest>* manager =
      new RequestManager<TestRequest>("test_buffer", 2);
  TestRequest* request = new TestRequest(1);
  TestRequest* popped_request = nullptr;
  // Enqueue into the ring
  manager->enqueue(request);
  popped_request = manager->dequeue();
  ASSERT_EQ(popped_request, request);
  // std::cout << manager.dequeue() << std::endl;
  delete (manager);
  delete (request);
}

TEST(RequestManagerTest, FlushBuffer) {
  RequestManager<TestRequest> manager("test_buffer", 2);
  TestRequest request1 = TestRequest(1);
  TestRequest request2 = TestRequest(2);
  TestRequest request3 = TestRequest(3);
  TestRequest request4 = TestRequest(4);
  TestRequest* popped_request = nullptr;
  // Enqueue into the ring
  manager.enqueue(&request1);
  manager.enqueue(&request2);
  manager.enqueue(&request3);
  manager.enqueue(&request4);

  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &request1);
  manager.flushFallbackBuffer();
  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &request2);
  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &request3);
  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &request4);
  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, nullptr);
}

TEST(RequestManagerTest, FailZeroCount) {
  try {
    RequestManager<TestRequest> manager("test_buffer", -100);
  } catch (std::runtime_error& e) {
    std::cout << e.what() << std::endl;
    ;
    ASSERT_STREQ(e.what(), "Failed to create ring");
  }
}

TEST(RequestManagerTest, PushAfterPopEmpty) {
  RequestManager<TestRequest> manager("test_buffer", 2);
  TestRequest* popped_request = nullptr;
  TestRequest item = TestRequest(1);

  // Enqueue into the ring
  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, nullptr);

  manager.enqueue(&item);

  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &item);
}

TEST(RequestManagerTest, DequeueFromFallbackbuffer) {
  RequestManager<TestRequest> manager("test_buffer", 1);
  TestRequest* popped_request = NULL;
  TestRequest item1 = TestRequest(1);
  TestRequest item2 = TestRequest(1);

  manager.enqueue(&item1);
  manager.enqueue(&item2);

  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &item1);

  popped_request = manager.dequeue();
  ASSERT_EQ(popped_request, &item2);
}