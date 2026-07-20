// photonRecon.h

#ifndef PHOTONRECON_H
#define PHOTONRECON_H

#include <stdint.h>
#include <cstddef>
#include <vector>
#include <unordered_map>
#include <cstddef>
#include <cmath>

// User defined libraries
#include "structures.h"


double spatialDistance(const signalData& p1, const signalData& p2);
double temporalDistance(const signalData& p1, const signalData& p2);
bool isNeighbor(const signalData& p1, const signalData& p2, double epsSpatial, double epsTemporal); 
std::vector<size_t> regionQuery(configParameters configParams, tpx3FileDiagnostics& tpx3FileInfo, signalData* signalDataArray, const size_t homeIndex);
photonData expandCluster(configParameters configParams,tpx3FileDiagnostics& tpx3FileInfo, signalData* signalDataArray, size_t pIndex, std::vector<size_t>& neighbors, int clusterId, size_t dataPacketsInBuffer);
void ST_DBSCAN(configParameters configParams, tpx3FileDiagnostics& tpx3FileInfo, signalData* signalDataArray);


#endif // PHOTONRECON_H