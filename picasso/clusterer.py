"""
	picasso.clusterer
	~~~~~~~~~~~~~~~~~

	Clusterer optimized for DNA PAINT in CPU and GPU versions.

	Based on the work of Susanne Reinhardt.
"""

import os as _os

import numpy as _np
import math as _math
import yaml as _yaml
from scipy.spatial import distance_matrix as _dm
from numba import njit as _njit
from numba import cuda as _cuda
from tqdm import tqdm as _tqdm

from icecream import ic

#todo: 3D for all cases!
#todo: docstrings

@_njit 
def count_neighbors_picked(dist, radius):
	nn = _np.zeros(dist.shape[0], dtype=_np.int32)
	for i in range(len(nn)):
		nn[i] = _np.where(dist[i] <= radius)[0].shape[0] - 1
	return nn

@_njit
def local_maxima_picked(dist, nn, radius):
	"""
	Finds the positions of the local maxima which are the locs 
	with the highest number of neighbors within given distance dist
	"""
	n = dist.shape[0]
	lm = _np.zeros(n, dtype=_np.int32)
	for i in range(n):
		for j in range(n):
			if dist[i][j] <= radius and nn[i] >= nn[j]:
				lm[i] = 1
			if dist[i][j] <= radius and nn[i] < nn[j]:
				lm[i] = 0
				break
	return lm

@_njit
def assign_to_cluster_picked(dist, radius, lm):
	n = dist.shape[0]
	cluster_id = _np.zeros(n, dtype=_np.int32)
	for i in range(n):
		if lm[i]:
			for j in range(n):
				if dist[i][j] <= radius:
					if cluster_id[i] != 0:
						if cluster_id[j] == 0:
							cluster_id[j] = cluster_id[i]
					if cluster_id[i] == 0:
						if j == 0:
							cluster_id[i] = i + 1
						cluster_id[j] = i + 1
	return cluster_id

@_njit
def check_cluster_size(cluster_n_locs, min_locs, cluster_id):
	for i in range(len(cluster_id)):
		if cluster_n_locs[cluster_id[i]] <= min_locs:
			cluster_id[i] = 0
	return cluster_id

@_njit
def rename_clusters(cluster_id, clusters):
	for i in range(len(cluster_id)):
		for j in range(len(clusters)):
			if cluster_id[i] == clusters[j]:
				cluster_id[i] = j
	return cluster_id

@_njit 
def cluster_properties(cluster_id, n_clusters, frame):
	mean_frame = _np.zeros(n_clusters, dtype=_np.float32)
	n_locs_cluster = _np.zeros(n_clusters, dtype=_np.int32)
	locs_in_window = _np.zeros((n_clusters, 21), dtype=_np.int32)
	locs_frac = _np.zeros(n_clusters, dtype=_np.float32)
	window_search = frame[-1] / 20
	for j in range(n_clusters):
		for i in range(len(cluster_id)):
			if j == cluster_id[i]:
				n_locs_cluster[j] += 1
				mean_frame[j] += frame[i]
				locs_in_window[j][int(frame[i] / window_search)] += 1
	mean_frame = mean_frame / n_locs_cluster
	for i in range(n_clusters):
		for j in range(21):
			temp = locs_in_window[i][j] / n_locs_cluster[i]
			if temp > locs_frac[i]:
				locs_frac[i] = temp
	return mean_frame, locs_frac

@_njit
def find_true_clusters(mean_frame, locs_frac, frame):
	n_frame = _np.int32(_np.max(frame))
	true_cluster = _np.zeros(len(mean_frame), dtype=_np.int8)
	for i in range(len(mean_frame)):
		cond1 = locs_frac[i] < 0.8
		cond2 = mean_frame[i] < n_frame * 0.8
		cond3 = mean_frame[i] > n_frame * 0.2
		if cond1 and cond2 and cond3:
			true_cluster[i] = 1
	return true_cluster

