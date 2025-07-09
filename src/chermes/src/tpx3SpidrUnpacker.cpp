/**
 * @file tpx3SpidrUnpacker.cpp
 * @brief Main entry point for the TPX3 SPIDR data unpacking application.
 *
 * This program reads a configuration file specified as a command-line argument,
 * parses the configuration parameters, and processes TPX3 data files accordingly.
 * It utilizes several HERMES-defined modules for data packet processing, diagnostics,
 * photon reconstruction, and configuration management.
 *
 * Usage:
 *   ./tpx3SpidrUnpacker <config_file_path>
 *
 * The program will exit with an error message if the configuration file cannot be read.
 */

#include <chrono>

// HERMES defined functions 
#include "dataPacketProcessor.h"
#include "structures.h"
#include "diagnostics.h"
#include "photonRecon.h"
#include "configReader.h"

using namespace std;

int main(int argc, char *argv[]){  

    configParameters configParams;

    // Check for the number of command-line arguments
    if (argc < 2) {
        std::cerr << "Please provide the path to the config file as a command-line argument." << std::endl;
        return 1; // Exit the program with an error code
    }
    // Use the command-line argument for the config file path
    const char* configFilePath = argv[1];

    // Check if the configuration file was successfully read
    if(!readConfigFile(configFilePath, configParams)) {
        std::cerr << "Error: Failed to read configuration file: " << configFilePath << std::endl;
        return 1; // Exit the program with an error code
    } 

    processTPX3Files(configParams);

	return 0;
}