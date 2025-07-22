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
    params.batchMode = false;
    params.writeRawSignals = true;
    params.sortSignals = true;
    params.outputFolder = ".";
    params.verboseLevel = 1;
    params.fillHistograms = false;
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
bool fileExists(const std::string& filepath) {
    std::ifstream file(filepath);
    return file.good();
}

/**
 * @brief Check if a file has a specific extension
 * @param filepath Path to the file
 * @param extension Expected extension (e.g., ".tpx3", ".config")
 * @return true if file has the expected extension
 */
bool hasExtension(const std::string& filepath, const std::string& extension) {
    size_t pos = filepath.find_last_of('.');
    if (pos == std::string::npos) return false;
    
    std::string fileExt = filepath.substr(pos);
    return fileExt == extension;
}

/**
 * @brief Check if a file exists and has a specific extension
 * @param filepath Path to the file
 * @param extension Expected extension (e.g., ".tpx3", ".config")
 * @return true if file exists and has the expected extension
 */
bool isFileWithExtension(const std::string& filepath, const std::string& extension) {
    return fileExists(filepath) && hasExtension(filepath, extension);
}

/**
 * @brief Extract directory path from file path
 * @param filepath Full path to file
 * @return Directory path (empty string if no directory)
 */
std::string getDirectoryPath(const std::string& filepath) {
    size_t pos = filepath.find_last_of("/\\");
    if (pos == std::string::npos) return "";
    return filepath.substr(0, pos);
}

/**
 * @brief Extract filename from file path
 * @param filepath Full path to file
 * @return Filename only
 */
std::string getFilename(const std::string& filepath) {
    size_t pos = filepath.find_last_of("/\\");
    if (pos == std::string::npos) return filepath;
    return filepath.substr(pos + 1);
}

/**
 * @brief Safely parse integer from string
 * @param str String to parse
 * @param defaultValue Default value if parsing fails
 * @return Parsed integer or default value
 */
int parseIntOrDefault(const std::string& str, int defaultValue) {
    try {
        return std::stoi(str);
    } catch (const std::exception&) {
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
    
    std::string inputFile, inputDir, outputDir, configFile;
    bool sortSignals = false;
    bool sortSpecified = false;
    bool writeRawSignals = true;
    bool writeRawSignalsSpecified = false;
    bool clusterPixels = false;
    bool clusterPixelsSpecified = false;
    bool writeOutPhotons = false;
    bool writeOutPhotonsSpecified = false;
    bool fillHistograms = false;
    bool fillHistogramsSpecified = false;
    int verboseLevel = 1;
    uint32_t maxPackets = 0;
    uint8_t epsSpatial = 0;
    double epsTemporal = 0.0;
    uint8_t minPts = 0;
    uint16_t queryRegion = 0;
    
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        
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
            writeRawSignals = true;
            writeRawSignalsSpecified = true;
        }
        else if (arg == "-W" || arg == "--no-writeRawSignals") {
            writeRawSignals = false;
            writeRawSignalsSpecified = true;
        }
        else if (arg == "-C" || arg == "--clusterPixels") {
            clusterPixels = true;
            clusterPixelsSpecified = true;
        }
        else if (arg == "-p" || arg == "--writeOutPhotons") {
            writeOutPhotons = true;
            writeOutPhotonsSpecified = true;
        }
        else if (arg == "-H" || arg == "--fillHistograms") {
            fillHistograms = true;
            fillHistogramsSpecified = true;
        }
        else if ((arg == "-m" || arg == "--maxPackets") && i + 1 < argc) {
            maxPackets = static_cast<uint32_t>(parseIntOrDefault(argv[++i], 0));
        }
        else if ((arg == "-S" || arg == "--epsSpatial") && i + 1 < argc) {
            epsSpatial = static_cast<uint8_t>(parseIntOrDefault(argv[++i], 0));
        }
        else if ((arg == "-T" || arg == "--epsTemporal") && i + 1 < argc) {
            try {
                epsTemporal = std::stod(argv[++i]);
            } catch (const std::exception&) {
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
            std::cerr << "Error: Unknown option: " << arg << std::endl;
            return false;
        }
    }
    
    // If config file is specified, read it first
    if (!configFile.empty()) {
        if (!readConfigFile(configFile, configParams)) {
            std::cerr << "Error: Failed to read configuration file: " << configFile << std::endl;
            return false;
        }
        std::cout << "Loaded configuration from: " << configFile << std::endl;
    }
    
    // Validate required parameters
    if (inputFile.empty() && inputDir.empty() && configFile.empty()) {
        std::cerr << "Error: Must specify either -i <input_file>, -I <input_dir>, or -c <config_file>" << std::endl;
        return false;
    }
    
    if (!inputFile.empty() && !inputDir.empty()) {
        std::cerr << "Error: Cannot specify both -i and -I options" << std::endl;
        return false;
    }
    
    // Configure parameters (override config file if specified)
    if (!inputFile.empty()) {
        // Single file mode
        if (!fileExists(inputFile)) {
            std::cerr << "Error: Input file does not exist: " << inputFile << std::endl;
            return false;
        }
        if (!hasExtension(inputFile, ".tpx3")) {
            std::cerr << "Error: Input file must have .tpx3 extension: " << inputFile << std::endl;
            return false;
        }
        configParams.rawTPX3File = getFilename(inputFile);
        configParams.rawTPX3Folder = getDirectoryPath(inputFile);
        configParams.runHandle = grabRunHandle(configParams.rawTPX3File);
        configParams.batchMode = false;
    } else if (!inputDir.empty()) {
        // Batch mode
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
        std::cout << "Warning: Invalid verbose level " << verboseLevel 
                 << ". Using default: " << configParams.verboseLevel << std::endl;
    }
    
    // Set sorting option (override config if specified)
    if (sortSpecified) {
        configParams.sortSignals = sortSignals;
        std::cout << "Signal sorting: " << (sortSignals ? "enabled" : "disabled") << std::endl;
    }
    
    // Set other boolean options (override config if specified)
    if (writeRawSignalsSpecified) {
        configParams.writeRawSignals = writeRawSignals;
        std::cout << "Write raw signals: " << (writeRawSignals ? "enabled" : "disabled") << std::endl;
    }
    
    if (clusterPixelsSpecified) {
        configParams.clusterPixels = clusterPixels;
        std::cout << "Cluster pixels: " << (clusterPixels ? "enabled" : "disabled") << std::endl;
    }
    
    if (writeOutPhotonsSpecified) {
        configParams.writeOutPhotons = writeOutPhotons;
        std::cout << "Write out photons: " << (writeOutPhotons ? "enabled" : "disabled") << std::endl;
    }
    
    if (fillHistogramsSpecified) {
        configParams.fillHistograms = fillHistograms;
        std::cout << "Fill histograms: " << (fillHistograms ? "enabled" : "disabled") << std::endl;
    }
    
    // Set numeric parameters (override config if specified)
    if (maxPackets > 0) {
        configParams.maxPacketsToRead = maxPackets;
        std::cout << "Max packets to read: " << maxPackets << std::endl;
    }
    
    if (epsSpatial > 0) {
        configParams.epsSpatial = epsSpatial;
        std::cout << "Epsilon spatial: " << static_cast<int>(epsSpatial) << std::endl;
    }
    
    if (epsTemporal > 0.0) {
        configParams.epsTemporal = epsTemporal;
        std::cout << "Epsilon temporal: " << epsTemporal << std::endl;
    }
    
    if (minPts > 0) {
        configParams.minPts = minPts;
        std::cout << "Minimum points: " << static_cast<int>(minPts) << std::endl;
    }
    
    if (queryRegion > 0) {
        configParams.queryRegion = queryRegion;
        std::cout << "Query region: " << queryRegion << std::endl;
    }
    
    return true;
}

