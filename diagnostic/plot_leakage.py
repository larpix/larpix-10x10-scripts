#!/usr/bin/env python3

import argparse
from collections import defaultdict

from tqdm import tqdm
import h5py
import matplotlib.pyplot as plt
from matplotlib import colors
from mpl_toolkits.axes_grid1 import make_axes_locatable

import numpy as np
import yaml

def unique_channel_id(channel):
    return ((channel['io_group'].astype(int)*256 + channel['io_channel'].astype(int))*256 \
            + channel['chip_id'].astype(int))*64 + channel['channel_id'].astype(int)

threshold = 128
gain = 4 # mV /ke-
lsb = 3.91

_default_runtime = 10

geometrypath = '/home/brussell/batch2-tiles/bern/geometry/layout-2.4.0.yaml'

with open(geometrypath) as fi:
    geo = yaml.load(fi)
chip_pix = dict([(chip_id, pix) for chip_id,pix in geo['chips']])

def xy_rate(data):
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
    rates = [data[key]['rate'] for key in data if 'rate' in data[key]]

    return x, y, rates

def plot_summary(data_original, data_updated):
    fig,axes = plt.subplots(1,2,
                            sharex=True,
                            num='leakage_rate',
                            figsize=(12,5),
                            tight_layout=True)
    x_original, y_original, rates_original = xy_rate(data_original)
    x_updated, y_updated, rates_updated = xy_rate(data_updated)

    max_rate = max(max(rates_original),max(rates_updated))

    sc0 = axes[0].scatter(x_original,y_original,
                          marker='.',
                          norm=colors.LogNorm(vmax=max_rate),
                          c=rates_original)

    sc1 = axes[1].scatter(x_updated,y_updated,
                          marker='.',
                          norm=colors.LogNorm(vmax=max_rate),
                          c=rates_updated)

    divider = make_axes_locatable(axes[0])
    cax0 = divider.append_axes("right", size="5%", pad=0.05)

    divider = make_axes_locatable(axes[1])
    cax1 = divider.append_axes("right", size="5%", pad=0.05)

    fig.colorbar(sc0, cax=cax0, label='Rate [Hz]')
    fig.colorbar(sc1, cax=cax1, label='Rate [Hz]')

    axes[0].set(xlabel='x [mm]', ylabel='y [mm]', aspect='equal', title='Original')
    axes[1].set(xlabel='x [mm]', aspect='equal', title='Updated')

    fig.suptitle("Leakage rate",fontsize=20)
    fig.savefig("leakage.png")

    return fig, axes

def analyze_data(file, runtime):
    print('opening', file)

    with h5py.File(file,'r') as f:
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
        adc = dataword[id_mask]
        rate_i = len(adc) / runtime

        data[channel] = dict(
            adc = adc,
            rate = rate_i / runtime,
            leakage = (rate_i)*threshold*lsb*(1000/gain)/1000 # e- / ms
        )

    return data

def main(leakage_file,
         leakage_file_updated,
         runtime=_default_runtime):

    data_original = analyze_data(leakage_file, runtime)
    data_updated = analyze_data(leakage_file_updated, runtime)

    plot_summary(data_original, data_updated)

    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--leakage_file',
                        type=str,
                        help='''Leakage HDF5 file''')
    parser.add_argument('--leakage_file_updated',
                        type=str,
                        help='''Leakage HDF5 file with updated bad channel list applied''')
    parser.add_argument('--runtime',
                        default=_default_runtime,
                        type=float,
                        help='''Duration for run (in seconds) (default=%s)''' % _default_runtime)
    args = parser.parse_args()
    c = main(**vars(args))
