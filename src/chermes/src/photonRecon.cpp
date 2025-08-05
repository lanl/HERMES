#include "structures.h"
#include "photonRecon.h"

#include <iostream>
#include <fstream> 

using namespace std;

// Computes the spatial distance between two signal data points using Euclidean distance formula.
double spatialDistance(const signalData& p1, const signalData& p2) {
    return sqrt((p1.xPixel - p2.xPixel) * (p1.xPixel - p2.xPixel) +
                     (p1.yPixel - p2.yPixel) * (p1.yPixel - p2.yPixel));
}

// Computes the temporal distance between two signal data points.
double temporalDistance(const signalData& p1, const signalData& p2) {
    return abs(p1.ToaFinal - p2.ToaFinal);
}

// Checks if two signal data points are neighbors based on given spatial and temporal thresholds.
bool isNeighbor(const signalData& p1, const signalData& p2, double epsSpatial, double epsTemporal) {
    return spatialDistance(p1, p2) <= epsSpatial && temporalDistance(p1, p2) <= epsTemporal;
}

/**
 * @brief Searches for neighboring signal data points within defined spatial
 * and temporal thresholds.
 *
 * This function identifies neighbors of a specified 'homeIndex' in
 * 'signalDataArray', within a [-queryRegion, +queryRegion] range. It adjusts
 * the search to stay within array bounds, using 'configParams' for spatial
 * (epsSpatial) and temporal (epsTemporal) distance thresholds.
 *
 * @param configParams Configuration parameters including spatial (epsSpatial)
 * and temporal (epsTemporal) thresholds.
 * @param tpx3FileInfo Contains file diagnostics, like total number of data
 * packets (numberOfDataPackets), to keep search indices valid.
 * @param signalDataArray Pointer to the array of signal data points, each
 * includes spatial coordinates, time of arrival, etc.
 * @param homeIndex Index in 'signalDataArray' for which neighbors are searched.
 *
 * @return vector<size_t> Indices of neighboring data points within
 * specified thresholds.
 *
 * Example usage:
 * auto neighbors = regionQuery(config, fileInfo, signalData, 1000);
 * Searches for neighbors of data point at index 1000 in 'signalDataArray',
 * using 'config' defined thresholds.
 */
vector<size_t> regionQuery(configParameters configParams, tpx3FileDiagnostics& tpx3FileInfo, signalData* signalDataArray, const size_t homeIndex) {
    
    // Calculate start and end indices to search within, ensuring they stay within bounds of the array
    size_t startIndex = homeIndex > configParams.queryRegion ? homeIndex - configParams.queryRegion : 0;
    size_t endIndex = homeIndex + configParams.queryRegion < tpx3FileInfo.numberOfDataPackets ? homeIndex + configParams.queryRegion : tpx3FileInfo.numberOfDataPackets - 1;
    
    vector<size_t> neighbors;
    for (size_t i = startIndex; i <= endIndex; i++) {
        if (isNeighbor(signalDataArray[homeIndex], signalDataArray[i], configParams.epsSpatial, configParams.epsTemporal)) {
            neighbors.push_back(i);
        }
    }
    return neighbors;
}


/**
 * @brief Expands a cluster from a seed point by including all density-reachable
 * points within spatial and temporal thresholds.
 *
 * This function evaluates each new point found within the specified spatial and
 * temporal thresholds not already assigned to a cluster or marked as noise. If
 * a point has enough neighbors, it is added to the cluster, and its neighbors
 * are also evaluated, recursively expanding the cluster. The function accumulates
 * photon data statistics for the cluster and returns a photonData structure
 * containing the calculated center of mass and total Time over Threshold (ToT)
 * for the cluster.
 *
 * @param configParams Configuration parameters including the spatial
 * (epsSpatial) and temporal (epsTemporal) thresholds.
 * @param tpx3FileInfo Contains information about the dataset, such as the
 * number of data packets.
 * @param signalDataArray Array of signal data points to be clustered.
 * @param homeIndex Index of the seed point from which to start expanding the
 * cluster.
 * @param neighbors Initial list of neighbors of the seed point that meet the
 * density criteria.
 * @param clusterId The identifier for the current cluster being expanded.
 * @return photonData Structure containing the photon data statistics for the
 * expanded cluster.
 */
