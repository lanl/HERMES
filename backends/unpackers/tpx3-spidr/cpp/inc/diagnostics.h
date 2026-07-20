// diagnostics.h

#ifndef DIAGNOSTICS_H
#define DIAGNOSTICS_H

// libraries
#include <stdint.h>
#include <cstddef>
#include <stdio.h>
#include <iostream>

// User defined libraries
#include "structures.h"

// Declarations of variables
extern int numberOfHeaders;
extern int numberOfBuffers;
extern int numberOfTDCPackets;
extern int numberOfPixelPackets;
extern int numberOfGlobalTSPackets;
extern int numberOfPhotons;

// Function prototypes
void printGroupIDs(int numberOfBuffers, signalData* signalDataArray, int16_t* signalGroupID,size_t dataPacketsInBuffer);
void printOutUnpackingDiagnostics(tpx3FileDiagnostics tpxFileInfo);

#endif