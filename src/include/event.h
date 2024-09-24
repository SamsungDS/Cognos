#ifndef __EVENT_H__
#define __EVENT_H__

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <thread>
#include <iostream>
#include <sstream>
#include <fstream>
#include <vector>
#include <string>
#include <ctime>
#include <tuple>
const uint8_t HOSTNAME_MAXLEN = 128;

/**
 * @brief Event class
 * @details Event class.
 *          It holds the event fields.
 * 			Presently supports metric event, Event type = metric
 * 			Future supports Event type = alert/heartbeat.
 */
class Event 
{
	public:
        	//default constructor
		Event() = default;

		std::string type;
		std::string source;
		std::string source_type;
		std::string timestamp;
		std::string description;
		std::string category;
		std::string application;
		std::vector <std::tuple<std::string, std::string>> observations;
};
#endif
