/**
 * @file tpx3SpidrUnpacker.cpp
 * @brief Main entry point for the TPX3 SPIDR data unpacking application.
 *
 * This program can be used in multiple ways:
 * 1. ./tpx3SpidrUnpacker -i <input_file> [options...]
 * 2. ./tpx3SpidrUnpacker -c <config_file> [options...]
 * 3. ./tpx3SpidrUnpacker -I <input_dir> [options...]
 *
 * The flag-based interface allows for flexible configuration with the ability
 * to override config file settings via command-line flags.
 */

#include <chrono>
#include <iostream>

// HERMES defined functions 
#include "dataPacketProcessor.h"
#include "structures.h"
#include "diagnostics.h"
#include "photonRecon.h"
#include "configReader.h"
#include "commandLineParser.h"

using namespace std;

int main(int argc, char *argv[]){  

    configParameters configParams;
    int helpLevel = 0;

    // Check for the number of command-line arguments
    if (argc < 2) {
        cerr << "Error: Please provide command-line arguments." << endl;
        printUsage(argv[0]);
        return 1;
    }

    string firstArg = argv[1];
    
    // Case 1: Help requested
    if (firstArg == "-h" || firstArg == "--help") {
        // Check if next argument is a number for help level
        if (argc > 2 && argv[2][0] != '-') {
            helpLevel = parseIntOrDefault(argv[2], 1);
            if (helpLevel < 1 || helpLevel > 2) {
                helpLevel = 1;  // Default to level 1 if invalid
            }
        } else {
            helpLevel = 1;  // Default help level
        }
        printUsage(argv[0], helpLevel);
        return 0;
    }
    
    // Case 2: Flag-based parsing (starts with -)
    else if (firstArg[0] == '-') {
        if (!parseCommandLineFlags(argc, argv, configParams, helpLevel)) {
            if (helpLevel > 0) {
                // Help was requested during parsing
                printUsage(argv[0], helpLevel);
            } else {
                // Error occurred
                printUsage(argv[0]);
            }
            return (helpLevel > 0) ? 0 : 1;
        }
        
        cout << "Using flag-based configuration:" << endl;
        if (configParams.batchMode) {
            cout << "Input directory: " << configParams.rawTPX3Folder << endl;
            cout << "Batch mode: ALL files" << endl;
        } else {
            cout << "Input file: " << configParams.rawTPX3Folder << "/" << configParams.rawTPX3File << endl;
        }
        cout << "Output folder: " << configParams.outputFolder << endl;
        cout << "Verbose level: " << configParams.verboseLevel << endl;
    }
    else {
        cerr << "Error: Unrecognized option. Please use flags starting with '-' or '--'." << endl;
        cerr << "Provided: " << firstArg << endl;
        cout << "Note: To use a config file, use: -c <config_file>" << endl;
        printUsage(argv[0]);
        return 1;
    }

    processTPX3Files(configParams);

	return 0;
}