#include "configReader.h"
#include <fstream>
#include <sstream>
#include <iostream>

using namespace std;


// Trim function to remove leading and trailing whitespace
string trim(const string& str) {
    size_t first = str.find_first_not_of(' ');
    if (first == string::npos)
        return ""; // Return an empty string if the string contains only spaces
    size_t last = str.find_last_not_of(' ');
    return str.substr(first, (last - first + 1));
}

string grabRunHandle(const string& str){
    size_t lastDotIndex = str.find_last_of('.');
        return (lastDotIndex != string::npos) ? str.substr(0, lastDotIndex) : str;
}

// Function to convert string to boolean
bool stringToBool(const string& str) {
    if (str == "true") return true;
    if (str == "false") return false;
    throw invalid_argument("Invalid boolean value: " + str);
}

// Template function to handle conversion from string to numeric types with error checking
template<typename T> T stringToNumber(const string& str) {
    T num;
    istringstream iss(str);
    iss >> num;
    if (iss.fail() || !iss.eof()) {
        throw invalid_argument("Invalid numeric value: " + str);
    }
    return num;
}

// Error handling
void logConfigError(const string& key, const string& value, const string& error) {
    cerr << "CONFIG ERROR for key '" << key << "' with value '" << value << "': " << error << endl;
}


/**
 * @brief Reads configuration parameters from a given file and populates a struct with the configuration values.
 * 
 * This function opens a configuration file specified by the filename and reads it line by line. Each line
 * is expected to contain a key-value pair separated by an '=' character. Lines starting with '#' or containing
 * '#' are ignored as comments. The function supports setting various configuration parameters specified
 * by the keys in the file. Invalid or unexpected key-value pairs will generate errors to stderr.
 * 
 * Supported configuration parameters include:
 * - rawTPX3Folder: Folder for raw TPX3 files.
 * - rawTPX3File: Specific raw TPX3 file name (or 'ALL' for batch mode.).
 * - writeRawSignals: Whether to write raw signals (true/false).
 * - outputFolder: Folder for output files.
 * - maxBuffersToRead: Maximum number of buffers to read.
 * - sortSignals: Whether to sort signals (true/false).
 * - verboseLevel: Level of verbosity in output.
 * - clusterPixels: Whether to cluster pixels (true/false).
 * - queryRegion: Region to query (as an integer within uint16_t range).
 * - writeOutPhotons: Whether to write out photons (true/false).
 * - epsSpatial: Epsilon spatial value (as an integer within uint8_t range).
 * - epsTemporal: Epsilon temporal value (as a double).
 * - minPts: Minimum points value (as an integer within uint8_t range).
 * 
 * TODO: refactor this!!!
 * 
 * @param filename The path to the configuration file to be read.
 * @param params Reference to a struct where the configuration parameters will be stored.
 * @return true if the file was successfully read and parsed; false otherwise.
 * 
 * @note The function will print error messages to stderr for any issues encountered while reading the file
 * or parsing the configuration parameters.
 */
bool readConfigFile(const string &filename, configParameters &params) {
    ifstream configFile(filename);
    if (!configFile.is_open()) {
        cerr << "Failed to open configuration file: " << filename << endl;
        return false;
    }
    
    string line;
    while (getline(configFile, line)) {
        if (line.empty() || line[0] == '#' || line.find('#') != string::npos) continue;

        istringstream lineStream(line);
        string key, value;
        getline(lineStream, key, '=');
        getline(lineStream, value);
        key = trim(key);
        value = trim(value);

        try {
            if (key == "rawTPX3Folder") params.rawTPX3Folder = value;
            else if (key == "rawTPX3File") {

                // If the value is empty, blank spaces, "ALL" then analyze all files in the folder in batch mode. 

                if (value.empty() || value == "ALL" || value == "all") {
                    params.rawTPX3File = "ALL";
                    params.runHandle = "";
                } else {
                    params.rawTPX3File = value;
                    params.runHandle = grabRunHandle(value);
                }

            }
            else if (key == "writeRawSignals") params.writeRawSignals = stringToBool(value);
            else if (key == "outputFolder") params.outputFolder = value;
            else if (key == "sortSignals") params.sortSignals = stringToBool(value);
            else if (key == "verboseLevel") params.verboseLevel = stringToNumber<int>(value);
            else if (key == "clusterPixels") params.clusterPixels = stringToBool(value);
            else if (key == "queryRegion") params.queryRegion = static_cast<uint16_t>(stringToNumber<int>(value));
            else if (key == "writeOutPhotons") params.writeOutPhotons = stringToBool(value);
            else if (key == "epsSpatial") params.epsSpatial = static_cast<uint8_t>(stringToNumber<int>(value));
            else if (key == "epsTemporal") params.epsTemporal = stringToNumber<double>(value);
            else if (key == "minPts") params.minPts = static_cast<uint8_t>(stringToNumber<int>(value));
            else if (key == "maxPacketsToRead") params.maxPacketsToRead = stringToNumber<int>(value);
            else cerr << "Unknown configuration key: " << key << endl;
        } catch (const exception& e) {
            logConfigError(key, value, e.what());
        }
    }

    configFile.close();
    return true;
}

void printParameters(const configParameters &params) {
    // If the program reaches this point, the configuration file was successfully read
    cout << "=================== Config parameters ====================" << endl;
    cout << "inputTPX3Folder: " << params.rawTPX3Folder << endl;
    cout << "inputTPX3File: " << params.rawTPX3File << endl;
    cout << "writeRawSignals: " << (params.writeRawSignals ? "true" : "false") << endl;
    cout << "outputFolder: " << params.outputFolder << endl;
    cout << "maxPacketsToRead: " << params.maxPacketsToRead << endl;
    cout << "sortSignals: " << (params.sortSignals ? "true" : "false") << endl;
    cout << "verboseLevel: " << params.verboseLevel << endl;
    cout << "clusterPixels: " << (params.clusterPixels ? "true" : "false") << endl;
    cout << "writeOutPhotons: " << (params.writeOutPhotons ? "true" : "false") << endl;
    cout << "epsSpatial: " << static_cast<int>(params.epsSpatial) << endl;
    cout << "epsTemporal: " << params.epsTemporal << endl;
    cout << "minPts: " << static_cast<int>(params.minPts) << endl;
    cout << "=========================================================" << endl << endl;
}
