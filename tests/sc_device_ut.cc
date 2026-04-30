#include <gtest/gtest.h>

#include "sc_device.h"
#include "sc_device_info.h"

using namespace std;

class ScDeviceTest : public ::testing::Test {
 protected:
  sc_device defaultDevice;
  sc_device paramDevice;

  void SetUp() override {
    paramDevice = sc_device(123, "TestDevice", 1024, 8080);
  }
};

TEST_F(ScDeviceTest, ToDeviceInfo) {
  DevStaticInfo sinfo;
  sinfo.location = "0000:5e:00.0";
  paramDevice.d_set_static_info(sinfo);

  DevInfo dinfo;
  dinfo.numa_node = -1;
  dinfo.available_capacity_MB = 0;
  paramDevice.d_set_dynamic_info(dinfo);
  DevInfo result = paramDevice.to_device_info();
  EXPECT_EQ(result.static_info.location, "0000:5e:00.0");
}

TEST_F(ScDeviceTest, DefaultConstructor) {
  // Test default constructor
  EXPECT_EQ(defaultDevice.d_get_dev_name(), "");
  EXPECT_EQ(defaultDevice.d_get_capacity(), 0);
  EXPECT_EQ(defaultDevice.d_get_port(), 0);
}

TEST_F(ScDeviceTest, ParameterizedConstructor) {
  // Test parameterized constructor
  EXPECT_EQ(paramDevice.d_get_dev_name(), "TestDevice");
  EXPECT_EQ(paramDevice.d_get_capacity(), 1024);
  EXPECT_EQ(paramDevice.d_get_port(), 8080);
}

TEST_F(ScDeviceTest, SettersAndGetters) {
  // Test setters and getters
  defaultDevice.d_set_dev_name("NewDevice");
  defaultDevice.d_set_capacity(2048);
  defaultDevice.d_set_port(9090);

  EXPECT_EQ(defaultDevice.d_get_dev_name(), "NewDevice");
  EXPECT_EQ(defaultDevice.d_get_capacity(), 2048);
  EXPECT_EQ(defaultDevice.d_get_port(), 9090);
}

TEST_F(ScDeviceTest, OverCapacity) {
  // Test over capacity
  EXPECT_THROW(
      paramDevice.d_set_capacity(6000ull * 1024ull * 1024ull * 1024ull + 1),
      std::invalid_argument);
}

TEST_F(ScDeviceTest, InvalidDeviceName) {
  // Test invalid device name
  EXPECT_THROW(paramDevice.d_set_dev_name("Invalid$Name"),
               std::invalid_argument);
}

TEST_F(ScDeviceTest, InvalidPortRange) {
  // Test invalid port range
  EXPECT_THROW(paramDevice.d_set_port(70000), std::invalid_argument);
}

TEST_F(ScDeviceTest, UnderCapacity) {
  // Test under capacity
  EXPECT_THROW(paramDevice.d_set_capacity(-1), std::invalid_argument);
}

TEST_F(ScDeviceTest, EmptyDeviceName) {
  // Test empty device name
  EXPECT_THROW(paramDevice.d_set_dev_name(""), std::invalid_argument);
}

TEST_F(ScDeviceTest, GetCompositeObj) {
  // Test d_get_id method
  sc_id compositeId = paramDevice.d_get_id();
  EXPECT_EQ(compositeId.get_sc_id(), 123);
}

TEST_F(ScDeviceTest, SetDevName_ValidName) {
  string validName = "ValidName";
  ASSERT_NO_THROW(paramDevice.d_set_dev_name(validName));
  EXPECT_EQ(validName, paramDevice.d_get_dev_name());
}

TEST_F(ScDeviceTest, SetDevName_InvalidName) {
  string invalidName = "Invalid Name!";
  EXPECT_THROW(paramDevice.d_set_dev_name(invalidName), std::invalid_argument);
}

