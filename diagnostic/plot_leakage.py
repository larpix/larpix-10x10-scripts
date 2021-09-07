#!/usr/bin/env python3

import argparse
from tqdm import tqdm
import h5py
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.cm as cm
from mpl_toolkits.axes_grid1 import make_axes_locatable

import numpy as np
import yaml

threshold = 128
gain = 4 # mV /ke-
lsb = 3.91

_default_runtime = 10

geometrypath = '/home/brussell/batch2-tiles/bern/geometry/layout-2.4.0.yaml'

with open(geometrypath) as fi:
    geo = yaml.load(fi)
chip_pix = dict([(chip_id, pix) for chip_id,pix in geo['chips']])

def unique_channel_id(io_group, io_channel, chip_id, channel_id):
    return channel_id + 64*(chip_id + 256*(io_channel + 256*(io_group)))

def unique_channel_id_2_str(unique_id):
    return (unique_id//(256*256*64)).astype(int).astype(str) \
        + '-' + ((unique_id//(256*64))%256).astype(int).astype(str) \
        + '-' + ((unique_id//64)%256).astype(int).astype(str) \
        + '-' + (unique_id%64).astype(int).astype(str)

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
                            constrained_layout=True)
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

    fig.suptitle("Leakage rate")
    fig.savefig("leakage.png")

    return fig, axes

def analyze_data(file, runtime):
    print('opening', file)

    with h5py.File(file,'r') as f:
        data_mask = f['packets'][:]['packet_type'] == 0
        data = f['packets'][data_mask]['packet_type']
        valid_parity_mask = f['packets'][data_mask]['valid_parity'] == 1
        good_data = (f['packets'][data_mask])[valid_parity_mask]

    print(len(data),' data packets')
    print(len(good_data),' valid parity data packets')

    io_group = good_data['io_group'].astype(np.uint64)
    io_channel = good_data['io_channel'].astype(np.uint64)
    chip_id = good_data['chip_id'].astype(np.uint64)
    channel_id = good_data['channel_id'].astype(np.uint64)
    unique_channels = set(unique_channel_id(io_group, io_channel, chip_id, channel_id))

    data = dict()

    for channel in tqdm(sorted(unique_channels), desc="Analyzing channels..."):
        channel_mask = unique_channel_id(io_group, io_channel, chip_id, channel_id) == channel
        timestamp = good_data[channel_mask]['timestamp']
        adc = good_data[channel_mask]['dataword']
        rate_i = len(adc) / runtime

        data[channel] = dict(
            timestamp = timestamp,
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