// dataPacketProcessor.cpp
#include <filesystem>
#include <algorithm>


#include "dataPacketProcessor.h"
#include "diagnostics.h"
#include "structures.h"
#include "configReader.h"

using namespace std;

const double nanoSecondsToSeconds = 1E-9;

// Some global variables, constants, and containers
unsigned long long fileLength;
unsigned long long NumofPackets;

// TODO: Fix this! Possibly make it into a structure that is inherited 
double coarseTime;
unsigned long tmpFine;
unsigned long trigTimeFine;
double timeUnit = 25. / 4096; 
double global_timestamp;
int trigger_counter;
unsigned long long int timemaster;
double TDC_timestamp;
double spidrTimeInNs;
int x, y;
double timeOverThresholdNS;
double timeOfArrivalNS;
long dCol;
long sPix;
long pix;
unsigned short timeOverThreshold, timeOfArrival;
char fineTimeOfArrival;
int frameNr;
int coarseTimeOfArrival;
int mode;

// Needed for global time stamps
uint32_t timeStampLow_25nsClock = 0;    
uint16_t timeStampHigh_107sClock = 0;
uint16_t spidrTime = 0;
unsigned long Timer_LSB32 = 0;
unsigned long Timer_MSB16 = 0;

// Some buffer timing info for diagnostics
std::chrono::duration<double> bufferUnpackTime;
std::chrono::duration<double> bufferSortTime;
std::chrono::duration<double> bufferWriteTime;
std::chrono::duration<double> bufferClusterTime;


/**
 * @brief Resets global variables to clean state for processing new TPX3 files.
 * 
 * This function resets all global timing and processing variables to their default
 * values. This is essential for batch mode processing to prevent contamination
 * between files, which could lead to incorrect TDC counts and timing information.
 */
void resetGlobalVariables() {
    // Reset basic file processing variables
    fileLength = 0;
    NumofPackets = 0;
    
    // Reset timing variables
    coarseTime = 0.0;
    tmpFine = 0;
    trigTimeFine = 0;
    global_timestamp = 0.0;
    trigger_counter = 0;
    timemaster = 0;
    TDC_timestamp = 0.0;
    spidrTimeInNs = 0.0;
    
    // Reset pixel processing variables  
    x = 0;
    y = 0;
    timeOverThresholdNS = 0.0;
    timeOfArrivalNS = 0.0;
    dCol = 0;
    sPix = 0;
    pix = 0;
    timeOverThreshold = 0;
    timeOfArrival = 0;
    fineTimeOfArrival = 0;
    frameNr = 0;
    coarseTimeOfArrival = 0;
    mode = 0;
    
    // Reset global time stamp variables
    timeStampLow_25nsClock = 0;
    timeStampHigh_107sClock = 0;
    spidrTime = 0;
    Timer_LSB32 = 0;
    Timer_MSB16 = 0;
}


/**
 * @brief Get a list of all files in a directory of a specific type or extention.
 *
 * This function takes a configParameters structure as input and returns a vector of strings containing the full paths of all files in the directory specified by the rawTPX3Folder field of the configParameters structure. The function uses the filesystem library to iterate over the directory and obtain the full paths of all files within it. The function then returns a vector of strings containing the full paths of all files in the directory.
 *
 * @param configParams A const reference to the configParameters structure that includes control parameters for the operation, such as the directory containing the raw TPX3 files.
 * @return std::vector<std::string> A vector of strings containing the full paths of all files in the directory specified by the rawTPX3Folder field of the configParameters structure.
 * 
 */
std::vector<std::string> getFilesInDirectory(configParameters configParams){
    std::vector<std::string> files;
    // grab all files with a given extension of ".tpx3"
    for (const auto & entry : std::filesystem::directory_iterator(configParams.rawTPX3Folder)){
        if (entry.path().extension() == ".tpx3"){
            // only grab the file name and not the full path
            files.push_back(entry.path().filename().string());

            //files.push_back(entry.path().string());
        }
    }
    return files;
}


/**
 * @brief Sorts an array of signalData structures by the ToaFinal field and updates sorting time diagnostics.
 *
 * This function sorts an array of signalData structures in ascending order based on the ToaFinal field, 
 * The function also measures the duration of the sorting process using high-resolution clocks and updates
 *  the totalSortingTime field in the tpx3FileDiagnostics structure to facilitate performance diagnostics.
 * Additionally, it outputs a message indicating the start of the sorting operation if the verboseLevel in 
 * configParameters is set to 3 or higher.
 *
 * @param configParams A const reference to the configParameters structure that includes control 
 *                     parameters for the operation, such as the verbosity level for logging.
 * @param signalDataArray A pointer to the first element of an array of signalData structures to be sorted. 
 *                        The array is modified in place by the sorting operation. The length of this 
 *                        array is determined by the numberOfDataPackets field in tpx3FileInfo.
 * @param tpx3FileInfo A reference to a tpx3FileDiagnostics structure that is updated with the 
 *                     sorting duration. This structure also provides the number of data packets 
 *                     (elements) in signalDataArray that should be sorted.
 */