photonData expandCluster(configParameters configParams, tpx3FileDiagnostics& tpx3FileInfo, signalData* signalDataArray, size_t homeIndex, vector<size_t>& neighbors, size_t clusterId) {
   
    photonData pd;                                      // Create a photonData instance to be filled and returned
    signalDataArray[homeIndex].groupID = clusterId;     // Mark the seed point as part of the cluster

    // Initialize weighted sums for calculating the center of mass (CoM) of the cluster
    float weightedSumX = signalDataArray[homeIndex].xPixel * signalDataArray[homeIndex].TotFinal;
    float weightedSumY = signalDataArray[homeIndex].yPixel * signalDataArray[homeIndex].TotFinal;
    double weightedSumToA = signalDataArray[homeIndex].ToaFinal * signalDataArray[homeIndex].TotFinal;
    uint16_t totalToT = signalDataArray[homeIndex].TotFinal;
    size_t pixelCount = 1; // Initialize pixel count, starting with the seed point itself


    // Use a queue to iteratively process each neighbor and its neighbors
    size_t index = 0;
    while (index < neighbors.size()) {
        size_t qIndex = neighbors[index];

        // Skip non-Pixel signals
        if (signalDataArray[qIndex].signalType != 2) {
            //TODO Figure out if I need to ++index
            ++index;    // Move to the next neighbor, even if the current one is skipped   
            continue;   // Skip the rest of the iteration in this loop
        }

        // Only process points that haven't been assigned to a cluster or marked as noise
        if (signalDataArray[qIndex].groupID == 0) { 
            signalDataArray[qIndex].groupID = clusterId; // Mark as part of the current cluster
            pixelCount++; // Increment the count of pixels contributing to the photon

            // Find neighbors of this point
            vector<size_t> qNeighbors = regionQuery(configParams, tpx3FileInfo, signalDataArray, qIndex);

            // If this point has enough neighbors, add them to the list for processing
            if (qNeighbors.size() >= configParams.minPts) {
                neighbors.insert(neighbors.end(), qNeighbors.begin(), qNeighbors.end());
            }
        }

        // Update weighted sums for CoM calculations
        weightedSumX += signalDataArray[qIndex].xPixel * signalDataArray[qIndex].TotFinal;
        weightedSumY += signalDataArray[qIndex].yPixel * signalDataArray[qIndex].TotFinal;
        weightedSumToA += signalDataArray[qIndex].ToaFinal * signalDataArray[qIndex].TotFinal;
        totalToT += signalDataArray[qIndex].TotFinal;

        ++index; // Move to the next neighbor
    }

    // Calculate and store the cluster's center of mass and total ToT
    pd.photonX = weightedSumX / totalToT;
    pd.photonY = weightedSumY / totalToT;
    pd.photonToa = weightedSumToA / totalToT;
    pd.integratedTot = totalToT;
    pd.multiplicity = pixelCount;

    return pd;
}



/**
 * @brief Performs the ST_DBSCAN clustering algorithm on a dataset of signal
 * data points.
 *
 * This function segregates Pixel signals (signalType == 2) into clusters based
 * on spatial and temporal closeness according to configuration parameters,
 * marks non-Pixel signals as unprocessed, and identifies noise. Clusters are
 * assigned unique IDs starting from 2, with noise marked as 1, and
 * unprocessed/non-Pixel signals left as 0.
 *
 * @param configParams Configuration parameters for the DBSCAN algorithm,
 * including spatial and temporal thresholds (epsSpatial, epsTemporal) and the
 * minimum number of points (minPts) required to form a cluster.
 * @param tpx3FileInfo File diagnostics information including the total number
 * of data packets (numberOfDataPackets) to be processed.
 * @param signalDataArray Array of signalData structs representing the dataset
 * for clustering.
 *
 * @note The function modifies the `groupID` field of each `signalData` struct
 * in `signalDataArray` to indicate cluster membership, mark as noise, or leave
 * as unprocessed for non-Pixel signals.
 */
void ST_DBSCAN(configParameters configParams, tpx3FileDiagnostics& tpx3FileInfo, signalData* signalDataArray) {
    uint32_t clusterId = 2; // Start cluster IDs from 2, reserving 1 for noise
    vector<photonData> photons; // Vector to store photon data for each cluster.

    // Loop through signalDataArray and begin clustering. 
    for (size_t currentPacketIndex = 0; currentPacketIndex < tpx3FileInfo.numberOfDataPackets; currentPacketIndex++) {
        
        // Skip processing for non-Pixel signals or already processed signals
        // TODO: Figure out if I should be skipping already processed signals. 
        if (signalDataArray[currentPacketIndex].signalType != 2 || signalDataArray[currentPacketIndex].groupID != 0) {
            continue;
        }

        vector<size_t> neighbors = regionQuery(configParams, tpx3FileInfo, signalDataArray, currentPacketIndex);

        if (neighbors.size() < static_cast<size_t>(configParams.minPts)) {
            signalDataArray[currentPacketIndex].groupID = 1; // Mark as noise
        } else {
            clusterId++;
            photonData clusterPhotonData = expandCluster(configParams, tpx3FileInfo, signalDataArray, currentPacketIndex, neighbors, clusterId);
            photons.push_back(clusterPhotonData); // Store the photon data for the cluster
        }
    }
}
