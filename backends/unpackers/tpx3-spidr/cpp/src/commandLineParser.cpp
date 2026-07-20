/**
 * @file commandLineParser.cpp
 * @brief Implementation of command-line parsing utilities
 */

#include <fstream>
#include <iostream>
#include "commandLineParser.h"
#include "configReader.h"
#include "diagnostics.h"

using namespace std;

/**
 * @brief Creates default configuration parameters
 * @return configParameters struct with default values
 */
configParameters createDefaultConfig() {
    configParameters params;
    // Default values are already set in the struct definition
    // Just ensure some sensible defaults for common use cases
    params.writeRawSignals = true;
    params.sortSignals = true;
    params.outputFolder = ".";
    params.verboseLevel = 1;
    params.clusterPixels = false;
    params.writeOutPhotons = false;
    params.maxPacketsToRead = 0;
    params.epsSpatial = 2;
    params.epsTemporal = 500.0;
    params.minPts = 3;
    params.queryRegion = 0;
    
    return params;
}

/**
 * @brief Check if a file exists
 * @param filepath Path to the file
 * @return true if file exists
 */
bool fileExists(const string& filepath) {
    ifstream file(filepath);
    return file.good();
}

/**
 * @brief Check if a file has a specific extension
 * @param filepath Path to the file
 * @param extension Expected extension (e.g., ".tpx3", ".config")
 * @return true if file has the expected extension
 */
bool hasExtension(const string& filepath, const string& extension) {
    size_t pos = filepath.find_last_of('.');
    if (pos == string::npos) return false;
    
    string fileExt = filepath.substr(pos);
    return fileExt == extension;
}

/**
 * @brief Check if a file exists and has a specific extension
 * @param filepath Path to the file
 * @param extension Expected extension (e.g., ".tpx3", ".config")
 * @return true if file exists and has the expected extension
 */
bool isFileWithExtension(const string& filepath, const string& extension) {
    return fileExists(filepath) && hasExtension(filepath, extension);
}

/**
 * @brief Extract directory path from file path
 * @param filepath Full path to file
 * @return Directory path (empty string if no directory)
 */
string getDirectoryPath(const string& filepath) {
    size_t pos = filepath.find_last_of("/\\");
    if (pos == string::npos) return "";
    return filepath.substr(0, pos);
}

/**
 * @brief Extract filename from file path
 * @param filepath Full path to file
 * @return Filename only
 */
string getFilename(const string& filepath) {
    size_t pos = filepath.find_last_of("/\\");
    if (pos == string::npos) return filepath;
    return filepath.substr(pos + 1);
}

/**
 * @brief Safely parse integer from string
 * @param str String to parse
 * @param defaultValue Default value if parsing fails
 * @return Parsed integer or default value
 */
int parseIntOrDefault(const string& str, int defaultValue) {
    try {
        return stoi(str);
    } catch (const exception&) {
        return defaultValue;
    }
}

/**
 * @brief Parse command-line flags and populate configuration
 * @param argc Number of arguments
 * @param argv Array of arguments
 * @param configParams Configuration parameters to populate
 * @param helpLevel Output parameter for help level (if help requested)
 * @return true if parsing successful, false if help requested or error
 */