void sortSignals(const configParameters& configParams, signalData* signalDataArray, tpx3FileDiagnostics& tpx3FileInfo) {
    auto startSortTime = std::chrono::high_resolution_clock::now(); // Grab a start time for sorting
        
    // Print info depending on verbosity level
    if (configParams.verboseLevel>=2) {std::cout <<"Sorting " << tpx3FileInfo.numberOfDataPackets << " raw signal data. " << std::endl;}

    // Sort the signalDataArray based on ToaFinal
    std::sort(signalDataArray, signalDataArray + tpx3FileInfo.numberOfDataPackets,[](const signalData &a, const signalData &b) -> bool {return a.ToaFinal < b.ToaFinal;});
    
    // Grab stop time, calculate buffer sort duration, and append to total sorting time.
    auto stopSortTime = std::chrono::high_resolution_clock::now();
    bufferSortTime = stopSortTime - startSortTime;
    tpx3FileInfo.totalSortingTime = bufferSortTime.count();
    if (configParams.verboseLevel>=2) {std::cout <<"Finished sorting "<< tpx3FileInfo.numberOfDataPackets << " raw signals. " << std::endl;}
}


/**
 * @brief Clusters signal data based on the a selected algorithm and updates clustering time.
 *
 * Invokes a clustering algorithm (e.g., DBSCAN) to group pixels in the signalDataArray into clusters based on their properties.
 * The function measures the duration of the clustering process and updates the totalClusteringTime in the tpx3FileDiagnostics structure.
 * A message indicating the start of the clustering operation is printed if the verboseLevel in configParams is 3 or higher.
 * The actual clustering function (ST_DBSCAN or equivalent) should be defined elsewhere and is assumed to operate on the signalDataArray.
 *
 * @param configParams Configuration parameters, including the verbosity level for logging.
 * @param signalDataArray Array of signalData structures to be clustered. The array size is determined by numberOfDataPackets.
 * @param numberOfDataPackets The number of data packets (elements) in signalDataArray to be clustered.
 * @param tpx3FileInfo Diagnostics structure that is updated with the duration of the clustering operation.
 */

void clusterSignals(const configParameters& configParams, signalData* signalDataArray, tpx3FileDiagnostics& tpx3FileInfo) {
    if (configParams.verboseLevel >= 2) {std::cout << "Clustering pixels based on DBSCAN " << std::endl;}

    auto startClusterTime = std::chrono::high_resolution_clock::now();
    
    // Invoke the clustering algorithm.
    ST_DBSCAN(configParams, tpx3FileInfo, signalDataArray);

    auto stopClusterTime = std::chrono::high_resolution_clock::now();
    bufferClusterTime = stopClusterTime - startClusterTime;
    tpx3FileInfo.totalClusteringTime = bufferClusterTime.count();
    if (configParams.verboseLevel >= 2) {std::cout << "Finished clustering of " << tpx3FileInfo.numberOfDataPackets << " pixels based on DBSCAN " << std::endl;}
}


/**
 * @brief Opens a TPX3 file, calculates file size and number of data packets, updates diagnostic information, and returns an ifstream object.
 *
 * This function constructs the full path to a TPX3 file using the `configParameters` structure provided in `config`. 
 * It attempts to open the specified TPX3 file in binary mode. Upon successfully opening the file, it utilizes the filesystem 
 * library to securely obtain the file's size. It then calculates the number of data packets in the TPX3 file based on 
 * the file size and updates the `tpx3FileDiagnostics` structure `tpx3FileInfo` with this information. The function outputs 
 * relevant information to the console, depending on the verbosity level specified in `config`. If the file cannot be opened 
 * or if there is an error obtaining the file size, the function handles these errors appropriately by either throwing a runtime_error 
 * exception or closing the file and rethrowing the exception to ensure clean error handling and resource management. 
 * Finally, it returns the ifstream object associated with the opened file, allowing for further processing.
 *
 * @param config       The `configParameters` structure that holds control parameters for the operation, 
 * including the directory and filename of the TPX3 file, and the verbosity level for logging.
 * @param tpx3FileInfo A reference to a `tpx3FileDiagnostics` structure that will be updated with the file 
 * size and number of data packets. This structure should be used later for diagnostics and processing information.
 * @return std::ifstream An ifstream object associated with the opened TPX3 file. This object is used for subsequent file reading operations.
 * @throws std::runtime_error if the TPX3 file cannot be opened or if there is an error obtaining the file size.
 */
