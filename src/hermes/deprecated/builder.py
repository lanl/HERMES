from numba import njit
import numpy as np

@njit()
def dbscanTime(data, eps, minSamples):
    """Performs a one dimensional DBSCAN based on one axis (array) and sets group 
        labels in another axis (a different array)

    Args:
        data (signleEventData): array of signleEventData,
        eps (int): epsilon
        minSamples (int): minium number of samples

    Returns:
        _type_: _description_
        
    NOTE: Need to fix issue of updating data. It should be passed another array 
    that it would update. 
    MOST OF THIS WILL BE DONE IN EMPIR!
    """

    clusterLabel = 0
    for i in range(len(data)):
        if data[i]['timeGroup'] != -1:
            continue

        neighbors = findNeighborsTime(data, i, eps, 'ToA_final')

        # if it has no neighbors then mark as
        if len(neighbors) < minSamples:
            data[i]['timeGroup'] = 0  # Mark as noise
        else:
            clusterLabel += 1
            data[i]['timeGroup'] = clusterLabel
            expandClusterTime(data, i, neighbors, clusterLabel, eps, minSamples)

    return len(np.unique(data['timeGroup']))

@njit()
def findNeighborsTime(data, index, eps, dataType):
    neighbors = []
    for i in range(len(data)):
        if abs(data[i][dataType] - data[index][dataType]) <= eps:
            neighbors.append(i)
    return neighbors
    #--------------------------------------------------------------------------

@njit()
def expandClusterTime(data, index, neighbors, clusterLabel, eps, minSamples):
    i = 0
    
    while i < len(neighbors):
        
        neighbor_index = neighbors[i]
        
        if data[neighbor_index]['timeGroup'] == -1:  # Unvisited point
            data[neighbor_index]['timeGroup'] = clusterLabel
            neighbor_neighbors = findNeighborsTime(data, neighbor_index, eps, 'ToA_final')
            
            if len(neighbor_neighbors) >= minSamples:
                neighbors.extend(neighbor_neighbors)
        
        elif data[neighbor_index]['timeGroup'] == 0:  # Noise point
            data[neighbor_index]['timeGroup'] = clusterLabel
        i += 1
    #--------------------------------------------------------------------------

@njit()
def dbscanSpace(data, eps, min_samples):

    cluster_label = 0

    for i in range(len(data)):
        if data[i]['spaceGroup'] != -1:
            continue

        neighbors = findNeighborsSpace(data, i, eps)
        if len(neighbors) < min_samples:
            data[i]['spaceGroup'] = 0  # Mark as noise
        else:
            cluster_label += 1
            data[i]['spaceGroup'] = cluster_label
            expandClusterSpace(data, i, neighbors, cluster_label, eps, min_samples)


@njit()
def findNeighborsSpace(data, index, eps):
    x_i, y_i = data['xpixel'][index], data['ypixel'][index]
    neighbors = []
    for i in range(len(data)):
        x_j, y_j = data['xpixel'][i], data['ypixel'][i]
        if euclideanDistance(x_i, y_i, x_j, y_j) <= eps:
            neighbors.append(i)
    return neighbors


@njit()
def euclideanDistance(x1, y1, x2, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


@njit()
def expandClusterSpace(data, index, neighbors, cluster_label, eps, min_samples):
    i = 0
    while i < len(neighbors):
        neighbor_index = neighbors[i]
        if data[neighbor_index]['spaceGroup'] == -1:  # Unvisited point
            data[neighbor_index]['spaceGroup'] = cluster_label
            neighbor_neighbors = findNeighborsSpace(data, neighbor_index, eps)
            if len(neighbor_neighbors) >= min_samples:
                neighbors.extend(neighbor_neighbors)
        elif data[neighbor_index]['spaceGroup']  == 0:  # Noise point
            data[neighbor_index]['spaceGroup']  = cluster_label
        i += 1