TEST_F(ScDeviceTest, InvalidDeviceNameException) {
  // Contains spaces and special characters
  string invalidName = "Invalid Name!";
  try {
    paramDevice.d_set_dev_name(invalidName);
    FAIL() << "Expected std::invalid_argument exception, but no exception was "
              "thrown.";
  } catch (const std::invalid_argument& e) {
    EXPECT_TRUE(std::string(e.what()).find("Invalid device name: ") !=
                std::string::npos);
  }
}

TEST_F(ScDeviceTest, SetPortValidValue) {
  uint32_t validPort = 8080;
  ASSERT_NO_THROW(paramDevice.d_set_port(validPort));
  EXPECT_EQ(paramDevice.d_get_port(), validPort);
}

TEST_F(ScDeviceTest, SetPortInvalidValue) {
  uint32_t invalidPort = 70000;
  EXPECT_THROW(paramDevice.d_set_port(invalidPort), std::invalid_argument);
}

TEST_F(ScDeviceTest, SetCapacityValidValue) {
  // valid capacity (1 GB)
  uint64_t validCapacity = 1024ull * 1024ull * 1024ull;
  ASSERT_NO_THROW(paramDevice.d_set_capacity(validCapacity));
  EXPECT_EQ(paramDevice.d_get_capacity(), validCapacity);
}

TEST_F(ScDeviceTest, SetCapacityInvalidValue) {
  // invalid capacity (70 GB)
  uint64_t invalidCapacity = 70000ull * 1024ull * 1024ull;

  try {
    paramDevice.d_set_capacity(invalidCapacity);
  } catch (const std::invalid_argument& e) {
    EXPECT_TRUE(std::string(e.what()).find("Invalid capacity value: ") !=
                std::string::npos);
  } catch (...) {
    FAIL() << "Unexpected exception type.";
  }
}

TEST_F(ScDeviceTest, get_info_valid) {
  sc_device dev(1001, "sample_dev", 2048, 2);

  DevStaticInfo static_info;
  static_info.device_id = 1001;
  static_info.location = "slot-B";
  static_info.manufacturer = "AcmeCorp";
  static_info.cxl_device_type = "CMMH";
  dev.d_set_static_info(static_info);

  DevInfo dynamic_info;
  dynamic_info.aspm_active = true;
  dynamic_info.status = "active";
  dynamic_info.available_capacity_MB = 1024;
  dev.d_set_dynamic_info(dynamic_info);

  const DevInfo& info = dev.d_get_info();

  EXPECT_EQ(info.static_info.device_id, 1001);
  EXPECT_EQ(info.static_info.location, "slot-B");
  EXPECT_EQ(info.static_info.manufacturer, "AcmeCorp");
  EXPECT_EQ(info.static_info.cxl_device_type, "CMMH");

  EXPECT_EQ(info.status, "active");
  EXPECT_TRUE(info.aspm_active);
  EXPECT_EQ(info.available_capacity_MB, 1024);
}

/*
 * We are using mock data from 3 different setups to simulate all possible data
 * inputs based on OS, number and types of devices, etc. Hence we chose the
 * following 3 setups: Setup1 - SRF11 - this machine has 1 CMM-H devices and OS
 * as Oracle linux 10 Setup2 - SRF14 - this machine has 4 CMM-H devices and OS
 * as Oracle Linux 9 Setup3 - CX03 - 4 CMM-D shown as single NUMA node. OS is
 * Ubuntu24
 */

