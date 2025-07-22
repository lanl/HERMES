#ifndef STRUCTURES_H
#define STRUCTURES_H

#include <cstdint>
#include <string>

struct configParameters {
    // Input options
    std::string rawTPX3Folder;  // Directory where raw TPX3 files are located
    std::string rawTPX3File;    // Specific TPX3 file to process
    std::string runHandle;      // Name of the run number that is being processed.
    bool batchMode = false;     // Flag to run in batch mode
    
    // Output options
    bool writeRawSignals = true;    // Flag to write out rawsignals in binrary
    std::string outputFolder = "."; // Default to current directory
    
    // Sorting options
    bool sortSignals = true;        // Flag to sort signals
    
    // Basic Clustering Options
    bool clusterPixels = false;
    uint8_t epsSpatial = 0;
    double epsTemporal = 0;
    uint8_t minPts = 0;
    uint16_t queryRegion = 0;
    bool writeOutPhotons = true;    // Flag to write out Photon data in binrary

    //Diagnostic options
    uint32_t maxPacketsToRead = 0;  // Number of buffer to read in. 0 means read all buffers. 
    bool fillHistograms = false;    // Flag to fill histograms
    int verboseLevel = 1;           // Verbosity Level
                                    // 0 = be quite, print nothing!
                                    // 1 = General file input/output
                                    // 2 = Config and event diagnostics
                                    // 3 = Buffer diagnostics
                                    // 4 = packet diagnostics
};

// This structure is used to contain various diagnostic info used during the unpacking processes (in dataPacketProcessor class)
struct tpx3FileDiagnostics {
    size_t filesize = 0;                 // size in bytes of tpx3 file
    size_t numberOfDataPackets = 0;       // number of data packets
    size_t numberOfProcessedPackets = 0;  // number of processed data packets
    size_t numberOfBuffers = 0;           // number of buffers 
    size_t numberOfPixelHits = 0;         // number of pixel hits
    size_t numberOfTDC1s = 0;             // number of TDC1 triggers
    size_t numberOfTDC2s = 0;             // number of TDC2 triggers
    size_t numberOfGTS = 0;               // number of global time stamps.
    size_t numberOfTXP3Controls = 0;      // number of TPX3 Control packets.

    double totalHermesTime = 0;
    double totalUnpackingTime = 0;
    double totalSortingTime = 0;
    double totalClusteringTime = 0;
    double totalWritingTime = 0;
};

// Represents the data for a single raw signal.
struct signalData {
    uint32_t bufferNumber;  // Buffer number from where signal was recorded
    uint8_t signalType;     // Type of the signal (TDC=1,Pixel=2,GTS=3)
    uint8_t xPixel;         // X-coordinate of the pixel
    uint8_t yPixel;         // Y-coordinate of the pixel
    double ToaFinal;        // Time of Arrival in seconds (final value)
    uint16_t TotFinal;      // Time over Threshold in nano seconds (final value)
    uint32_t groupID;       // Group ID for clustering. 
};

// Represents the data for a single reconstructed photon.
struct photonData{
    float photonX = 0;
    float photonY = 0;
    double photonToa = 0;
    uint16_t integratedTot = 0;
    uint8_t multiplicity = 0;
};

#endif
