#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include "cme_global.h"
#include "cme_init.h"
#include "cme_utils.h"
#include "cme_publisher.h"
#include "framework_downstream.h"
#include <numa.h>
#include <numaif.h>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>

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

TEST_F(cmeTest, CommandParserJsonTest) {
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

TEST_F(cmeTest, ExecuteCommandTest) {
        vector<string> output;
        string cmd = "invalid_command";
        EXPECT_NE(execute_command(cmd, output, false), 0);
        cmd = "ls";
        EXPECT_EQ(execute_command(cmd, output, false), 0);
        EXPECT_NE(output.size(), 0);
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

TEST_F(cmeTest, CheckCmeInitialization) {
	cme_global cme_global_obj;
	EXPECT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	EXPECT_EQ(cme_global_obj.cme_discovery(), 0);
	EXPECT_EQ(cme_global_obj.initialize(), 0);
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmeDiscovery) {
	cme_global cme_global_obj;
        string path = "invalid_path";
	EXPECT_EQ(cme_global_obj._cme_discovery(path, CME_MOVER), -EINVAL);
        EXPECT_EQ(cme_global_obj._cme_discovery("movers", CME_INVALID_TYPE), -EINVAL);
        ASSERT_EQ(cme_global_obj.cme_discovery(), -EINVAL);
        EXPECT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        cme_global_obj.movers_lib.clear();
        ASSERT_EQ(cme_global_obj.cme_discovery(), -EINVAL);
        EXPECT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        cme_global_obj.profilers_lib.clear();
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
}

TEST_F(cmeTest, CheckCmeRegister) {
	cme_global cme_global_obj;
        string mover_ = "numa_move_all";
	EXPECT_NO_THROW(cme_global_obj.mover_register(mover_, NULL));
        EXPECT_NO_THROW(cme_global_obj.profiler_register(mover_, NULL));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckInvalidCommand) {
        cme_global cme_global_obj;
        //Check invalid command
        string command = "command=InvalidCommand;app=gemfire;app_pid=363043;src=0;dst=1;sla_iops=150000;sla_size=1024;sla_latencyus=750";
	EXPECT_THROW(cme_global_obj.cme_command_handler(command), std::runtime_error);
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmeFindMover) {
	cme_global cme_global_obj;
	EXPECT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	EXPECT_EQ(cme_global_obj.cme_discovery(), 0);
	EXPECT_EQ(cme_global_obj.initialize(), 0);
        cme_context ctx;
        EXPECT_EQ(cme_global_obj.cg_find_mover(&ctx), nullptr);
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmeFindContext) {
	cme_global cme_global_obj;
	EXPECT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	EXPECT_EQ(cme_global_obj.cme_discovery(), 0);
	EXPECT_EQ(cme_global_obj.initialize(), 0);
        unordered_map<string, string> tokens_map;
        tokens_map.try_emplace("command", "testcommand");
        EXPECT_EQ(cme_global_obj.cg_find_context(tokens_map, false), nullptr);
        EXPECT_EQ(cme_global_obj.cg_find_context(tokens_map, true), nullptr);
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmePublisher) {
        std::string app_ctx = "test_1234";
        namespace pt = boost::property_tree;
        pt::ptree root;
        root.put("test_event", "event_data");
        std::stringstream json_stream;
        pt::write_json(json_stream, root);
        std::string event_data = json_stream.str();
        // For now we publisher function returns exception/failure.
        EXPECT_NE(publish_cme_event(app_ctx, event_data, getCurrentTimestamp()), 0);
}

TEST_F(cmeTest, CheckCmdValidMoveAll) {
        cme_global cme_global_obj;
	ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
	int pid = getpid();
        // move_all: Test valid context name and expected move_all success
	std::string command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	// get_status: Test valid context name and expected move_all success
	command = "command=get_status;app=test;app_pid=" + to_string(pid);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

// ## Check move_all() API
TEST_F(cmeTest, CheckCmdMoveAllFlatString) {
        cme_global cme_global_obj;
	ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
	int pid = getpid();

        // trigger other mover functions with Dummy PID
	string command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(DUMMY_PID) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        std::this_thread::sleep_for(std::chrono::seconds(2));
        command = "command=stop;app=test;app_pid=" + to_string(DUMMY_PID);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = "command=get_status;app=test;app_pid=" + to_string(DUMMY_PID);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
	
	// move_all: Test valid context name and expected move_all success
	command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	// get_status: Test valid context name and expected move_all success
	command = "command=get_status;app=test;app_pid=" + to_string(pid);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

	// get_status: Test invalid context name (wrong pid)
	command = "command=get_status;app=test;app_pid=" + to_string(pid-1);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

	// move_all: Test invalid pid, valid numa node for numa_move_all mover
        int invalid_pid = get_invalid_pid();
	command = "command=move_all;tm_attr=0;app=test;app_pid=" + to_string(invalid_pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	// get_status: Test invalid pid, valid numa node for numa_move_all mover
	command = "command=get_status;app=test;app_pid=" + to_string(invalid_pid);
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
	std::this_thread::sleep_for(std::chrono::seconds(2));
        command = "command=get_status;app=test1;app_pid=" + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	command = "command=move_all;tm_attr=1;app=test1;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

	// move_all: Test valid context but no mover for it (erase mover)
	command = "command=move_all;tm_attr=0;app=test2;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	command = "command=get_status;app=test2;app_pid=" + to_string(pid);
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        
        // delete all movers , check move_all failure
        cme_global_obj.movers_list.clear();
        command = "command=move_all;tm_attr=0;app=test2;app_pid=" + to_string(pid) + ";src=0;dst=0";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
        
}

TEST_F(cmeTest, CheckCmdMoveAllJsonStringInput) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

	string command = " {\"command_name\": \"move_all\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"tm_attr\": \"0\", \"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"src\": \"0\", \"dst\": \"0\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
	std::this_thread::sleep_for(std::chrono::seconds(2));
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

// ## Check damo mover APIs..

TEST_F(cmeTest, CheckNoMoverStart) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();
        
        // delete movers
        cme_global_obj.movers_list.clear();
        // Check valid start command with no movers
	string command = "command=StartTuning;application=test;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckNoMoverStop) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
	ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid start command with no movers
	string command = "command=StartTuning;application=test;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // delete movers
        cme_global_obj.movers_list.clear();

        // Check valid stop with no movers
        command = "command=StopTuning;application=test;application_id="  + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdMove) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command move
        string command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check busy for existing move context
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EBUSY));

        // Check invalid stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        // Check stop no context
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test1\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        // Check valid stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check move with no movers
        cme_global_obj.movers_list.clear();
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test1\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        // Check invalid move command
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
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
        string command;

        // Check valid start
	command = "command=StartTuning;application=test;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check valid stop
        command = "command=StopTuning;application=test;application_id="  + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check invalid start
	command = "command=StartTuning;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        // Check stop invalid
	command = "command=StartTuning;application=test1;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = "command=StopTuning;application_id="  + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        // Check stop invalid context
	command = "command=StartTuning;application=test2;application_id="  + to_string(pid) + ";dram_node=0;cxl_node=1";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = "command=StopTuning;application=test3;application_id="  + to_string(pid);
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckCmdGetStats) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check stats for move_all
        string command = " {\"command_name\": \"move_all\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"tm_attr\": \"0\", \"app\": \"test1\", \"app_pid\":\"" + to_string(pid) + "\", \"src\": \"0\", \"dst\": \"0\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test1\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_NO_THROW(cme_global_obj.cme_command_handler(command));
	std::this_thread::sleep_for(std::chrono::seconds(2));
	command = " {\"command_name\": \"get_status\", \"feature_name\": \"me\", \"feature_id\": \"0\", \"command_params\": {\"app\": \"test1\", \"app_pid\":\"" + to_string(pid) + "\"},\"cluster_id\": \"CL_ID_1\",\"node_id\": \"localhost\"} ";
	EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test1\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_NO_THROW(cme_global_obj.cme_command_handler(command));

        // // Check stats for move
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
       
        // Check get_stats
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_NO_THROW(cme_global_obj.cme_command_handler(command));

        // Check stop
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check get_stats, no context
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command),  to_string(-EINVAL));

        // Get Stats exception cases
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test2\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test2\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_NO_THROW(cme_global_obj.cme_command_handler(command));
        unordered_map<string, string> tokens_map;
        tokens_map.try_emplace("app", "test2");
        tokens_map.try_emplace("app_pid", to_string(pid));
        cme_context* ctx = cme_global_obj.cg_find_context(tokens_map, true);
        EXPECT_TRUE(ctx != nullptr);
        
        ctx->get_stats_state = STATS_INPROGRESS;
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test2\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EBUSY));

        // Check no mover case
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"test3\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test3\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_NO_THROW(cme_global_obj.cme_command_handler(command));
        cme_global_obj.movers_list.clear();
        command = " {\"command_name\": \"get_stats\", \"command_params\": {\"app\": \"test3\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));

        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckMoverDamoTwoContexts) {
        cme_global cme_global_obj;
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();

        // Check valid command , contex1
        string command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"contex1\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check valid command , contex2
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"contex2\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
       
        // Check stop contex2
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"contex2\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check stop contex1
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"contex1\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}

TEST_F(cmeTest, CheckMoverDamoInvalidDamoConfigGen) {
        cme_global cme_global_obj;
        EXPECT_EQ(cme_global_obj.read_cme_config_json("no_exist_cme_config.json"), -EINVAL);
        ASSERT_EQ(cme_global_obj.read_cme_config_json("cme_config.json"), 0);
        ASSERT_EQ(cme_global_obj.cme_discovery(), 0);
        ASSERT_EQ(cme_global_obj.initialize(), 0);
        int pid = getpid();
        unsigned int numa_count_conf = numa_num_configured_nodes();

        // Check valid command , contex2
        string command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"contex2\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \"0\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));

        // Check invalid numa node for damo config gen
        command = " {\"command_name\": \"move\", \"command_params\": {\"app\": \"contex1\", \"app_pid\":\"" + to_string(pid) + "\", \"tm_attr\": \"MOVER_AGGRESSIVENESS_LOW\",\"slow_tier\": \"1\",\"fast_tier\": \""  + to_string(numa_count_conf) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(-EINVAL));
  
        // Check stop 
        command = " {\"command_name\": \"stop\", \"command_params\": {\"app\": \"contex2\", \"app_pid\":\"" +  to_string(pid) + "\"}} ";
        EXPECT_EQ(cme_global_obj.cme_command_handler(command), to_string(0));
        EXPECT_EQ(cme_global_obj.clean_up(), 0);
}