std::ifstream openTPX3File(const configParameters& configParams, tpx3FileDiagnostics& tpx3FileInfo) {
    // Construct the full path to the TPX3 file
    std::string fullTpx3Path = configParams.rawTPX3Folder + "/" + configParams.rawTPX3File;
    std::cout << "Opening TPX3 file at path: " << fullTpx3Path << std::endl;
    
    // Attempt to open the TPX3 file
    std::ifstream tpx3File(fullTpx3Path, std::ios::binary);
    
    // Check if the file stream is in a good state (i.e., the file has been successfully opened)
    if (!tpx3File) {
        // If the file cannot be opened, throw an exception
        throw std::runtime_error("Unable to open input TPX3 file at path: " + fullTpx3Path);
    }

    // Using filesystem to get file size securely and handling large files
    try {
        tpx3FileInfo.filesize = std::filesystem::file_size(fullTpx3Path);
        tpx3FileInfo.numberOfDataPackets = tpx3FileInfo.filesize / 8;
        if (configParams.verboseLevel >= 2) {
            std::cout << "File size: " << tpx3FileInfo.filesize << " bytes" << std::endl;
            std::cout << "Number of Data Packets: " << tpx3FileInfo.numberOfDataPackets << std::endl;
        }
    } catch (std::filesystem::filesystem_error& e) {
        std::cerr << "Error getting file size: " << e.what() << '\n';
        // Properly handle the error, such as by closing the file and rethrowing the exception
        tpx3File.close();
        throw;
    }
    
    return tpx3File; // Return the ifstream object associated with the opened file
}

/**
 * @brief Opens an output file for raw signals based on configuration parameters.
 *
 * If the writeRawSignals flag within the configParameters structure is set to true, this function constructs
 * the full path to the output file using the outputFolder and runHandle specified in config. It then attempts
 * to open this file for binary output. If the file is successfully opened, it returns an ofstream object
 * associated with the file. If writeRawSignals is false or the file cannot be opened, it handles the
 * situation appropriately, either by not attempting to open the file or by throwing an exception.
 *
 * @param config         The configParameters structure containing the output file configuration, including
 *                       the output folder, run handle, and the flag indicating whether to write raw signals.
 * @return std::ofstream An ofstream object for the output file. If writeRawSignals is false, this ofstream
 *                       may not be opened (check with is_open() before using).
 * @throws std::runtime_error If the file cannot be opened when writeRawSignals is true.
 */
std::ofstream openRawSignalsOutputFile(const configParameters& configParams) {
    std::ofstream rawSignalsFile;

    // Construct the full path to the output file
    std::string fullOutputPath = configParams.outputFolder + "/" + configParams.runHandle + ".rawSignals";
    std::cout << "Opening output file for raw signals at path: " << fullOutputPath << std::endl;

    // Attempt to open the output file
    rawSignalsFile.open(fullOutputPath, std::ios::out | std::ios::binary);

    // Check if the file stream is in a good state (i.e., the file has been successfully opened)
    if (!rawSignalsFile) {
        // If the file cannot be opened, throw an exception
        throw std::runtime_error("Unable to open output file for raw signals at path: " + fullOutputPath);
    }
    // Return the ofstream object associated with the opened file
    // Note: If writing is disabled, this returns an unopened ofstream, which the caller needs to check
    return rawSignalsFile;
}


/**
 * @brief Writes raw signal data to a file and updates writing duration.
 *
 * Logs the operation if verboseLevel is 3 or higher, writes the raw signal data from signalDataArray to 
 * the file associated with rawSignalsFile, and updates tpx3FileInfo's totalWritingTime with the duration 
 * of the write operation. Assumes rawSignalsFile is open and ready for writing.
 *
 * @param configParams Configuration parameters, including verboseLevel for logging.
 * @param rawSignalsFile Open ofstream for writing raw signal data.
 * @param signalDataArray Array of signalData to be written.
 * @param tpx3FileInfo Diagnostics structure to be updated with writing time.
 */
void writeRawSignals(const configParameters& configParams, std::ofstream& rawSignalsFile, const signalData* signalDataArray, tpx3FileDiagnostics& tpx3FileInfo) {

    if (configParams.verboseLevel >= 3) {std::cout << "Writing out raw signal data." << std::endl;}

    auto startWriteTime = std::chrono::high_resolution_clock::now(); // Grab a start time for writing

    // Perform the writing operation
    rawSignalsFile.write(reinterpret_cast<const char*>(signalDataArray), sizeof(signalData) * tpx3FileInfo.numberOfDataPackets);

    // Calculate and update the total writing time
    auto stopWriteTime = std::chrono::high_resolution_clock::now();
    bufferWriteTime = stopWriteTime - startWriteTime;
    tpx3FileInfo.totalWritingTime = bufferWriteTime.count();
    if (configParams.verboseLevel >= 3) {std::cout << "Finished writing out raw signal data." << std::endl;}
}


