#ifndef CONFIG_READER_H
#define CONFIG_READER_H

#include "structures.h"
#include <string>

std::string trim(const std::string& str);
std::string grabRunHandle(const std::string& str);
bool stringToBool(const std::string& str);
template<typename T> T stringToNumber(const std::string& str);
bool readConfigFile(const std::string &filename, configParameters &params);
void printParameters(const configParameters &params) ;

#endif // CONFIG_READER_H
