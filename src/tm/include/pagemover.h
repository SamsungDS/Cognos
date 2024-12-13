#ifndef __PAGEMOVER_H__
#define __PAGEMOVER_H__

#include <iostream>
#include <iostream>
#include <sstream>
#include <fstream>
#include <vector>
#include <string>
#include <map>
#include <unordered_map>
#include <tuple>
#include "jansson.h"
#include "yaml-cpp/yaml.h"
#include "tuner_element.h"

using namespace std;

/**
 * @brief pagemover class 
 * @details Abstract out which page mover and it's functionality
 * Has reference to tuner_element object as its members are needed
 * for page mover functionality
 */
class pagemover {
public:
	pagemover() = default;
	virtual ~pagemover(){};
	tuner_element* mte;
	virtual int start();
	virtual	int stop();
};
#endif