TEST_F(ScDeviceTest, validate_setup1) {
  // Start the Python interpreter
  pybind11::scoped_interpreter guard{};

  // Add TEST_PYTHON_DIR directory defined in CMakeLists.txt to sys.path so
  // Python can find cxl_device_info.py
  py::module_ sys = py::module_::import("sys");
  sys.attr("path").attr("insert")(0, TEST_PYTHON_DIR);
  try {
    // Import python code file ('cxl_device_info.py' in build/tests directory)
    auto my_module = py::module_::import("cxl_device_info");

    // Import the inspect module to read source code
    auto inspect = py::module_::import("inspect");

    // Get the specific function object for get_numa_map_from_lsmem
    auto func_lsmem = my_module.attr("get_numa_map_from_lsmem");

    // Get source as string and cast to std::string
    string source_code_lsmem =
        inspect.attr("getsource")(func_lsmem).cast<std::string>();
    string tstr = R"(    output = """)";
    tstr += lsmem_output_all_setup1;
    tstr += R"(    """)";
    string srch = "output = run_command(\"lsmem --output-all\")";
    string replaced_str_lsmem =
        replaceLine(source_code_lsmem, R"("lsmem --output-all")", tstr);

    // Prepare Python code for exec using info from above
    istringstream stream(replaced_str_lsmem);
    string line, eline = "";

    // Creating code line by line
    while (std::getline(stream, line)) {
      eline += line;
      eline += "\n";
    }
    py::dict scope = py::globals();
    py::exec(eline, scope, scope);

    py::object numa_map_func = scope["get_numa_map_from_lsmem"];

    // Get result dict of function call get_numa_map_from_lsmem
    // This dict is used later for getting the numa node for each range
    py::dict pd = numa_map_func();

    // Cast python dict to C++ map
    auto m_cpp = pd.cast<map<string, int> >();

    // Test for equality of dict obtained with manually obtained values
    EXPECT_EQ(m_cpp, m_range_node_setup1);

    for (auto& x : pd) {
      string t = x.first.cast<string>();
      EXPECT_TRUE(m_range_node_setup1.count(t) > 0);
    }

    // Get the specific function object for get_numa_node_for_device,
    // hex_string_to_range and range_subset
    auto func_lspci = my_module.attr("get_numa_node_for_device");
    auto func_hex_string_to_range = my_module.attr("hex_string_to_range");
    auto func_range_subset = my_module.attr("range_subset");

    // Get source as string and replace run_command of lspci command
    // with appropriate info
    string source_code_lspci, source_code_hex_string_to_range,
        source_code_range_subset;
    string actual_source_code_lspci, replaced_str_lspci, replaced_str_lspci2;
    string empty_str =
        ""
        ""
        "";
    istringstream stream_lspci;

    // Iterating over each Range value for each BDF to get NUMA node
    for (const auto& z : v_lspci_vvv_s_bdf_grep_Range1_setup1) {
      source_code_lspci =
          inspect.attr("getsource")(func_lspci).cast<std::string>();
      source_code_hex_string_to_range =
          inspect.attr("getsource")(func_hex_string_to_range)
              .cast<std::string>();
      source_code_range_subset =
          inspect.attr("getsource")(func_range_subset).cast<std::string>();
      tstr = R"(    output = """)";
      tstr += z;
      tstr += R"(    """)";

      // Insert the code to be executed
      actual_source_code_lspci = "import re\n\n";
      actual_source_code_lspci += source_code_range_subset;
      actual_source_code_lspci += source_code_hex_string_to_range;
      actual_source_code_lspci += source_code_lspci;

      // Replace line with lspci command string with empty string
      replaced_str_lspci =
          replaceLine(actual_source_code_lspci, R"(lspci -vvv)", empty_str);
      replaced_str_lspci2 =
          replaceLine(replaced_str_lspci, R"(run_command)", tstr);

      // Prepare Python code for exec using info from above
      stream_lspci.clear();
      stream_lspci.str(replaced_str_lspci2);
      string line2, eline2 = "";

      // Creating code line by line
      while (std::getline(stream_lspci, line2)) {
        eline2 += line2;
        eline2 += "\n";
      }
      py::dict scope2 = py::globals();
      py::exec(eline2, scope2, scope2);

      // Get result of function call get_numa_node_for_device
      py::object numa_node_for_device = scope2["get_numa_node_for_device"];

      // Tests to ensure that for each BDF we get the expected NUMA node
      for (const auto& y : v_bdf_setup1) {
        auto numa_node = numa_node_for_device(y, pd);
        // Success condition will return a  positive value
        EXPECT_TRUE(numa_node.cast<int>() >= 0);

        // The NUMA node value should be a value in key-value pair of the
        // map populated using lsmem output
        int targetValue = numa_node.cast<int>();
        auto it =
            std::find_if(m_range_node_setup1.begin(), m_range_node_setup1.end(),
                         [&targetValue](const auto& pair) {
                           return pair.second == targetValue;
                         });
        EXPECT_TRUE(it != m_range_node_setup1.end());

        // The device address range should be subset/superset of the address
        // range NUMA node value in map obtained from lsmem output
        regex hex_range_regex(R"([0-9a-fA-F]+-[0-9a-fA-F]+)");
        smatch match;
        EXPECT_TRUE(regex_search(z, match, hex_range_regex));
        string s = match.str();
        string t = it->first;
        if (isSubrange(s, t) || isSubrange(t, s)) {
          EXPECT_EQ(it->second, targetValue);
        }
      }
    }
  } catch (pybind11::error_already_set& e) {
    FAIL() << "Error: " << e.what();
  }
}