/**
 * @brief Takes a TDC data packet from a tpx3 file, processes it, and updates the corresponding signal data structure. 
 *
 * This function takes the data packet pass through unsigned long long dataPacket and processes the timing of 
 * the TDC trigger. It then update the corresponding signalData structure, which is passed by reference. 
 * 
 * @param dataPacket    64 byte data packet that contains raw timing info
 * @param signalData    HERMES defined structure that contain raw data info from data packets.
 * @return nothing
 */
void processTDCPacket_old(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData) {
    // Logic for TDC packet

	// Unpack dataPacket
	coarseTime = (dataPacket >> 12) & 0xFFFFFFFF;                        
	tmpFine = (dataPacket >> 5) & 0xF; 
	tmpFine = ((tmpFine - 1) << 9) / 12;
	trigTimeFine = (dataPacket & 0x0000000000000E00) | (tmpFine & 0x00000000000001FF);

	// Set info in signalData 
    signalData.bufferNumber = bufferNumber;
    signalData.signalType = 1;
	signalData.xPixel = 0;
	signalData.yPixel = 0;
	signalData.ToaFinal = coarseTime*25*nanoSecondsToSeconds + trigTimeFine*timeUnit*nanoSecondsToSeconds;
	signalData.TotFinal = 0;
}


/**
 * @brief Takes a TDC data packet from a tpx3 file, processes it, and updates the corresponding signal data structure. 
 *
 * This function takes the data packet pass through unsigned long long dataPacket and processes the timing of 
 * the TDC trigger. It then update the corresponding signalData structure, which is passed by reference. 
 * 
 * @param dataPacket    64 byte data packet that contains raw timing info
 * @param signalData    HERMES defined structure that contain raw data info from data packets.
 * @return nothing
 */
void processTDCPacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData) {
    // Extract according to manual specification
    uint64_t timestamp = (dataPacket >> 9) & 0x7FFFFFFFF;  // Bits 43-9 (35 bits)
    uint8_t stamp = (dataPacket >> 5) & 0xF;               // Bits 8-5 (4 bits)
    
    // Calculate time according to manual
    double timestampNs = timestamp * 3.125;  // 320MHz -> nanoseconds
    double stampNs = (stamp != 0) ? stamp * 0.260 : 0.0;  // 260 ps -> nanoseconds
    
    double finalTimestampNs = timestampNs + stampNs;
    
    // Set info in signalData 
    signalData.bufferNumber = bufferNumber;
    signalData.signalType = 1;
    signalData.xPixel = 0;
    signalData.yPixel = 0;
    signalData.ToaFinal = finalTimestampNs * nanoSecondsToSeconds;  // Convert to seconds
    signalData.TotFinal = 0;
}


/**
 * @brief Takes a Pixel data packet from a tpx3 file, processes it, and updates the corresponding signal data structure. 
 *
 * This function takes the data packet pass through unsigned long long dataPacket and processes the timing and position of 
 * the Pixel hit. It then update the corresponding signalData structure, which is passed by reference. 
 * 
 * TODO: I need to rewrite this for clarity. 
 * 
 * @param dataPacket    64 byte data packet that contains raw timing info
 * @param signalData    HERMES defined structure that contain raw data info from data packets.
 * @return nothing
 */ 
void processPixelPacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData) {
    // Unpack dataPacket
    spidrTime = (unsigned short)(dataPacket & 0xffff);
    dCol = (dataPacket & 0x0FE0000000000000L) >> 52;                                                                  
    sPix = (dataPacket & 0x001F800000000000L) >> 45;                                                                    
    pix = (dataPacket & 0x0000700000000000L) >> 44;
    x = (int)(dCol + pix / 4);
    y = (int)(sPix + (pix & 0x3));
    timeOfArrival = (unsigned short)((dataPacket >> (16 + 14)) & 0x3fff);   
    timeOverThreshold = (unsigned short)((dataPacket >> (16 + 4)) & 0x3ff);	
    fineTimeOfArrival = (unsigned char)((dataPacket >> 16) & 0xf);
    coarseTimeOfArrival = (timeOfArrival << 4) | (~fineTimeOfArrival & 0xf);
    spidrTimeInNs = spidrTime * 25.0 * 16384.0;
    //timeOfArrivalNS = timeOfArrival * 25.0;
    timeOverThresholdNS = timeOverThreshold * 25.0;	
    global_timestamp = spidrTimeInNs + coarseTimeOfArrival * (25.0 / 16);
    
    // Set info in signalData 
    signalData.bufferNumber = bufferNumber;
    signalData.signalType = 2;
	signalData.xPixel = x;
	signalData.yPixel = y;
	signalData.ToaFinal = global_timestamp / 1E9;
	signalData.TotFinal = timeOverThresholdNS;
}