def clusterer_picked(x, y, frame, radius, min_locs):
	xy = _np.stack((x, y)).T
	dist = _dm(xy, xy)
	n_neighbors = count_neighbors_picked(dist, radius)
	local_max = local_maxima_picked(dist, n_neighbors, radius)
	cluster_id = assign_to_cluster_picked(dist, radius, local_max)
	cluster_n_locs = _np.bincount(cluster_id)
	cluster_id = check_cluster_size(
		cluster_n_locs, min_locs, cluster_id
	)
	clusters = _np.unique(cluster_id)
	cluster_id = rename_clusters(cluster_id, clusters)
	n_clusters = len(clusters)
	mean_frame, locs_frac = cluster_properties(
		cluster_id, n_clusters, frame
	)
	true_cluster = find_true_clusters(mean_frame, locs_frac, frame)
	labels = -1 * _np.ones(len(x), dtype=_np.int32)
	for i in range(len(x)):
		if cluster_id[i] != 0 and true_cluster[cluster_id[i]] == 1:
			labels[i] = cluster_id[i] - 1
	return labels

#_____________________________________________________________________#

def get_distance(x1, x2, y1, y2):
	return _np.sqrt((x2-x1)**2 + (y2-y1)**2)

def assing_locs_to_boxes(x, y, box_size):

	# assigns each loc to a box
	box_id = _np.zeros(len(x), dtype=_np.int32)
	
	x_start = x.min()
	x_end = x.max()
	y_start = y.min()
	y_end = y.max()

	n_boxes_x = int((x_end - x_start) / box_size) + 1
	n_boxes_y = int((y_end - y_start) / box_size) + 1
	n_boxes = n_boxes_x * n_boxes_y

	for i in range(len(x)):
		box_id[i] = (
			int((x[i] - x_start) / box_size)
			+ int((y[i] - y_start) / box_size)
			* n_boxes_x
		)

	# gives indeces of locs in a given box
	locs_id_box = [[]]
	for i in range(n_boxes):
		locs_id_box.append([])

	# fill values for locs_id_box
	# also add locs that are in the adjacent boxes
	for i in range(len(x)):
		locs_id_box[box_id[i]].append(i)

		if box_id[i] != n_boxes:
			locs_id_box[box_id[i]+1].append(i)
		if box_id[i] != 0:
			locs_id_box[box_id[i]-1].append(i)

		if box_id[i] > n_boxes_x:
			locs_id_box[box_id[i]-n_boxes_x].append(i)
			locs_id_box[box_id[i]-n_boxes_x+1].append(i)
			locs_id_box[box_id[i]-n_boxes_x-1].append(i)

		if box_id[i] < n_boxes - n_boxes_x:
			locs_id_box[box_id[i]+n_boxes_x].append(i)
			locs_id_box[box_id[i]+n_boxes_x+1].append(i)
			locs_id_box[box_id[i]+n_boxes_x-1].append(i)	

	return locs_id_box, box_id	

def count_neighbors_CPU(locs_id_box, box_id, x, y, radius):
	nn = _np.zeros(len(x), dtype=_np.int32) # number of neighbors
	for i in range(len(x)):
		for j in locs_id_box[box_id[i]]:
			dist = get_distance(x[i], x[j], y[i], y[j])
			if dist <= radius:
				nn[i] += 1
		nn[i] -= 1 # subtract case i == j
	return nn

def local_maxima_CPU(locs_id_box, box_id, nn, x, y, radius):
	lm = _np.zeros(len(x))
	for i in range(len(x)):
		for j in locs_id_box[box_id[i]]:
			dist = get_distance(x[i], x[j], y[i], y[j])
			if dist <= radius and nn[i] >= nn[j]:
				lm[i] = 1
			if dist <= radius and nn[i] < nn[j]:
				lm[i] = 0
				break
	return lm

