#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "cme_global.h"
#include "cme_utils.h"
#include "cme_init.h"
#include "framework_downstream.h"
#include <numa.h>
#include <numaif.h>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>

extern "C"{
#include "jansson.h"
}

using namespace std;

class cmeTest : public ::testing::Test {
        protected:
      
         void SetUp() override {}
};

TEST_F(cmeTest, GetSupportedFeatureListTest) {
  feature_id feat_id;
  char feature_names[256];
  svk_status status = get_supported_feature_list(&feat_id, feature_names);
  ASSERT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(cmeTest, IsLicenseValidTest) {
  svk_status status = is_license_valid(nullptr);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(cmeTest, ConfigureDeviceIfAnyTest) {
  svk_device_ctx device_handles;
  void* config_details = nullptr;
  uint64_t length = 0;
  void* resp = nullptr;
  svk_status status =
      configure_device_if_any(config_details, &device_handles, length, resp);
  ASSERT_EQ(status, SVK_STATUS_SUCCESS);
}

TEST_F(cmeTest, ExecuteAsyncTest) {
    svk_pass_thru_cmd pass_thru;
    svk_postprocess_fn postprocess_fn;
    svk_status status = execute_async(&pass_thru, &postprocess_fn);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}

TEST_F(cmeTest, CleanUpTest) {
    svk_status status = clean_up(nullptr);
    ASSERT_EQ(status, SVK_STATUS_FAIL);
}


TEST_F(cmeTest, TokenizeTest) {
    string input = "key1=value1;key2=value2;key3=value3";
    unordered_map<string, string> tokens = tokenize(input);
    EXPECT_EQ(tokens.size(), 3);
    EXPECT_EQ(tokens["key1"], "value1");
    EXPECT_EQ(tokens["key2"], "value2");
    EXPECT_EQ(tokens["key3"], "value3");
}

TEST_F(cmeTest, TokenHelperTest) {
    string input = "key1=value1;key2=value2;key3=value3";
    unordered_map<string, string> tokens = token_helper(input);
    EXPECT_EQ(tokens.size(), 3);
    EXPECT_EQ(tokens["key1"], "value1");
    EXPECT_EQ(tokens["key2"], "value2");
    EXPECT_EQ(tokens["key3"], "value3");
}

TEST_F(cmeTest, CommandParserJsonTestt) {
    namespace pt = boost::property_tree;
    pt::ptree root;
    root.put("command_name", "test_command");
    pt::ptree child_node;
    child_node.put("param_1", "value_1");
    child_node.put("param_2", "value_2");
    root.add_child("command_params", child_node);
    std::stringstream json_stream;
    pt::write_json(json_stream, root);
    std::string json_string = json_stream.str();
    unordered_map<string, string> command_params_map;

    EXPECT_TRUE(command_parser_json(json_string, command_params_map));
    EXPECT_EQ(command_params_map["command"], "test_command");
    EXPECT_EQ(command_params_map["param_1"], "value_1");
    EXPECT_EQ(command_params_map["param_2"], "value_2");

    command_params_map.clear();
    std::string invalid_json_string = "{\"tm_attr\":\"0\",\"app\":\"test\",\"app_pid\":\"107626\",\"src\":\"2\",\"dst\":\"1\",,}";
    EXPECT_FALSE(command_parser_json(invalid_json_string, command_params_map));
}


TEST_F(cmeTest, ExecuteSyncInvalidCommandTest) {
    svk_input input;
    svk_output output;
    svk_pass_thru_cmd pass_thru;
    input.input_buffer = reinterpret_cast<uint8_t*>(strdup("command=InvalidCommand"));
    input.len = strlen("command=InvalidCommand");
    svk_status status = execute_sync(&pass_thru, &input, &output);
    ASSERT_EQ(status, SVK_STATUS_FAIL); 
    free(input.input_buffer);
}

TEST_F(cmeTest, CheckInitialize) {
 	cme_global cme_global_obj;
	EXPECT_EQ(cme_global_obj.initialize(), 0);
}

TEST_F(cmeTest, CheckInvalidCommand) {
        cme_global cme_global_obj;
        string invalidcommand = "command=InvalidCommand;app=gemfire;app_pid=363043;src=0;dst=1;sla_iops=150000;sla_size=1024;sla_latencyus=750";
	EXPECT_THROW(cme_global_obj.cme_command_handler(invalidcommand), std::runtime_error);
}

TEST_F(cmeTest, CheckCmeInitialization) {
	cme_global cme_global_obj;
	EXPECT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	EXPECT_EQ(cme_global_obj.cme_discovery(), 0);
	EXPECT_EQ(cme_global_obj.initialize(), 0);
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}




TEST_F(cmeTest, CheckCmdMoveAllFlatStringInput) {
        cme_global cme_global_obj;
	ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
	int pid = getpid();

	// move_all: Test mover busy for context using dummy mover
	string command = "command=move_all;tm_attr=cme_mover_dummy;app=test;app_pid="  + to_string(pid) + ";src=0;dst=0";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EBUSY));
	// get_status: Test mover busy for context using dummy mover
	command = "command=get_status;app=test;app_pid=" + to_string(pid);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EBUSY));
	std::this_thread::sleep_for(std::chrono::seconds(4));
	
	// move_all: Test valid context name and expected move_all success
	command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(4));
	// get_status: Test valid context name and expected move_all success
	command = "command=get_status;app=test;app_pid=" + to_string(pid);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

	// get_status: Test invalid context name (wrong pid)
	command = "command=get_status;app=test;app_pid=" + to_string(pid-1);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

	// move_all: Test invalid pid, valid numa node for numa_move_all mover
	command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(-1) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	// get_status: Test invalid pid, valid numa node for numa_move_all mover
	command = "command=get_status;app=test;app_pid=" + to_string(-1);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-ESRCH));

	// move_all: Test valid pid, invalid numa node for numa_move_all mover
	unsigned int numa_count_conf = numa_num_configured_nodes();
	command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(pid) + ";src=0;dst=" + to_string(numa_count_conf);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	// get_status: Test valid pid, invalid numa node for numa_move_all mover
	command = "command=get_status;app=test;app_pid=" + to_string(pid);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
        
	// move_all: is_cmd_valid_move_all fail
	command = "command=move_all;app=test;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
	command = "command=move_all;tm_attr=1;app=test;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

	//move_all: is_cmd_valid_move_all fail for existing context
	command = "command=move_all;tm_attr=0;app=test1;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(4));
        command = "command=get_status;app=test1;app_pid=" + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	command = "command=move_all;tm_attr=1;app=test1;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);

}

