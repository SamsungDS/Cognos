#ifndef __GRPC_CONTROLLER_HLPR_H__
#define __GRPC_CONTROLLER_HLPR_H__

#include "grpc_controller.h"

std::shared_ptr<Server> InitializeServicer(ControllerServicer *svcr);
int StartServer(std::string svk_conf_file, bool blocking);
void signal_handler(int signal);
int StartSLAThreadForTiering(ControllerServicer *svcr);
int StopSLAThreadForTiering(ControllerServicer *svcr);

#endif /*__GRPC_CONTROLLER_HLPR_H__*/