bool parseCommandLineFlags(int argc, char* argv[], configParameters& configParams, int& helpLevel) {
    configParams = createDefaultConfig();
    helpLevel = 0;  // 0 = no help, 1 = basic help, 2 = help with examples
    
    string inputFile, inputDir, outputDir, configFile;
    bool sortSignals = false;
    bool sortSpecified = false;
    bool clusterPixels = false;
    bool clusterPixelsSpecified = false;
    bool writeOutPhotons = false;
    bool writeOutPhotonsSpecified = false;
    bool batchModeSpecified = false;
    int verboseLevel = 1;
    uint32_t maxPackets = 0;
    uint8_t epsSpatial = 0;
    double epsTemporal = 0.0;
    uint8_t minPts = 0;
    uint16_t queryRegion = 0;
    
    for (int i = 1; i < argc; i++) {
        string arg = argv[i];
        
        if (arg == "-h" || arg == "--help") {
            // Check if next argument is a number for help level
            if (i + 1 < argc && argv[i + 1][0] != '-') {
                helpLevel = parseIntOrDefault(argv[++i], 1);
                if (helpLevel < 1 || helpLevel > 2) {
                    helpLevel = 1;  // Default to level 1 if invalid
                }
            } else {
                helpLevel = 1;  // Default help level
            }
            return false;  // Help requested
        }
        else if ((arg == "-i" || arg == "--inputFile") && i + 1 < argc) {
            inputFile = argv[++i];
        }
        else if ((arg == "-I" || arg == "--inputDir") && i + 1 < argc) {
            inputDir = argv[++i];
        }
        else if ((arg == "-o" || arg == "--outputDir") && i + 1 < argc) {
            outputDir = argv[++i];
        }
        else if ((arg == "-c" || arg == "--configFile") && i + 1 < argc) {
            configFile = argv[++i];
        }
        else if (arg == "-s" || arg == "--sort") {
            sortSignals = true;
            sortSpecified = true;
        }
        else if ((arg == "-v" || arg == "--verbose") && i + 1 < argc) {
            verboseLevel = parseIntOrDefault(argv[++i], 1);
        }
        else if (arg == "-w" || arg == "--writeRawSignals") {
            configParams.writeRawSignals = true;
            cout << "Write raw signals: enabled" << endl;
        }
        else if (arg == "-C" || arg == "--clusterPixels") {
            clusterPixels = true;
            clusterPixelsSpecified = true;
        }
        else if (arg == "-p" || arg == "--writeOutPhotons") {
            writeOutPhotons = true;
            writeOutPhotonsSpecified = true;
        }
        else if ((arg == "-m" || arg == "--maxPackets") && i + 1 < argc) {
            maxPackets = static_cast<uint32_t>(parseIntOrDefault(argv[++i], 0));
        }
        else if ((arg == "-S" || arg == "--epsSpatial") && i + 1 < argc) {
            epsSpatial = static_cast<uint8_t>(parseIntOrDefault(argv[++i], 0));
        }
        else if ((arg == "-T" || arg == "--epsTemporal") && i + 1 < argc) {
            try {
                epsTemporal = stod(argv[++i]);
            } catch (const exception&) {
                epsTemporal = 0.0;
            }
        }
        else if ((arg == "-P" || arg == "--minPts") && i + 1 < argc) {
            minPts = static_cast<uint8_t>(parseIntOrDefault(argv[++i], 0));
        }
        else if ((arg == "-q" || arg == "--queryRegion") && i + 1 < argc) {
            queryRegion = static_cast<uint16_t>(parseIntOrDefault(argv[++i], 0));
        }
        else {
            cerr << "Error: Unknown option: " << arg << endl;
            return false;
        }
    }
    
    // If config file is specified, read it first
    if (!configFile.empty()) {
        if (!readConfigFile(configFile, configParams)) {
            cerr << "Error: Failed to read configuration file: " << configFile << endl;
            return false;
        }
        cout << "Loaded configuration from: " << configFile << endl;
    }
    
    // Validate required parameters
    if (inputFile.empty() && inputDir.empty() && !batchModeSpecified && configFile.empty()) {
        cerr << "Error: Must specify either -i <input_file>, -I <input_dir>, -b (batch mode), or -c <config_file>" << endl;
        return false;
    }
    
    // Handle conflicts between input options
    if (!inputFile.empty() && !inputDir.empty()) {
        cerr << "Error: Cannot specify both -i and -I options" << endl;
        return false;
    }
    
    if (!inputFile.empty() && batchModeSpecified) {
        cout << "Warning: Both input file (-i) and batch mode (-b) specified. Processing single file only: " << inputFile << endl;
        // Single file mode will be set in the configuration section below
    }
    
    // Check if batch mode is specified without input directory
    if (batchModeSpecified && inputDir.empty() && inputFile.empty()) {
        cerr << "Error: Batch mode (-b) requires an input directory. Use -I <directory> to specify the directory." << endl;
        return false;
    }
    
    // Configure parameters (override config file if specified)
    if (!inputFile.empty()) {
        // Single file mode (takes priority over batch mode)
        if (!fileExists(inputFile)) {
            cerr << "Error: Input file does not exist: " << inputFile << endl;
            return false;
        }
        if (!hasExtension(inputFile, ".tpx3")) {
            cerr << "Error: Input file must have .tpx3 extension: " << inputFile << endl;
            return false;
        }
        configParams.rawTPX3File = getFilename(inputFile);
        configParams.rawTPX3Folder = getDirectoryPath(inputFile);
        configParams.runHandle = grabRunHandle(configParams.rawTPX3File);
        configParams.batchMode = false;
    } else if (!inputDir.empty()) {
        // Directory-based batch mode (works with or without -b flag)
        configParams.rawTPX3Folder = inputDir;
        configParams.rawTPX3File = "ALL";
        configParams.batchMode = true;
    }
    
    // Set output directory (override config if specified)
    if (!outputDir.empty()) {
        configParams.outputFolder = outputDir;
    } else if (configFile.empty()) {
        // Only set default if no config file was used
        configParams.outputFolder = configParams.rawTPX3Folder.empty() ? "." : configParams.rawTPX3Folder;
    }
    
    // Set verbose level (override config if specified)
    if (verboseLevel >= 0 && verboseLevel <= 3) {
        configParams.verboseLevel = verboseLevel;
    } else {
        cout << "Warning: Invalid verbose level " << verboseLevel 
                 << ". Using default: " << configParams.verboseLevel << endl;
    }
    
    // Set sorting option (override config if specified)
    if (sortSpecified) {
        configParams.sortSignals = sortSignals;
        cout << "Signal sorting: " << (sortSignals ? "enabled" : "disabled") << endl;
    }
    
    // Set other boolean options (override config if specified)
    if (clusterPixelsSpecified) {
        configParams.clusterPixels = clusterPixels;
        cout << "Cluster pixels: " << (clusterPixels ? "enabled" : "disabled") << endl;
    }
    
    if (writeOutPhotonsSpecified) {
        configParams.writeOutPhotons = writeOutPhotons;
        cout << "Write out photons: " << (writeOutPhotons ? "enabled" : "disabled") << endl;
    }
    
    // Set numeric parameters (override config if specified)
    if (maxPackets > 0) {
        configParams.maxPacketsToRead = maxPackets;
        cout << "Max packets to read: " << maxPackets << endl;
    }
    
    if (epsSpatial > 0) {
        configParams.epsSpatial = epsSpatial;
        cout << "Epsilon spatial: " << static_cast<int>(epsSpatial) << endl;
    }
    
    if (epsTemporal > 0.0) {
        configParams.epsTemporal = epsTemporal;
        cout << "Epsilon temporal: " << epsTemporal << endl;
    }
    
    if (minPts > 0) {
        configParams.minPts = minPts;
        cout << "Minimum points: " << static_cast<int>(minPts) << endl;
    }
    
    if (queryRegion > 0) {
        configParams.queryRegion = queryRegion;
        cout << "Query region: " << queryRegion << endl;
    }
    
    return true;
}

