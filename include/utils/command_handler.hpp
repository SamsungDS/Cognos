#ifndef _COMMAND_HANDLER__HPP_
#define _COMMAND_HANDLER__HPP_

#include <unordered_map>

template <typename Request>
class CommandHandlerImpl {
 public:
  virtual bool validate(Request& r) = 0;
  virtual void execute(Request& r) = 0;
  virtual std::string get_command(void) = 0;
};

template <typename Request>
class CommandHandler {
 public:
  enum class command_status {
    COMMAND_EXECUTED,
    COMMAND_INVALID,
    COMMAND_UNSUPPORTED
  };

  void register_command(const std::string command,
                        std::unique_ptr<CommandHandlerImpl<Request>> handler) {
    // TODO Check error
    this->command_handlers_.insert(
        std::make_pair(std::string(command), std::move(handler)));
  }

  command_status execute_command(const std::string& command, Request& cmd) {
    if (auto it = this->command_handlers_.find(command);
        it != this->command_handlers_.end()) {
      if (it->second->validate(cmd) == true) {
        it->second->execute(cmd);
        return command_status::COMMAND_EXECUTED;
      }
      return command_status::COMMAND_INVALID;
    }
    return command_status::COMMAND_UNSUPPORTED;
  }

 private:
  std::unordered_map<std::string, std::unique_ptr<CommandHandlerImpl<Request>>>
      command_handlers_;
};

#endif  // _COMMAND_HANDLER__HPP_