#ifndef _RAS_COMMAND_HANDLERS__HPP_
#define _RAS_COMMAND_HANDLERS__HPP_

#pragma once

#include <vector>

#include "command_handlers/ras_add_device_handler.hpp"
#include "command_handlers/ras_monitor_check_device_status.hpp"
#include "command_handlers/ras_remove_device_handler.hpp"

std::unique_ptr<cognos::utils::CommandHandler<ras_request>>
get_ras_command_handler(void);

#endif  // _RAS_COMMAND_HANDLERS__HPP_