/**
 * @brief Takes a Global Time Stamp data packet from a tpx3 file, processes it, 
 * and updates the corresponding signal data structure. 
 *
 * This function takes the data packet pass through unsigned long long dataPacket and processes the timing of 
 * the Global Time Stamp hit. It then update the corresponding signalData structure, which is passed by reference. 
 * 
 * TODO: I need to rewrite this for clarity. Also need to figure out logic for time stamps.  
 * 
 * @param dataPacket    64 byte data packet that contains raw timing info
 * @param signalData    HERMES defined structure that contain raw data info from data packets.
 * @return nothing
 */ 
void processGlobalTimePacket(uint16_t bufferNumber, uint64_t dataPacket, signalData &signalData) {
    // Logic for Global time packet
    uint8_t timeType = static_cast<uint8_t>((dataPacket >> 56) & 0xFF);                        

    // Time Low packet
    if (timeType == 0x44) {
        timeStampLow_25nsClock = static_cast<uint32_t>((dataPacket >> 16) & 0xFFFFFFFF);    // Extract 32-bit timestamp
        spidrTime = static_cast<uint16_t>(dataPacket & 0xFFFF);                             // Extract 16-bit SPIDR time
        global_timestamp = timeStampLow_25nsClock*25E-9;

    // Time High packet
    } else if (timeType == 0x45) { 
        timeStampHigh_107sClock = static_cast<uint16_t>((dataPacket >> 16) & 0xFFFF);       // Extract 16-bit timestamp
        spidrTime = static_cast<uint16_t>(dataPacket & 0xFFFF);                             // Extract 16-bit SPIDR time
        global_timestamp = timeStampHigh_107sClock*107.374182;
    }

    // Set info in signalData 
    signalData.bufferNumber = bufferNumber;
    signalData.signalType = 3;
    signalData.xPixel = 0;
    signalData.yPixel = 0;
    signalData.ToaFinal = global_timestamp;
    signalData.TotFinal = spidrTime;
	
}

/**
 * @brief Takes a SPIDR control packet from a tpx3 file, processes it, 
 * and updates the corresponding signal data structure. 
 *
 * This function takes the data packet pass through unsigned long long dataPacket and processes the timing of 
 * the SPIDR control flag. It then update the corresponding signalData structure, which is passed by reference. 
 * 
 * TODO: Need to get logic for unpacking from ASI.  
 * 
 * @param dataPacket    64 byte data packet that contains raw timing info
 * @param signalData    HERMES defined structure that contain raw data info from data packets.
 * @return nothing
 */ 
void processSPIDRControlPacket(uint16_t bufferNumber, uint64_t dataPacket, signalData &signalData) {

    // Set info in signalData 
    signalData.bufferNumber = bufferNumber;
    signalData.signalType = 4;
    signalData.xPixel = 0;
    signalData.yPixel = 0;
    signalData.ToaFinal = 0;
    signalData.TotFinal = 0;
	
}

/**
 * @brief Takes a TPX3 control packet from a tpx3 file, processes it, 
 * and updates the corresponding signal data structure. 
 *
 * This function takes the data packet pass through unsigned long long dataPacket and processes the timing of 
 * the TPX3 control flag. It then update the corresponding signalData structure, which is passed by reference. 
 * 
 * TODO: Need to get logic for unpacking from ASI.  
 * 
 * @param dataPacket    64 byte data packet that contains raw timing info
 * @param signalData    HERMES defined structure that contain raw data info from data packets.
 * @return nothing
 */ 
void processTPX3ControlPacket(uint16_t bufferNumber, uint64_t dataPacket, signalData &signalData) {

    // Set info in signalData 
    signalData.bufferNumber = bufferNumber;
    signalData.signalType = 5;
    signalData.xPixel = 0;
    signalData.yPixel = 0;
    signalData.ToaFinal = 0;
    signalData.TotFinal = 0;
	
}


