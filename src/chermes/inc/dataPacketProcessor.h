// dataPacketProcessor.h
#include <stdio.h>
#include <iostream>
#include <fstream>
#include <iomanip>
#include <vector>
#include <cstring>
#include <stdint.h>
#include <chrono>
#include <filesystem> // For std::filesystem::file_size

#ifndef DATAPACKETPROCESSOR_H
#define DATAPACKETPROCESSOR_H

#include "structures.h"
#include "photonRecon.h"

std::vector<std::string> getFilesInDirectory(configParameters configParams);
void resetGlobalVariables();
std::ifstream openTPX3File(const std::string& path, tpx3FileDiagnostics& tpx3FileInfo);
std::ofstream openRawSignalsOutputFile(const configParameters& configParams);
void processDataPackets(const configParameters& configParams, tpx3FileDiagnostics& tpx3FileInfo, const uint64_t* packets, signalData* signalDataArray);
void sortSignals(const configParameters& configParams, signalData* signalDataArray, size_t numberOfDataPackets);
void writeRawSignals(const configParameters& configParams, std::ofstream& rawSignalsFile, const signalData* signalDataArray, tpx3FileDiagnostics& tpx3FileInfo);
void clusterSignals(const configParameters& configParams, signalData* signalDataArray, tpx3FileDiagnostics& tpx3FileInfo);

// Processes a TDC packet and updates the provided signalData structure.
void processTDCPacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData);

// Processes a Pixel packet and updates the provided signalData structure.
void processPixelPacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData);

// Processes a Global Time packet and updates the provided signalData structure.
void processGlobalTimePacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData);

void processSPIDRControlPacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData);
void processTPX3ControlPacket(uint16_t bufferNumber, unsigned long long dataPacket, signalData &signalData);

// Unpack and process entire TPX3File
void processTPX3Files(configParameters configParams);
tpx3FileDiagnostics unpackAndSortTPX3File(configParameters configParams);

// Unpack and process TPX3Files buffer by buffer
//tpx3FileDiagnostics unpackandSortTPX3FileInSequentialBuffers(configParameters configParams);

#endif

