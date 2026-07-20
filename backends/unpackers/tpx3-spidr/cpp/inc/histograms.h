// histograms.h

#ifndef HISTOGRAM_H
#define HISTOGRAM_H

#include <TH1F.h>
#include <TH2C.h>
#include "structures.h"

// Declaration of histograms
extern TH1F *pixelToA_1D;
extern TH1F *tdcToA_1D;
extern TH1F *gtsToA_1D;
extern TH2C *pixelHits_2D;

// Function prototypes
void fillRawTDCHistogram(signalData &data);
void fillRawPixelHistogram(signalData &data);
void fillRawGTSHistogram(signalData &data);
void fillRawHistograms(int dataPacketsInBuffer, signalData* signalDataArray);
void writeHistograms();

#endif