def assign_to_cluster_CPU(locs_id_box, box_id, nn, lm, x, y, radius):
	cluster_id = _np.zeros(len(x), dtype=_np.int32)
	for i in range(len(x)):
		if lm[i]:
			for j in locs_id_box[box_id[i]]:
				dist = get_distance(x[i], x[j], y[i], y[j])
				if dist <= radius:
					if cluster_id[i] != 0:
						if cluster_id[j] == 0:
							cluster_id[j] = cluster_id[i]
					else:
						if j == 0:
							cluster_id[i] = i + 1
						cluster_id[j] = i + 1
	return cluster_id

def clusterer_CPU(x, y, frame, radius, min_locs):
	"""
	almost the same as clusterer picked, except locs are allocated
	to boxes and neighbors counting is slightly different.
	"""
	xy = _np.stack((x, y)).T
	locs_id_box, box_id = assing_locs_to_boxes(x, y, radius*1.05) # todo: check if 1.05 changes results
	n_neighbors = count_neighbors_CPU(locs_id_box, box_id, x, y, radius)
	local_max = local_maxima_CPU(locs_id_box, box_id, n_neighbors, x, y, radius)
	cluster_id = assign_to_cluster_CPU(
		locs_id_box, box_id, n_neighbors, local_max, x, y, radius
	)
	cluster_n_locs = _np.bincount(cluster_id)
	cluster_id = check_cluster_size(
		cluster_n_locs, min_locs, cluster_id
	)
	clusters = _np.unique(cluster_id)
	cluster_id = rename_clusters(cluster_id, clusters)
	n_clusters = len(clusters)
	mean_frame, locs_frac = cluster_properties(
		cluster_id, n_clusters, frame
	)
	true_cluster = find_true_clusters(mean_frame, locs_frac, frame)
	labels = -1 * _np.ones(len(x), dtype=_np.int32)
	for i in range(len(x)):
		if cluster_id[i] != 0 and true_cluster[cluster_id[i]] == 1:
			labels[i] = cluster_id[i] - 1
	return labels

#_____________________________________________________________________#

@_cuda.jit
def count_neighbors_GPU(nn, r2, x, y):
	i = _cuda.grid(1)
	if i >= len(x):
		return

	temp_sum = 0
	for j in range(len(x)):
		d2 = (x[i]-x[j])**2 + (y[i]-y[j])**2
		if d2 <= r2:
			temp_sum += 1

	nn[i] = temp_sum - 1 # subtract case i == j

@_cuda.jit
def local_maxima_GPU(lm, nn, r2, x, y):
	i = _cuda.grid(1)
	if i >= len(x):
		return

	for j in range(len(x)):
		d2 = (x[i]-x[j])**2 + (y[i]-y[j])**2
		if d2 <= r2 and nn[i] >= nn[j]:
			lm[i] = 1
		if d2 <= r2 and nn[i] < nn[j]:
			lm[i] = 0
			break

@_cuda.jit
def assign_to_cluster_GPU(i, r2, cluster_id, x, y):
	j = _cuda.grid(1)
	if j >= len(x):
		return

	d2 = (x[i]-x[j])**2 + (y[i]-y[j])**2
	if d2 <= r2:
		if cluster_id[i] != 0:
			if cluster_id[j] == 0:
				cluster_id[j] = cluster_id[i]
		if cluster_id[i] == 0:
			if j == 0:
				cluster_id[i] = i + 1
			cluster_id[j] = i + 1

@_cuda.jit
def rename_clusters_GPU(cluster_id, clusters):
	i = _cuda.grid(1)
	if i >= len(cluster_id):
		return

	for j in range(len(clusters)):
		if cluster_id[i] == clusters[j]:
			cluster_id[i] = j

@_cuda.jit
def cluster_properties_GPU1(
	cluster_id,
	n_clusters,
	frame,
	locs_in_window,
	n_locs_cluster,
	mean_frame,
):
	window_search = frame[-1] / 20
	j = _cuda.grid(1)
	if j >= n_clusters:
		return

	for i in range(len(cluster_id)):
		if cluster_id[i] == j:
			n_locs_cluster[j] += 1
			mean_frame[j] += frame[i]
			locs_in_window[j][int(frame[i]/window_search)] += 1

	mean_frame[j] /= n_locs_cluster[j]

