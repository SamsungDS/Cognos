#ifndef __GRPC_SERVER_HLPR_H__
#define __GRPC_SERVER_HLPR_H__

#include "grpc_server.h"

std::shared_ptr<Server> InitializeNodeServicer(Servicer *svcr);
int StartNodeServer(std::string svk_conf_file, bool blocking);
void signal_node_handler(int signal);

#endif /*__GRPC_SERVER_HLPR_H__*/