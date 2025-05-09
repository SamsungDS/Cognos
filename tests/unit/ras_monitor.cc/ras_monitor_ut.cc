#include <gtest/gtest.h>
#include <ras_monitor.h>

TEST(RasMonitorTest, TestClass) {
  std::unique_ptr<ras_monitor> test_mon_inst = std::make_unique<ras_monitor>();
  std::string instr =
      R"({"command": "getErrorCount", "device": 0, "type": "correctable"})";
  char out[2048];
  std::string outstr;
  outstr.assign(out);
  ras_request *dummy_request =
      new ras_request(false, true, instr, outstr, test_mon_inst.get());
  bool result = false;

  result = test_mon_inst->ras_submit_request(nullptr);
  ASSERT_EQ(false, result);

  result = test_mon_inst->ras_submit_request(dummy_request);
  ASSERT_EQ(true, result);

  delete dummy_request;
}

TEST(RasMonitorTest, ProcessRequestSync) {
  std::unique_ptr<ras_monitor> test_mon_inst = std::make_unique<ras_monitor>();
  ras_monitor rm;
  std::string instr =
      R"({"command": "getErrorCount", "device": 0, "type": "correctable"})";
  char out[2048];
  strcpy(out, "");
  std::string outstr;
  outstr.assign(out);
  ras_request *dummy_request =
      new ras_request(false, true, instr, outstr, test_mon_inst.get());

  proc_req(rm, nullptr);
  ASSERT_EQ(strcmp(dummy_request->output.c_str(), ""), 0);

  proc_req(rm, dummy_request);
  ASSERT_EQ(strcmp(dummy_request->output.c_str(), "getErrorCount"), 0);

  std::string instr_1 =
      R"({"command": "getErrorCount", "device" 0, "type": "correctable"})";
  ras_request *dummy_request_1 =
      new ras_request(false, true, instr_1, outstr, test_mon_inst.get());

  proc_req(rm, dummy_request_1);
  ASSERT_EQ(strcmp(dummy_request_1->output.c_str(), ""), 0);

  std::string instr_2 = R"(A sample RAS string)";
  ras_request *dummy_request_2 =
      new ras_request(false, true, instr_2, outstr, test_mon_inst.get());

  proc_req(rm, dummy_request_2);
  ASSERT_EQ(strcmp(dummy_request_2->output.c_str(), ""), 0);

  delete dummy_request;
  delete dummy_request_1;
  delete dummy_request_2;
}
