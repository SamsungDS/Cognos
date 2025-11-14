
#include <array>
#include <functional>
#include <csignal>
#include <unistd.h>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>
#include "cme_utils.h"
#include "cme_logger.h"

using namespace std;

constexpr size_t POPEN_BUFFER_SIZE = 1024;

bool isDirectory(std::string path)
{
        struct stat entrystat;
      
        if (stat(path.c_str(), &entrystat)) return false;
        return S_ISDIR(entrystat.st_mode);
}

unordered_map<string, string> tokenize (string input)
{
  	char *s = (char *)input.c_str ();
  	char *tok = strtok (s, ";");
  	char key[256], val[256];
  	unordered_map<string, string> tokens;
  	while (tok != NULL)
    	{
      		sscanf (tok, "%[a-zA-Z0-9_]=%[/a-zA-Z0-9_-]", key, val);
      		tokens[key] = val;
      		tok = strtok (NULL, ";");
    	}
  	return tokens;
}

unordered_map<string, string> token_helper (string input)
{
  	unordered_map<string, string> tokens_map = tokenize (input);
  	return tokens_map;
}

bool command_parser_json(const std::string& input_cme_command, unordered_map<std::string, std::string> &command_params_map)
{
        try
        {
                namespace pt = boost::property_tree;
                pt::ptree root;
                std::istringstream json_stream(input_cme_command);                
		pt::read_json(json_stream, root);
                std::string command_name = root.get<std::string> ("command_name");
                command_params_map.try_emplace("command", command_name);
                auto command_params = root.get_child("command_params");
                for (const auto& item : command_params)
                {
			command_params_map.try_emplace(item.first, item.second.data());
                }
        }
        catch (const std::exception &e)
        {
                CME_ERR("command_parser_json. Error -> ", e.what ());
                return false;
        }
        return true;
}

int execute_command(const std::string& cmd, std::vector<std::string>& output, bool test_flag)
{
        if (test_flag)
        {
                return 0;
        }
        output.clear();
        string command = cmd;
        CME_LOG("INFO", "Executing ", command);
        std::unique_ptr<FILE, std::function<void(FILE*)>> pipe(
                popen(command.c_str(), "r"),
                [](FILE* f) { pclose(f); }
        );

        if (!pipe) {
                throw std::runtime_error("popen() failed!");
        }

        std::array<char, POPEN_BUFFER_SIZE> buffer;
        while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
                output.emplace_back(buffer.data());
        }

        // Get the exit status of the command
        int status = pclose(pipe.release());
        if (status == -1) {
                throw std::runtime_error("pclose() failed!");
        }

        // Extract the exit status
        int exit_status = WEXITSTATUS(status);
        return exit_status;
}

long get_invalid_pid( void)
{
        const char* max_pid_str = std::getenv("MAX_PID");
        if (max_pid_str == nullptr) {
                // Fallback to a default value if MAX_PID is not set
                max_pid_str = std::to_string(32768).c_str();
        }
        int max_pid = std::atoi(max_pid_str);
        return((long)(max_pid + 1));
}

bool pid_exists(long pid)
{
    // Use kill with signal 0 to check if the process exists
    // This does not send a real signal, just checks for permission
    return kill((pid_t)pid, 0) == 0;
}

std::string getCurrentTimestamp()
{
        // Get the current time as a time_point
        auto now = std::chrono::system_clock::now();
        // Get epoch
        auto epoch_nano_seconds_direct = std::chrono::duration_cast<std::chrono::nanoseconds>(now.time_since_epoch()).count();
        std::string epoch_nano_seconds_str = std::to_string(epoch_nano_seconds_direct);
        return epoch_nano_seconds_str;
}