void processDataPackets(const configParameters& configParams, tpx3FileDiagnostics& tpx3FileInfo, const uint64_t* dataPackets, signalData* signalDataArray) {
    
    // Grab a START time for unpacking
    auto startUnpackTime = std::chrono::high_resolution_clock::now(); 
    if(configParams.verboseLevel >=2){std::cout << "Unpacking " << configParams.maxPacketsToRead << " raw signals from " << configParams.rawTPX3File << std::endl;}

    // Convert "TPX3" string to uint32_t in little endian format
    const char tpx3SignatureStr[] = "TPX3";
    uint32_t tpx3Signature;
    memcpy(&tpx3Signature, tpx3SignatureStr, sizeof(uint32_t));

    size_t currentPacket = 0;       // Initialize the counter outside the while loop
    tpx3FileInfo.numberOfBuffers = 1;
    
    // Continue to loop through dataPacket array until you hit the numberOfDataPackets 
    while (currentPacket < configParams.maxPacketsToRead) {
        
        // Grab last 32 bits of current packet
        uint32_t tpx3flag = static_cast<uint32_t>(dataPackets[currentPacket]);
        
        // If tpx3flag matches the "TPX3" then you found a chuck header
        if (tpx3flag == tpx3Signature) {

            // Start processing the chuck header to get size and number of data packets in chuck. 
            uint16_t chunkSize = static_cast<uint16_t>((dataPackets[currentPacket] >> 48) & 0xFFFF);
            uint16_t numPacketsInChunk = chunkSize / 8;
            if(configParams.verboseLevel >= 3){std::cout << std::dec << currentPacket << ":-: Found TPX3 chunk header with " << numPacketsInChunk << " packets."<<std::endl;}

            tpx3FileInfo.numberOfProcessedPackets++; // processed a chunk header packet so increment processed packets
            currentPacket++;    // move onto the next packet

            // Ensure we do not process more packets than the maxPacketsToRead limit
            if (tpx3FileInfo.numberOfProcessedPackets + numPacketsInChunk > configParams.maxPacketsToRead) {
                numPacketsInChunk = configParams.maxPacketsToRead - tpx3FileInfo.numberOfProcessedPackets;
                if(configParams.verboseLevel >= 3){std::cout << "MESSAGE: Shortening numPacketsInChunk to " << numPacketsInChunk << std::endl;}
            }

            // Iterate through each data packet in the current chunk
            for (uint16_t chunkPacketIndex = 0; chunkPacketIndex < numPacketsInChunk; ++chunkPacketIndex) {

                // Checking to make sure we are not reading a TPX3 chunk header packet
                // Grab last 32 bits of current packet
                uint32_t tpx3flag = static_cast<uint32_t>(dataPackets[currentPacket]);
                if (tpx3flag == tpx3Signature){ std::cout << "ERROR: FOUND a TPX3 chunk header before finishing with current buffer...";}

                // Safeguard against going beyond the allocated memory
                if (currentPacket >= tpx3FileInfo.numberOfDataPackets){ 
                    if(configParams.verboseLevel >= 3){std::cout << "Current Packet beyond " <<  tpx3FileInfo.numberOfDataPackets << ". Breaking out of process loop." << std::endl;}
                    break;
                }

                // Extract the packet type from the most significant nibble
                uint8_t packetType = static_cast<uint8_t>((dataPackets[currentPacket] >> 60) & 0xF);

                switch (packetType) {
                    case 0xA: // Integrated ToT mode
                        std::cout << "Integrated ToT mode packet detected." << std::endl;
                        break;
                    case 0xB: // Time of Arrival mode
                        processPixelPacket(tpx3FileInfo.numberOfBuffers, dataPackets[currentPacket], signalDataArray[currentPacket]);

                        if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" <<chunkPacketIndex << ": Pixel data packet" << std::endl;}
                        
                        tpx3FileInfo.numberOfProcessedPackets++; // Update number of packets processed
                        tpx3FileInfo.numberOfPixelHits++;
                        break;
                    case 0x6: // TDC data packets
                        processTDCPacket(tpx3FileInfo.numberOfBuffers, dataPackets[currentPacket], signalDataArray[currentPacket]);

                        if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" << chunkPacketIndex << ": TDC data packet" << std::endl;}
                        
                        tpx3FileInfo.numberOfProcessedPackets++; // Update number of packets processed
                        tpx3FileInfo.numberOfTDC1s++;
                        break;
                    case 0x4: // Global time data packets
                        processGlobalTimePacket(tpx3FileInfo.numberOfBuffers, dataPackets[currentPacket], signalDataArray[currentPacket]);

                        if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" << chunkPacketIndex << ": Global time stamp data packet" << std::endl;}
                        
                        tpx3FileInfo.numberOfProcessedPackets++; // Update number of packets processed
                        tpx3FileInfo.numberOfGTS++;
                        break;
                        
                    case 0x5: { // SPIDR control packets, note the added braces to introduce a new block scope
                        uint8_t subType = static_cast<uint8_t>((dataPackets[currentPacket] >> 56) & 0xF);
                        switch (subType) {
                            case 0xF:
                                if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" << chunkPacketIndex << ": Open shutter packet detected." << std::endl;}
                                break;
                            case 0xA:
                                if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" << chunkPacketIndex << ": Close shutter packet detected." << std::endl;}
                                break;
                            case 0xC:
                                if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" << chunkPacketIndex << ": Heartbeat packet detected." << std::endl;}
                                break;
                            default:
                                if(configParams.verboseLevel >= 4){std::cout << std::dec << currentPacket << ":" << chunkPacketIndex << ": Unknown SPIDR control packet subtype detected." << std::endl;}
                                break;
                        }

                        processSPIDRControlPacket(tpx3FileInfo.numberOfBuffers, dataPackets[currentPacket], signalDataArray[currentPacket]);
                        tpx3FileInfo.numberOfProcessedPackets++; // Update number of packets processed
                        break;
                    }
                    case 0x7: { // TPX3 control packets, again note the added braces
                        uint8_t controlType = static_cast<uint8_t>((dataPackets[currentPacket] >> 48) & 0xFF);
                        if (controlType ==0xA0) {
                            if(configParams.verboseLevel >= 4){
                                std::cout << "End of sequential readout detected with "<< std::hex << "packetType: 0x" << +packetType << "\t"<< "controlType: 0x" << +controlType << std::endl;
                            }

                        } else if (controlType == 0xB0) {
                            if(configParams.verboseLevel >= 4){
                                std::cout << "End of data driven readout detected with "<< std::hex << "packetType: 0x" << +packetType << "\t"<< "controlType: 0x" << +controlType << std::endl;
                            }
                        } else {
                            if(configParams.verboseLevel >= 4){
                            // Print out the hex value of controlType
                                std::cout << currentPacket << ":" << chunkPacketIndex << ": Unkown TPX3 control packets detected with "
                                << "packetType: 0x"<< std::hex << +packetType << "\t"
                                << "controlType: 0x" << controlType << std::endl;
                            }
                        }
                        
                        processTPX3ControlPacket(tpx3FileInfo.numberOfBuffers, dataPackets[currentPacket], signalDataArray[currentPacket]);
                        tpx3FileInfo.numberOfProcessedPackets++; // Update number of packets processed
                        tpx3FileInfo.numberOfTXP3Controls++;
                        break;
                    }
                }

                currentPacket++;

                // Break out of the loop if processedPackets reaches maxPacketsToRead
                if (tpx3FileInfo.numberOfProcessedPackets >= configParams.maxPacketsToRead) {break;}
            }
            
            // Update number of buffers processed. instead
            if (tpx3FileInfo.numberOfBuffers == 0){std::cout << "Buffer Number 0" << std::endl;}
            tpx3FileInfo.numberOfBuffers++;
            
        } else {
            std::cout << "ERROR: Could not find TPX3 Flag, instead found " << std::hex << +tpx3flag << endl;
            currentPacket++;
        }
    }

    // Grab stop time, calculate buffer unpacking duration, and append to total unpacking time.
    auto stopUnpackTime = std::chrono::high_resolution_clock::now(); // Grab a STOP time for unpacking
    bufferUnpackTime = stopUnpackTime - startUnpackTime;
    tpx3FileInfo.totalUnpackingTime = tpx3FileInfo.totalUnpackingTime + bufferUnpackTime.count();
    tpx3FileInfo.numberOfDataPackets = currentPacket;
    if(configParams.verboseLevel >= 2){std::cout << "Unpacked "<< currentPacket << " data packets, processed "<< tpx3FileInfo.numberOfProcessedPackets << " data packets" << std::endl;}
}