TEST_F(cmeTest, CheckCmdMoveAllJsonStringInput) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();
	string command = " {\"command_name\": \"move_all\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"tm_attr\": \"cme_mover_dummy\", \"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"src\": \"0\", \"dst\": \"1\"},\"cluster_id\": \"CL_ID_3\",\"node_id\": \"localhost\"} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EBUSY));
	command = " {\"command_name\": \"get_status\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EBUSY));
        std::this_thread::sleep_for(std::chrono::seconds(4));

	command = " {\"command_name\": \"move_all\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"tm_attr\": \"0\", \"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"src\": \"0\", \"dst\": \"0\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(4));
	command = " {\"command_name\": \"get_status\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	command = " {\"command_name\": \"get_status\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid-1) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
	command = " {\"command_name\": \"move_all\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"tm_attr\": \"0\", \"app\": \"test\", \"app_pid\":\"" + to_string(-1) + "\", \"src\": \"0\", \"dst\": \"0\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	command = " {\"command_name\": \"get_status\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(-1) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-ESRCH));
	unsigned int numa_count_conf = numa_num_configured_nodes();
	command = " {\"command_name\": \"move_all\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"tm_attr\": \"0\", \"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"src\": \"0\", \"dst\":\"" + to_string(numa_count_conf) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	command = " {\"command_name\": \"get_status\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdMove) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command mover_aggressiveness low
        string command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
       
        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdMoveAggr) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command mover_aggressiveness low
        string command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check valid command, mover_aggressiveness high
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_HIGH\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check valid command, mover_aggressiveness invalid
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"invalid_input\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        // Check valid command, mover_aggressiveness invalid blank
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
       
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdMoveHot) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command
        string command = " {\"command_name\": \"move_hot\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdMoveCold) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command
        string command = " {\"command_name\": \"move_cold\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdStartTuning) {
        cme_global cme_global_obj;
	ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
	int pid = getpid();

        // Check valid command
	string command = "command=StartTuning;application=test;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check stop
        command = "command=StopTuning;application=test;application_id="  + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdGetStats) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command
        string command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
       
        // Check get_stats
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), "");

        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check get_stats, no context
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command),  to_string(-EINVAL));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

