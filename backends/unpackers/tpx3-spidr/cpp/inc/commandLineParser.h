/**
 * @file commandLineParser.h
 * @brief Header file for command-line parsing utilities
 */

#ifndef COMMANDLINEPARSER_H
#define COMMANDLINEPARSER_H

#include <string>
#include "structures.h"

/**
 * @brief Creates default configuration parameters
 * @return configParameters struct with default values
 */
configParameters createDefaultConfig();

/**
 * @brief Check if a file exists
 * @param filepath Path to the file
 * @return true if file exists
 */
bool fileExists(const std::string& filepath);

/**
 * @brief Check if a file has a specific extension
 * @param filepath Path to the file
 * @param extension Expected extension (e.g., ".tpx3", ".config")
 * @return true if file has the expected extension
 */
bool hasExtension(const std::string& filepath, const std::string& extension);

/**
 * @brief Check if a file exists and has a specific extension
 * @param filepath Path to the file
 * @param extension Expected extension (e.g., ".tpx3", ".config")
 * @return true if file exists and has the expected extension
 */
bool isFileWithExtension(const std::string& filepath, const std::string& extension);

/**
 * @brief Extract directory path from file path
 * @param filepath Full path to file
 * @return Directory path (empty string if no directory)
 */
std::string getDirectoryPath(const std::string& filepath);

/**
 * @brief Extract filename from file path
 * @param filepath Full path to file
 * @return Filename only
 */
std::string getFilename(const std::string& filepath);

/**
 * @brief Safely parse integer from string
 * @param str String to parse
 * @param defaultValue Default value if parsing fails
 * @return Parsed integer or default value
 */
int parseIntOrDefault(const std::string& str, int defaultValue);

/**
 * @brief Parse command-line flags and populate configuration
 * @param argc Number of arguments
 * @param argv Array of arguments
 * @param configParams Configuration parameters to populate
 * @param helpLevel Output parameter for help level (if help requested)
 * @return true if parsing successful, false if help requested or error
 */
bool parseCommandLineFlags(int argc, char* argv[], configParameters& configParams, int& helpLevel);

/**
 * @brief Print usage information with different detail levels
 * @param programName Name of the program
 * @param helpLevel Level of help detail (1=basic, 2=with examples)
 */
void printUsage(const char* programName, int helpLevel = 1);

#endif // COMMANDLINEPARSER_H