/**
 * @brief  Unpacks a TPX3 file, sorts the signals, clusters the pixels, and writes raw signals to a file.
 * 
 * @param configParams    64 byte data packet that contains raw timing info
 * 
 * @return tpx3FileDiagnostics  HERMES defined structure that contains various diagnostic info used during the unpacking processes
 */ 
tpx3FileDiagnostics unpackAndSortTPX3File(configParameters configParams){
    
    std::ifstream tpx3File;             // initiate a input file-stream for reading in TPX3file
    std::ofstream rawSignalsFile;       // initiate a output file-stream for writing raw data
    tpx3FileDiagnostics tpx3FileInfo;    // initiate container for diagnostics while unpacking.

    // TODO: Combine these two once better error handling is implemented. 
    // Open the TPX3File
    try {tpx3File = openTPX3File(configParams,tpx3FileInfo);} 
    catch (const std::runtime_error& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return {};  // Handle the error as needed, possibly returning an error code or an empty object
    }  
    // If writeRawSignals is ``true, attempt to open the output file for raw signals
    if(configParams.writeRawSignals == true){
    // If writeRawSignals is true, attempt to open the output file for raw signals
        try {rawSignalsFile = openRawSignalsOutputFile(configParams);} 
        catch (const std::runtime_error& e) {
            std::cerr << "Error: " << e.what() << std::endl;
            return {}; // Handle the errors needed, possibly returning an error code or an empty object
        }
    }

    // Ensure maxPacketsToRead does not exceed the total number of available packets
    size_t packetsToRead = std::min(static_cast<size_t>(configParams.maxPacketsToRead), static_cast<size_t>(tpx3FileInfo.numberOfDataPackets));
    
    // If maxPacketsToRead is set to zero then read entire tpx3File and set maxPacketsToRead to numberOfDataPackets
    if(configParams.maxPacketsToRead == 0){
        packetsToRead = tpx3FileInfo.numberOfDataPackets;
        configParams.maxPacketsToRead = tpx3FileInfo.numberOfDataPackets;
    } else {
        // Update maxPacketsToRead to reflect the actual number of packets we'll process
        // This ensures processDataPackets doesn't try to read beyond available data
        configParams.maxPacketsToRead = packetsToRead;
    }

    // Allocate an array for tpx3DataPackets to store signals up to the maxPacketsToRead from the TPX3 file
    uint64_t* tpx3DataPackets = new uint64_t[packetsToRead];
    
    // Calculate the number of bytes to read based on the number of packets
    size_t bytesToRead = packetsToRead * sizeof(uint64_t);
    
    // Read the calculated number of bytes from the TPX3 file
    if(configParams.verboseLevel>=2){std::cout << "Reading tpx file "<<  configParams.runHandle << " into memory" << std::endl;}
    tpx3File.read((char*)tpx3DataPackets, bytesToRead);
    if(configParams.verboseLevel>=2){std::cout << "Closing tpx3 file" << configParams.runHandle << std::endl;}
    tpx3File.close();

    // allocate an array of signalData called signalDataArray that is the same size as bufferSize//8
    signalData* signalDataArray = new signalData[packetsToRead];
    
    // Process the data packets and fill the signalDataArray
    processDataPackets(configParams, tpx3FileInfo,  tpx3DataPackets, signalDataArray);

    // If sortSignals is true then sort!! 
    if (configParams.sortSignals){sortSignals(configParams, signalDataArray, tpx3FileInfo);}        

    // If writeRawSignals is true then write out binary
    if (configParams.writeRawSignals){writeRawSignals(configParams, rawSignalsFile, signalDataArray, tpx3FileInfo);}   

    // If clusterPixels is true, then cluster signals
    if (configParams.clusterPixels){clusterSignals(configParams, signalDataArray, tpx3FileInfo);}
    
    delete[] tpx3DataPackets;   // Don't forget to free the allocated memory
    delete[] signalDataArray;   // Assuming you're done with signalDataArray
    return tpx3FileInfo;        // Return the tpx3file info. 
}

