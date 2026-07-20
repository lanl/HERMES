#include <iomanip> // Include for setw and setprecision

// HERMES defined libraries
#include "diagnostics.h"

using namespace std;

// TODO: Figure out if you still need these otherwise delete them.
int numberOfHeaders = 0;
int numberOfBuffers = 0;
int numberOfTDCPackets = 0;
int numberOfPixelPackets = 0;
int numberOfGlobalTSPackets = 0;
int numberOfPhotons = 0;

/**
 * @brief converts signal type numbers to more descriptive strings
 *
 * This function function takes a HERMES defined structure tpx3FileDianostics
 * and prints out most of the diagnostic info that might be desired in 
 *
 * @param signalType int of signal types (e.g. 1,2,3,..)
 * @return string description of signal type
 */
string signalTypeToString(int signalType) {
    switch (signalType) {
        case 1: return "TDC";
        case 2: return "Pixel";
        case 3: return "GTS";
        default: return "Unknown";
    }
}

/**
 * @brief Prints out group ID info for all data in a single TPX3 data buffer.
 *
 * This function function loops through the singalData and the corresponding signalGroupID arrays
 * and prints out a table of signalType, xPixel, yPixel, ToaFinal, TotFinal, and groupID. 
 * Here groupID is assigned from some sorting algorithm, such as DBSCAN. 
 *
 * TODO: Add a output file instead of printing to terminal. 
 * 
 * @param buffernNumber         the buffer number from which the singalData was taking from.
 * @param signalDataArray       the array of raw signal data from a TPX3 file, such as pixelHit, TDCs, or global time stamps.
 * @param signalGroupID         the corresponding sorted IDs for all the raw signal data.
 * @param dataPacketsInBuffer   Number of data packets in buffer. 
 * @return nothing
 */
void printGroupIDs(int buffernNumber, signalData* signalDataArray, int16_t* signalGroupID, size_t dataPacketsInBuffer) {
    // Loop through dataPacketsInBuffer and print out each field. 
    for (size_t i = 0; i < dataPacketsInBuffer; i++) {
        cout << left 
                  << setw(6) << buffernNumber
                  << setw(10) << signalTypeToString(static_cast<int>(signalDataArray[i].signalType))
                  << setw(8) << static_cast<int>(signalDataArray[i].xPixel)
                  << setw(8) << static_cast<int>(signalDataArray[i].yPixel)
                  << setw(16) << fixed << setprecision(10) << signalDataArray[i].ToaFinal
                  << setw(10) << fixed << setprecision(3) << signalDataArray[i].TotFinal
                  << setw(10) << static_cast<int>(signalGroupID[i])
                  << endl;
    }
}

/**
 * @brief Prints out all diagnostics for unpacking, sorting, and writingout data from a TPX3 file.
 *
 * This function function takes a HERMES defined structure tpx3FileDianostics
 * and prints out most of the diagnostic info that might be desired in 
 *
 * @param tpxFileInfo a tpx3FileDianostics structure that contains all the diagnostic containers for
 * unpacking and processing tpx3Files.
 * @return nothing
 */
void printOutUnpackingDiagnostics(tpx3FileDiagnostics tpxFileInfo){
    int numberOfUnprocessedPackets = tpxFileInfo.numberOfDataPackets - tpxFileInfo.numberOfBuffers - tpxFileInfo.numberOfTDC1s - tpxFileInfo.numberOfPixelHits - tpxFileInfo.numberOfGTS - tpxFileInfo.numberOfTXP3Controls;
    cout << endl << "=============== Diagnostics ==============" << endl;
    cout << "Total HERMES Time: " << tpxFileInfo.totalHermesTime << " seconds" << endl;
    cout << "Total Unpacking Time: " << tpxFileInfo.totalUnpackingTime << " seconds" << endl;
    cout << "Total Sorting Time: " << tpxFileInfo.totalSortingTime << " seconds" << endl;
    cout << "Total Clustering Time: " << tpxFileInfo.totalClusteringTime << " seconds" << endl;
    cout << "Total Writing Time: " << tpxFileInfo.totalWritingTime << " seconds" << endl;
    cout << "------------------------------------------" << endl;
    cout << "Number of data packets: " << tpxFileInfo.numberOfDataPackets << endl;
    cout << "Number of headers packets: " << tpxFileInfo.numberOfBuffers << endl;
    cout << "Number of TDC packets: " << tpxFileInfo.numberOfTDC1s << endl;
    cout << "Number of Pixels packets: " << tpxFileInfo.numberOfPixelHits << endl;
    cout << "Number of Global Time stamp packets: " << tpxFileInfo.numberOfGTS << endl;
    cout << "Number of TPX3 control packets: " << tpxFileInfo.numberOfTXP3Controls << endl;
    cout << "Number of Unknown processed packets: " << numberOfUnprocessedPackets << endl;
    cout << "==========================================" << endl;
}