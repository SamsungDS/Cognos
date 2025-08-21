
#include "include/cme_utils.h"
#include <unistd.h>
#include <cstring>
#include <boost/property_tree/json_parser.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/xml_parser.hpp>

using namespace std;

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

bool command_parser_json(std::string input_cme_command, unordered_map<std::string, std::string> &command_params_map)
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
                std::cerr << "command_parser_json. Error -> " << e.what () << endl;
                return false;
        }

        return true;
}