/**
 * @brief Processes TPX3 files based on the configuration parameters.
 * 
 * This function processes TPX3 files based on the configuration parameters provided. It can process a single file or all files in a directory,
 * depending on the batchMode flag in the configParameters structure. The function prints out information based on the verbosity level specified in the configParameters.
 * 
 * 
 * @param  configParams    Configuration parameters for the operation, including the verbosity level for logging.
 * @param  verboseLevel    Verbosity level for logging (default is 0).
 * 
 * @return nothing
 */
void processTPX3Files(configParameters configParams){

    tpx3FileDiagnostics tpxFileInfo;

    // Print out config parameters based on verbosity level
    if(configParams.verboseLevel>=2){printParameters(configParams);}

    // Check for bacthMode
    if (configParams.batchMode){
        if (configParams.verboseLevel >= 1){
            std::cout << "Batch mode is enabled. Processing all files in the directory." << std::endl;
        }
        // Get a list of all the files in the directory
        std::vector<std::string> tpx3Files = getFilesInDirectory(configParams);
        // Loop through all the files in the directory
        for (const auto& tpx3File : tpx3Files){

            // Reset global variables to prevent contamination between files
            resetGlobalVariables();
            if (configParams.verboseLevel >= 2) {
                std::cout << "Global variables reset for file: " << tpx3File << std::endl;
            }

            // Grab start time for unpacking
            std::chrono::duration<double> hermesTime;
            auto hermesStartTime = std::chrono::high_resolution_clock::now();

            // Set the rawTPX3File to the current file
            configParams.rawTPX3File = tpx3File;

            // Set the handle to the current file
            configParams.runHandle = grabRunHandle(tpx3File);

            // Process the single file
            std::cout << "Processing file: " << tpx3File << std::endl;  
            tpxFileInfo = unpackAndSortTPX3File(configParams);

            // Grab stop time for unpacking and calculate total times
            auto hermesStopTime = std::chrono::high_resolution_clock::now();
            hermesTime = hermesStopTime - hermesStartTime;
            tpxFileInfo.totalHermesTime = hermesTime.count();

            // Print out diagnostics based on verbosity level
            if(configParams.verboseLevel>=2){printOutUnpackingDiagnostics(tpxFileInfo);}
            
        }

    } else {
        // Process a single file

        // Grab start time for unpacking
        std::chrono::duration<double> hermesTime;
        auto hermesStartTime = std::chrono::high_resolution_clock::now();

        // Process the single file
        tpxFileInfo = unpackAndSortTPX3File(configParams);
        
        // Grab stop time for unpacking and calculate total times
        auto hermesStopTime = std::chrono::high_resolution_clock::now();
        hermesTime = hermesStopTime - hermesStartTime;
        tpxFileInfo.totalHermesTime = hermesTime.count();

        // Print out diagnostics based on verbosity level
        if(configParams.verboseLevel>=2){printOutUnpackingDiagnostics(tpxFileInfo);}
    }
}