TEST_F(ScDeviceTest, validate_setup2) {
  // Start the Python interpreter
  pybind11::scoped_interpreter guard{};

  // Add TEST_PYTHON_DIR directory defined in CMakeLists.txt to sys.path so
  // Python can find cxl_device_info.py
  py::module_ sys = py::module_::import("sys");
  sys.attr("path").attr("insert")(0, TEST_PYTHON_DIR);
  try {
    // Import python code file ('cxl_device_info.py' in build/tests directory)
    auto my_module = py::module_::import("cxl_device_info");

    // Import the inspect module to read source code
    auto inspect = py::module_::import("inspect");

    // Get the specific function object for get_numa_map_from_lsmem
    auto func_lsmem = my_module.attr("get_numa_map_from_lsmem");

    // Get source as string and cast to std::string
    string source_code_lsmem =
        inspect.attr("getsource")(func_lsmem).cast<std::string>();
    string tstr = R"(    output = """)";
    tstr += lsmem_output_all_setup2;
    tstr += R"(    """)";
    string srch = "output = run_command(\"lsmem --output-all\")";
    string replaced_str_lsmem =
        replaceLine(source_code_lsmem, R"("lsmem --output-all")", tstr);

    // Prepare Python code for exec using info from above
    istringstream stream(replaced_str_lsmem);
    string line, eline = "";

    // Creating code line by line
    while (std::getline(stream, line)) {
      eline += line;
      eline += "\n";
    }
    py::dict scope = py::globals();
    py::exec(eline, scope, scope);

    py::object numa_map_func = scope["get_numa_map_from_lsmem"];

    // Get result dict of function call get_numa_map_from_lsmem
    // This dict is used later for getting the numa node for each range
    py::dict pd = numa_map_func();

    // Cast python dict to C++ map
    auto m_cpp = pd.cast<map<string, int> >();

    // Test for equality of dict obtained with manually obtained values
    EXPECT_EQ(m_cpp, m_range_node_setup2);

    for (auto& x : pd) {
      string t = x.first.cast<string>();
      EXPECT_TRUE(m_range_node_setup2.count(t) > 0);
    }

    // Get the specific function object for get_numa_node_for_device,
    // hex_string_to_range and range_subset
    auto func_lspci = my_module.attr("get_numa_node_for_device");
    auto func_hex_string_to_range = my_module.attr("hex_string_to_range");
    auto func_range_subset = my_module.attr("range_subset");

    // Get source as string and replace run_command of lspci command
    // with appropriate info
    string source_code_lspci, source_code_hex_string_to_range,
        source_code_range_subset;
    string actual_source_code_lspci, replaced_str_lspci, replaced_str_lspci2;
    string empty_str =
        ""
        ""
        "";
    istringstream stream_lspci;

    // Iterating over each Range value for each BDF to get NUMA node
    for (const auto& z : v_lspci_vvv_s_bdf_grep_Range1_setup2) {
      source_code_lspci =
          inspect.attr("getsource")(func_lspci).cast<std::string>();
      source_code_hex_string_to_range =
          inspect.attr("getsource")(func_hex_string_to_range)
              .cast<std::string>();
      source_code_range_subset =
          inspect.attr("getsource")(func_range_subset).cast<std::string>();
      tstr = R"(    output = """)";
      tstr += z;
      tstr += R"(    """)";

      // Insert the code to be executed
      actual_source_code_lspci = "import re\n\n";
      actual_source_code_lspci += source_code_range_subset;
      actual_source_code_lspci += source_code_hex_string_to_range;
      actual_source_code_lspci += source_code_lspci;

      // Replace line with lspci command string with empty string
      replaced_str_lspci =
          replaceLine(actual_source_code_lspci, R"(lspci -vvv)", empty_str);
      replaced_str_lspci2 =
          replaceLine(replaced_str_lspci, R"(run_command)", tstr);

      // Prepare Python code for exec using info from above
      stream_lspci.clear();
      stream_lspci.str(replaced_str_lspci2);
      string line2, eline2 = "";

      // Creating code line by line
      while (std::getline(stream_lspci, line2)) {
        eline2 += line2;
        eline2 += "\n";
      }
      py::dict scope2 = py::globals();
      py::exec(eline2, scope2, scope2);

      // Get result of function call get_numa_node_for_device
      py::object numa_node_for_device = scope2["get_numa_node_for_device"];

      // Tests to ensure that for each BDF we get the expected NUMA node
      for (const auto& y : v_bdf_setup2) {
        auto numa_node = numa_node_for_device(y, pd);
        // Success condition will return a  positive value
        EXPECT_TRUE(numa_node.cast<int>() >= 0);

        // The NUMA node value should be a value in key-value pair of the
        // map populated using lsmem output
        int targetValue = numa_node.cast<int>();
        auto it =
            std::find_if(m_range_node_setup2.begin(), m_range_node_setup2.end(),
                         [&targetValue](const auto& pair) {
                           return pair.second == targetValue;
                         });
        EXPECT_TRUE(it != m_range_node_setup2.end());

        // The device address range should be subset/superset of the address
        // range NUMA node value in map obtained from lsmem output
        regex hex_range_regex(R"([0-9a-fA-F]+-[0-9a-fA-F]+)");
        smatch match;
        EXPECT_TRUE(regex_search(z, match, hex_range_regex));
        string s = match.str();
        string t = it->first;
        if (isSubrange(s, t) || isSubrange(t, s)) {
          EXPECT_EQ(it->second, targetValue);
        }
      }
    }
  } catch (pybind11::error_already_set& e) {
    FAIL() << "Error: " << e.what();
  }
}