/**
 * @brief Print usage information with different detail levels
 * @param programName Name of the program
 * @param helpLevel Level of help detail (1=basic, 2=with examples)
 */
void printUsage(const char* programName, int helpLevel) {
    std::cout << "Input/Output Options:" << std::endl;
    std::cout << "  -i, --inputFile <file>     Input TPX3 file" << std::endl;
    std::cout << "  -I, --inputDir <dir>       Input directory (for batch mode)" << std::endl;
    std::cout << "  -o, --outputDir <dir>      Output directory" << std::endl;
    std::cout << "  -c, --configFile <file>    Configuration file" << std::endl;
    std::cout << std::endl;
    std::cout << "Processing Options:" << std::endl;
    std::cout << "  -s, --sort                 Enable signal sorting" << std::endl;
    std::cout << "  -w, --writeRawSignals      Enable writing raw signals" << std::endl;
    std::cout << "  -W, --no-writeRawSignals   Disable writing raw signals" << std::endl;
    std::cout << "  -C, --clusterPixels        Enable pixel clustering" << std::endl;
    std::cout << "  -p, --writeOutPhotons      Enable writing photon data" << std::endl;
    std::cout << "  -H, --fillHistograms       Enable histogram filling" << std::endl;
    std::cout << std::endl;
    std::cout << "Clustering Parameters:" << std::endl;
    std::cout << "  -S, --epsSpatial <n>       Spatial epsilon for clustering (pixels)" << std::endl;
    std::cout << "  -T, --epsTemporal <n>      Temporal epsilon for clustering (seconds)" << std::endl;
    std::cout << "  -P, --minPts <n>           Minimum points for clustering" << std::endl;
    std::cout << "  -q, --queryRegion <n>      Query region for clustering" << std::endl;
    std::cout << std::endl;
    std::cout << "Diagnostic Options:" << std::endl;
    std::cout << "  -m, --maxPackets <n>       Maximum packets to read (0=all)" << std::endl;
    std::cout << "  -v, --verbose <level>      Verbose level (0-3, default: 1)" << std::endl;
    std::cout << "  -h, --help                 Show this help message" << std::endl;
    
    // Only show examples and additional info for helpLevel >= 2
    if (helpLevel >= 2) {
        std::cout << std::endl;
        std::cout << "Examples:" << std::endl;
        std::cout << "  # Use config file as-is:" << std::endl;
        std::cout << "  ./bin/tpx3SpidrUnpacker -c settings.config" << std::endl;
        std::cout << std::endl;
        std::cout << "  # Direct file processing:" << std::endl;
        std::cout << "  ./bin/tpx3SpidrUnpacker -i data.tpx3 -o /path/to/output -v 2" << std::endl;
        std::cout << std::endl;
        std::cout << "  # Config file with overrides:" << std::endl;
        std::cout << "  ./bin/tpx3SpidrUnpacker -c settings.config -o /different/output -v 3 -W" << std::endl;
        std::cout << "  ./bin/tpx3SpidrUnpacker -c settings.config --clusterPixels -S 5 -T 100.0" << std::endl;
        std::cout << std::endl;
        std::cout << "  # Compact clustering setup:" << std::endl;
        std::cout << "  ./bin/tpx3SpidrUnpacker -i data.tpx3 -o /tmp -C -S 2 -T 250.5 -p -v 2" << std::endl;
        std::cout << std::endl;
        std::cout << "  # Batch processing with limits:" << std::endl;
        std::cout << "  ./bin/tpx3SpidrUnpacker -I /path/to/tpx3/files -o /path/to/output -s -H -m 1000" << std::endl;
    }
}
