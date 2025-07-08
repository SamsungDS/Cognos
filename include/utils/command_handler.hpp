#ifndef _COMMAND_HANDLER__HPP_
#define _COMMAND_HANDLER__HPP_

#include <string>
#include <unordered_map>

#include "ras_device.h"
#include "ras_request.h"

/**
 * @brief Abstract base class for command handlers.
 *
 * This class provides a pure virtual interface for handling commands.
 *
 * @tparam Request The type of the request being handled.
 */
template <typename Request>
class CommandHandlerImpl {
 public:
  /**
   * @brief Validates the given request.
   *
   * @param r The request to be validated.
   * @return true if the request is valid, false otherwise.
   */
  virtual bool validate(Request& r) = 0;

  /**
   * @brief Executes the given request.
   *
   * @param r The request to be executed.
   */
  virtual void execute(Request& r) = 0;

  /**
   * @brief Gets the command associated with this handler.
   *
   * @return The command as a string.
   */
  virtual std::string get_command(void) = 0;
};

/**
 * @brief Command handler class.
 *
 * This class manages a collection of command handlers and provides a way to
 * execute commands.
 *
 * @tparam Request The type of the request being handled.
 */
template <typename Request>
class CommandHandler {
 public:
  /**
   * @brief Enumerates the possible statuses of a command execution.
   */
  enum class command_status {
    COMMAND_EXECUTED,    ///< The command was executed successfully.
    COMMAND_INVALID,     ///< The command is invalid.
    COMMAND_UNSUPPORTED  ///< The command is not supported.
  };

  /**
   * @brief Registers a new command handler.
   *
   * @param handler The handler for the command.
   */
  void register_command(std::unique_ptr<CommandHandlerImpl<Request>> handler) {
    // Insert the command handler into the map.
    // Note: If the command already exists, it will be overwritten.
    std::string command = handler->get_command();
    this->command_handlers_.insert(std::make_pair(command, std::move(handler)));
  }

  /**
   * @brief Executes a command.
   *
   * @param command The command to be executed.
   * @param cmd The request associated with the command.
   * @return The status of the command execution.
   */
  command_status execute_command(const std::string& command, Request& cmd) {
    // Find the command handler in the map.
    if (auto it = this->command_handlers_.find(command);
        it != this->command_handlers_.end()) {
      // Validate the request.
      if (it->second->validate(cmd) == true) {
        // Execute the request.
        it->second->execute(cmd);
        return command_status::COMMAND_EXECUTED;
      }
      return command_status::COMMAND_INVALID;
    }
    return command_status::COMMAND_UNSUPPORTED;
  }

 private:
  /**
   * @brief Map of command handlers.
   */
  std::unordered_map<std::string, std::unique_ptr<CommandHandlerImpl<Request>>>
      command_handlers_;
};

#endif  // _COMMAND_HANDLER__HPP_