/**
 * @brief Print usage information with different detail levels
 * @param programName Name of the program
 * @param helpLevel Level of help detail (1=basic, 2=with examples)
 */
void printUsage(const char* programName, int helpLevel) {
    cout << "Input/Output Options:" << endl;
    cout << "  -i, --inputFile <file>     Input TPX3 file" << endl;
    cout << "  -I, --inputDir <dir>       Input directory (for batch mode)" << endl;
    cout << "  -b, --batch                Enable batch mode (requires -I <directory>)" << endl;
    cout << "  -o, --outputDir <dir>      Output directory" << endl;
    cout << "  -c, --configFile <file>    Configuration file" << endl;
    cout << endl;
    cout << "Processing Options:" << endl;
    cout << "  -s, --sort                 Enable signal sorting" << endl;
    cout << "  -w, --writeRawSignals      Enable writing raw signals" << endl;
    cout << "  -C, --clusterPixels        Enable pixel clustering" << endl;
    cout << "  -p, --writeOutPhotons      Enable writing photon data" << endl;
    cout << endl;
    cout << "Clustering Parameters:" << endl;
    cout << "  -S, --epsSpatial <n>       Spatial epsilon for clustering (pixels)" << endl;
    cout << "  -T, --epsTemporal <n>      Temporal epsilon for clustering (seconds)" << endl;
    cout << "  -P, --minPts <n>           Minimum points for clustering" << endl;
    cout << "  -q, --queryRegion <n>      Query region for clustering" << endl;
    cout << endl;
    cout << "Diagnostic Options:" << endl;
    cout << "  -m, --maxPackets <n>       Maximum packets to read (0=all)" << endl;
    cout << "  -v, --verbose <level>      Verbose level (0-3, default: 1)" << endl;
    cout << "  -h, --help                 Show this help message" << endl;
    
    // Only show examples and additional info for helpLevel >= 2
    if (helpLevel >= 2) {
        cout << endl;
        cout << "Examples:" << endl;
        cout << "  # Use config file as-is:" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -c settings.config" << endl;
        cout << endl;
        cout << "  # Direct file processing:" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -i data.tpx3 -o /path/to/output -v 2" << endl;
        cout << endl;
        cout << "  # Config file with overrides:" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -c settings.config -o /different/output -v 3 -W" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -c settings.config --clusterPixels -S 5 -T 100.0" << endl;
        cout << endl;
        cout << "  # Compact clustering setup:" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -i data.tpx3 -o /tmp -C -S 2 -T 250.5 -p -v 2" << endl;
        cout << endl;
        cout << "  # Batch processing with limits:" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -I /path/to/tpx3/files -o /path/to/output -s -m 1000" << endl;
        cout << endl;
        cout << "  # Explicit batch mode with directory:" << endl;
        cout << "  ./bin/tpx3SpidrUnpacker -b -I /path/to/tpx3/files -o /path/to/output -v 2" << endl;
    }
}
