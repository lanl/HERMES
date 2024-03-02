#include <chrono>

// HERMES defined functions 
#include "dataPacketProcessor.h"
#include "structures.h"
#include "diagnostics.h"
#include "photonRecon.h"
#include "configReader.h"

using namespace std;

int main(int argc, char *argv[]){  

    std::chrono::duration<double> hermesTime;
    auto hermesStartTime = std::chrono::high_resolution_clock::now();

    configParameters configParams;
    tpx3FileDianostics tpxFileInfo;

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

    // Print out config parameters based on vebosity level
    if(configParams.verboseLevel>=2){printParameters(configParams);}
    
    //tpxFileInfo = unpackandSortTPX3FileInSequentialBuffers(configParams);
    tpxFileInfo = unpackAndSortEntireTPX3File(configParams);

    auto hermesStopTime = std::chrono::high_resolution_clock::now();
    hermesTime = hermesStopTime - hermesStartTime;
    tpxFileInfo.totalHermesTime = hermesTime.count();

    if(configParams.verboseLevel>=2){printOutUnpackingDiagnostics(tpxFileInfo);}

	return 0;
}