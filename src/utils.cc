
#include "utils.h"
#include <unistd.h>

using namespace std;

int
execute_command (string cmd, vector<string> output, bool test_flag)
{
  cout << "Executing Command: " << cmd << endl;
  if (test_flag)
    {
      return 0;
    }
  try
    {
      char buffer[256];
      FILE *pipe = popen (cmd.c_str (), "r");
      if (!pipe)
        {
          throw runtime_error ("Error in " + string (__FUNCTION__)
                               + " : error in popen for command: " + cmd);
        }
      while (fgets (buffer, sizeof (buffer), pipe) != nullptr)
        {
          output.push_back (buffer);
        }
      int status = pclose (pipe);
      if (status != 0)
        {
          throw runtime_error ("Error in " + string (__FUNCTION__)
                               + " : error in execution for command: " + cmd
                               + " exit status: "
                               + to_string (WEXITSTATUS (status)));
        }
    }
  catch (const exception &e)
    {
      throw runtime_error ("Error in " + string (__FUNCTION__) + " : "
                           + string (e.what ()));
    }
  return 0;
}