@_cuda.jit
def cluster_properties_GPU2(
	locs_in_window,
	n_locs_cluster,
	locs_frac,
):
	i = _cuda.grid(1)
	if i >= len(locs_in_window):
		return

	for j in range(21):
		temp = locs_in_window[i][j] / n_locs_cluster[i]
		if temp > locs_frac[i]:
			locs_frac[i] = temp

def clusterer_GPU(x, y, frame, radius, min_locs):
	# cuda does not accept noncontiguous arrays
	x = _np.ascontiguousarray(x, dtype=_np.float32)
	y = _np.ascontiguousarray(y, dtype=_np.float32)
	frame = _np.ascontiguousarray(frame, dtype=_np.float32)
	r2 = radius ** 2

	block = 32
	grid_x = len(x) // block + 1

	### number of neighbors
	# move arrays to device
	d_x = _cuda.to_device(x)
	d_y = _cuda.to_device(y)
	d_n_neighbors = _cuda.to_device(_np.zeros(len(x), dtype=_np.int32))
	count_neighbors_GPU[grid_x, block](
		d_n_neighbors, r2, d_x, d_y
	)
	_cuda.synchronize()

	### local maxima
	d_local_max = _cuda.to_device(_np.zeros(len(x), dtype=_np.int32))
	local_maxima_GPU[grid_x, block](
		d_local_max, d_n_neighbors, r2, d_x, d_y
	)
	_cuda.synchronize()
	local_max = d_local_max.copy_to_host()

	### assign clusters
	d_cluster_id = _cuda.to_device(_np.zeros(len(x), dtype=_np.int32))
	for i in range(len(x)):
		if local_max[i]:
			assign_to_cluster_GPU[grid_x, block](
				i, r2, d_cluster_id, d_x, d_y
			)
			_cuda.synchronize()

	### check cluster size
	cluster_id = d_cluster_id.copy_to_host()
	cluster_n_locs = _np.bincount(cluster_id)
	cluster_id = check_cluster_size(cluster_n_locs, min_locs, cluster_id)

	### renaming cluster ids
	d_cluster_id = _cuda.to_device(cluster_id)
	clusters = _np.unique(cluster_id)
	d_clusters = _cuda.to_device(clusters)
	rename_clusters_GPU[grid_x, block](
		d_cluster_id, d_clusters
	)
	_cuda.synchronize()

	### cluster props 1
	n = len(clusters)
	d_frame = _cuda.to_device(frame)
	d_n_locs_cluster = _cuda.to_device(_np.zeros(n, dtype=_np.int32))
	d_mean_frame = _cuda.to_device(_np.zeros(n, dtype=_np.float32))
	window_search = frame[-1] / 20
	d_locs_in_window = _cuda.to_device(
		_np.zeros((n, 21), dtype=_np.float32)
	)
	grid_n = len(clusters) // block + 1
	cluster_properties_GPU1[grid_n, block](
		d_cluster_id,
		n,
		d_frame,
		d_locs_in_window,
		d_n_locs_cluster,
		d_mean_frame,
	)
	_cuda.synchronize()

	### check cluster props 2
	d_locs_frac = _cuda.to_device(_np.zeros(n, dtype=_np.float32))
	cluster_properties_GPU2[grid_n, block](
		d_locs_in_window, 
		d_n_locs_cluster,
		d_locs_frac,
	)
	_cuda.synchronize()

	### check for true clusters
	mean_frame = d_mean_frame.copy_to_host()
	locs_frac = d_locs_frac.copy_to_host()
	true_cluster = find_true_clusters(mean_frame, locs_frac, frame)

	### return labels
	cluster_id = d_cluster_id.copy_to_host()
	labels = -1 * _np.ones(len(x), dtype=_np.int32)
	for i in range(len(x)):
		if cluster_id[i] != 0 and true_cluster[cluster_id[i]] == 1:
			labels[i] = cluster_id[i] - 1
	return labels