TEST_F(ScDeviceTest, validate_setup3) {
  // Start the Python interpreter
  pybind11::scoped_interpreter guard{};

  // Add TEST_PYTHON_DIR directory defined in CMakeLists.txt to sys.path so
  // Python can find cxl_device_info.py
  py::module_ sys = py::module_::import("sys");
  sys.attr("path").attr("insert")(0, TEST_PYTHON_DIR);
  try {
    // Import python code file ('cxl_device_info.py' in build/tests directory)
    auto my_module = py::module_::import("cxl_device_info");

    // Import the inspect module to read source code
    auto inspect = py::module_::import("inspect");

    // Get the specific function object for get_numa_map_from_lsmem
    auto func_lsmem = my_module.attr("get_numa_map_from_lsmem");

    // Get source as string and cast to std::string
    string source_code_lsmem =
        inspect.attr("getsource")(func_lsmem).cast<std::string>();
    string tstr = R"(    output = """)";
    tstr += lsmem_output_all_setup3;
    tstr += R"(    """)";
    string srch = "output = run_command(\"lsmem --output-all\")";
    string replaced_str_lsmem =
        replaceLine(source_code_lsmem, R"("lsmem --output-all")", tstr);

    // Prepare Python code for exec using info from above
    istringstream stream(replaced_str_lsmem);
    string line, eline = "";

    // Creating code line by line
    while (std::getline(stream, line)) {
      eline += line;
      eline += "\n";
    }
    py::dict scope = py::globals();
    py::exec(eline, scope, scope);

    py::object numa_map_func = scope["get_numa_map_from_lsmem"];

    // Get result dict of function call get_numa_map_from_lsmem
    // This dict is used later for getting the numa node for each range
    py::dict pd = numa_map_func();

    // Cast python dict to C++ map
    auto m_cpp = pd.cast<map<string, int> >();

    // Test for equality of dict obtained with manually obtained values
    EXPECT_EQ(m_cpp, m_range_node_setup3);

    for (auto& x : pd) {
      string t = x.first.cast<string>();
      EXPECT_TRUE(m_range_node_setup3.count(t) > 0);
    }

    // Get the specific function object for get_numa_node_for_device,
    // hex_string_to_range and range_subset
    auto func_lspci = my_module.attr("get_numa_node_for_device");
    auto func_hex_string_to_range = my_module.attr("hex_string_to_range");
    auto func_range_subset = my_module.attr("range_subset");

    // Get source as string and replace run_command of lspci command
    // with appropriate info
    string source_code_lspci, source_code_hex_string_to_range,
        source_code_range_subset;
    string actual_source_code_lspci, replaced_str_lspci, replaced_str_lspci2;
    string empty_str =
        ""
        ""
        "";
    istringstream stream_lspci;

    // Iterating over each Range value for each BDF to get NUMA node
    for (const auto& z : v_lspci_vvv_s_bdf_grep_Range1_setup3) {
      source_code_lspci =
          inspect.attr("getsource")(func_lspci).cast<std::string>();
      source_code_hex_string_to_range =
          inspect.attr("getsource")(func_hex_string_to_range)
              .cast<std::string>();
      source_code_range_subset =
          inspect.attr("getsource")(func_range_subset).cast<std::string>();
      tstr = R"(    output = """)";
      tstr += z;
      tstr += R"(    """)";

      // Insert the code to be executed
      actual_source_code_lspci = "import re\n\n";
      actual_source_code_lspci += source_code_range_subset;
      actual_source_code_lspci += source_code_hex_string_to_range;
      actual_source_code_lspci += source_code_lspci;

      // Replace line with lspci command string with empty string
      replaced_str_lspci =
          replaceLine(actual_source_code_lspci, R"(lspci -vvv)", empty_str);
      replaced_str_lspci2 =
          replaceLine(replaced_str_lspci, R"(run_command)", tstr);

      // Prepare Python code for exec using info from above
      stream_lspci.clear();
      stream_lspci.str(replaced_str_lspci2);
      string line2, eline2 = "";

      // Creating code line by line
      while (std::getline(stream_lspci, line2)) {
        eline2 += line2;
        eline2 += "\n";
      }
      py::dict scope2 = py::globals();
      py::exec(eline2, scope2, scope2);

      // Get result of function call get_numa_node_for_device
      py::object numa_node_for_device = scope2["get_numa_node_for_device"];

      // Tests to ensure that for each BDF we get the expected NUMA node
      for (const auto& y : v_bdf_setup3) {
        auto numa_node = numa_node_for_device(y, pd);
        // Success condition will return a  positive value
        EXPECT_TRUE(numa_node.cast<int>() >= 0);

        // The NUMA node value should be a value in key-value pair of the
        // map populated using lsmem output
        int targetValue = numa_node.cast<int>();
        auto it =
            std::find_if(m_range_node_setup3.begin(), m_range_node_setup3.end(),
                         [&targetValue](const auto& pair) {
                           return pair.second == targetValue;
                         });
        EXPECT_TRUE(it != m_range_node_setup3.end());

        // The device address range should be subset/superset of the address
        // range NUMA node value in map obtained from lsmem output
        regex hex_range_regex(R"([0-9a-fA-F]+-[0-9a-fA-F]+)");
        smatch match;
        EXPECT_TRUE(regex_search(z, match, hex_range_regex));
        string s = match.str();
        string t = it->first;
        if (isSubrange(s, t) || isSubrange(t, s)) {
          EXPECT_EQ(it->second, targetValue);
        }
      }
    }
  } catch (pybind11::error_already_set& e) {
    FAIL() << "Error: " << e.what();
  }
}
