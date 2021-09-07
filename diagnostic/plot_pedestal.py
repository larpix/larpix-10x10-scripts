#!/usr/bin/env python3

import argparse
from collections import defaultdict

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colors
import h5py
import yaml
from tqdm import tqdm
from mpl_toolkits.axes_grid1 import make_axes_locatable

def unique_channel_id(channel):
    return ((channel['io_group'].astype(int)*256 + channel['io_channel'].astype(int))*256 \
            + channel['chip_id'].astype(int))*64 + channel['channel_id'].astype(int)

geometrypath = '/home/brussell/batch2-tiles/bern/geometry/layout-2.4.0.yaml'

with open(geometrypath) as fi:
    geo = yaml.load(fi,Loader=yaml.FullLoader)
chip_pix = dict([(chip_id, pix) for chip_id,pix in geo['chips']])

def analyze_data(filename):

    print("opening", filename)
    with h5py.File(filename,'r') as f:
        data_mask = f['packets']['packet_type'] == 0
        print(len(f['packets'][data_mask]),' data packets')
        data_mask = np.logical_and(f['packets']['valid_parity'], data_mask)
        print(len(f['packets'][data_mask]),' valid parity data packets')
        dataword = f['packets']['dataword'][data_mask]
        unique_id = unique_channel_id(f['packets'][data_mask])

    unique_id_set = np.unique(unique_id)
    data = defaultdict(dict)

    for channel in tqdm(unique_id_set, desc="Analyzing channels..."):

        id_mask = unique_id == channel

        if np.sum(id_mask) < 3:
            continue

        masked_dataword = dataword[id_mask]
        data[channel]['mean'] = np.mean(masked_dataword)
        data[channel]['std'] = np.std(masked_dataword)

    return data

def xy_mean_stds(data):
    for ch_id in data.keys():

        pix = chip_pix[int((ch_id//64)%256)][int(ch_id%64)] if (ch_id//64)%256 in chip_pix else None
        if pix:
            data[ch_id]['x'] = geo['pixels'][pix][1]
            data[ch_id]['y'] = geo['pixels'][pix][2]
        else:
            data[ch_id]['x'] = np.nan
            data[ch_id]['y'] = np.nan

    x = [data[key]['x'] for key in data if 'x' in data[key]]
    y = [data[key]['y'] for key in data if 'y' in data[key]]
    means = [data[key]['mean'] for key in data if 'mean' in data[key]]
    stds = [data[key]['std'] for key in data if 'std' in data[key]]

    return x, y, means, stds

def plot_summary(data_original, data_updated):
    fig,axes = plt.subplots(2,2,sharex=True,num='pedestal',figsize=(11,9),tight_layout=True)
    x_original, y_original, means_original, stds_original = xy_mean_stds(data_original)
    x_updated, y_updated, means_updated, stds_updated = xy_mean_stds(data_updated)

    max_means = max(max(means_original), max(means_updated))
    max_stds = max(max(stds_original), max(stds_updated))

    sc_means = axes[0][0].scatter(x_original,y_original,
                                  marker='.',
                                  norm=colors.LogNorm(vmax=max_means),
                                  c=means_original)

    sc_stds = axes[1][0].scatter(x_original,y_original,
                                 marker='.',
                                 norm=colors.LogNorm(vmax=max_stds),
                                 c=stds_original)

    sc1_means = axes[0][1].scatter(x_updated,y_updated,
                                   marker='.',
                                   norm=colors.LogNorm(vmax=max_means),
                                   c=means_updated)

    sc1_stds = axes[1][1].scatter(x_updated,y_updated,
                                  marker='.',
                                  norm=colors.LogNorm(vmax=max_stds),
                                  c=stds_updated)

    divider = make_axes_locatable(axes[0][0])
    cax00 = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(sc_means, cax=cax00, label='Mean')

    divider = make_axes_locatable(axes[1][0])
    cax10 = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(sc_stds, cax=cax10, label='Standard deviation')

    divider = make_axes_locatable(axes[0][1])
    cax01 = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(sc1_means, cax=cax01, label='Mean')

    divider = make_axes_locatable(axes[1][1])
    cax11 = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(sc1_stds, cax=cax11, label='Standard deviation')

    axes[0][0].set(ylabel='y [mm]', aspect='equal', title='Original')
    axes[1][0].set(xlabel='x [mm]', ylabel='y [mm]', aspect='equal')
    axes[0][1].set(ylabel='y [mm]', aspect='equal', title='Updated')
    axes[1][1].set(xlabel='x [mm]', ylabel='y [mm]', aspect='equal')

    fig.suptitle("Pedestal",fontsize=20)
    fig.savefig("pedestal.png")

    return fig, axes


def main(pedestal_file, pedestal_file_updated):

    data_original = analyze_data(pedestal_file)
    data_updated = analyze_data(pedestal_file_updated)

    plot_summary(data_original, data_updated)

    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pedestal_file',
                        type=str,
                        help='''Pedestal HDF5 file''')
    parser.add_argument('--pedestal_file_updated',
                        type=str,
                        help='''Pedestal HDF5 file with updated bad channel list applied''')
    args = parser.parse_args()
    c = main(**vars(args))
