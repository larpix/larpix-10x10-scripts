#!/usr/bin/env python3

import os.path
import json
import argparse

import h5py
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.cm as cm

import numpy as np
from scipy.stats import norm
import yaml

threshold = 128
gain = 4 # mV /ke-
lsb = 3.91

_default_rate = 10
_default_runtime = 10
_default_bad_channels = 'bad_channels.json'
_default_report = 'report.md'
#vref = 1.546 V
#vcm = 544 mV

nonrouted_channels = [6,7,8,9,
                      22,23,24,25,
                      38,39,40,
                      54,55,56,57]

norm = colors.Normalize(vmin=0,vmax=100)
norm_log = colors.LogNorm(vmin=1,vmax=1e6)
cmap = cm.viridis
m = cm.ScalarMappable(norm=norm, cmap=cmap)
m_log = cm.ScalarMappable(norm=norm_log, cmap=cmap)
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

def plot_summary(data, filename):
    plot_exists = plt.fignum_exists('summary')
    if plot_exists:
        fig = plt.figure('summary')
        axes = fig.axes
    else:
        fig,axes = plt.subplots(1,2,sharex='row',num='summary',figsize=(12,5))

    fig.subplots_adjust(hspace=0)
    fig.suptitle(filename)

    for ch_id in data.keys():

        pix = chip_pix[int((ch_id//64)%256)][int(ch_id%64)] if (ch_id//64)%256 in chip_pix else None
        if pix:
            data[ch_id]['x'] = geo['pixels'][pix][1]
            data[ch_id]['y'] = geo['pixels'][pix][2]
        else:
            data[ch_id]['x'] = np.nan
            data[ch_id]['y'] = np.nan

    x = np.array([data[key]['x'] for key in data if 'x' in data[key]])
    y = np.array([data[key]['y'] for key in data if 'y' in data[key]])

    c1 = fig.colorbar(axes[1].scatter(x,y,
                                      marker='.',
                                      c=[data[key]['rate'] for key in data if 'rate' in data[key]]),
                       ax=axes[0],fraction=0.046, pad=0.04)
    c2 = fig.colorbar(axes[0].scatter(x,y,
                                      marker='.',
                                      c=[data[key]['leakage'] for key in data if 'leakage' in data[key]],
                                      norm=colors.LogNorm()),
                       ax=axes[1],fraction=0.046, pad=0.04)

    axes[0].set(xlabel='x [mm]')
    axes[1].set(xlabel='x [mm]')
    axes[0].set(ylabel='y [mm]')
    axes[0].set_aspect('equal')
    axes[1].set_aspect('equal')
    c1.set_label(r'Leakage current [e$^-$ / ms]')
    axes[1].set(ylabel='y [mm]')
    c2.set_label('Rate [Hz]')

    plt.tight_layout()
    plt.show()
    plt.savefig("leakage.png")

def main(filename,
         bad_channels_file=_default_bad_channels,
         report_file=_default_report,
         leakage_rate=_default_rate,
         runtime=_default_runtime):

    print('opening',filename)
    plt.ion()
    f = h5py.File(filename,'r')

    f_report = open(report_file, 'a+')
    f_report.write('## Leakage test\n')

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
    high_leakage_channels = {}

    f_report.write("## High leakage channels list\n")
    for channel in sorted(unique_channels):
        channel_mask = unique_channel_id(io_group, io_channel, chip_id, channel_id) == channel
        timestamp = good_data[channel_mask]['timestamp']
        adc = good_data[channel_mask]['dataword']
        rate_i = len(adc) / runtime

        data[channel] = dict(
            channel_mask = channel_mask,
            timestamp = timestamp,
            adc = adc,
            rate = rate_i/runtime,
            leakage = (rate_i)*threshold*lsb*(1000/gain)/1000 # e- / ms
            )

        if rate_i > leakage_rate:
            chip_key = unique_channel_id_2_str(channel)
            chip_key_values = chip_key.split("-")
            chip_key_values = [int(c) for c in chip_key_values]
            just_chip = "%i-%i-%i" % (chip_key_values[0], chip_key_values[1], chip_key_values[2])
            this_channel = chip_key_values[-1]

            if just_chip in high_leakage_channels:
                high_leakage_channels[just_chip].append(this_channel)
            else:
                high_leakage_channels[just_chip] = [this_channel]

            output = '- chip key: {}\tchannel: {}\trate [Hz]: {:.02f}\tleakage: {:.02f} [e-/ms]'.format(just_chip,
                                                                                           chip_key_values[3],
                                                                                           data[channel]['rate'],
                                                                                           data[channel]['leakage'])
            print(output)
            print(output, file=f_report)

    plot_summary(data, filename)
    print(f"\n![Leakage current and rate](leakage.png)", file=f_report)

    if not os.path.isfile(bad_channels_file) or os.path.getsize(bad_channels_file) == 0:
        with open(bad_channels_file, 'w+') as file:
            file.write('{}')

    with open(bad_channels_file,'r+') as file:
        file_data = json.load(file)
        if "All" not in file_data:
            file_data["All"] = nonrouted_channels
        else:
            for channel in nonrouted_channels:
                if channel not in file_data['All']:
                    file_data["All"].append(channel)

        for chip in high_leakage_channels:
            if chip in file_data:
                for channel in high_leakage_channels[chip]:
                    if channel not in file_data[chip]:
                        file_data[chip].append(channel)
            else:
                file_data[chip] = high_leakage_channels[chip]

        file.seek(0)
        json.dump(file_data, file, indent=4)

    return data

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', type=str, help='''Leakage HDF5 file''')
    parser.add_argument('--bad_channels_file',
                        default=_default_bad_channels,
                        type=str,
                        help='''JSON file where to store high-leakage channels to be disabled (default=%s)''' % _default_bad_channels)
    parser.add_argument('--report_file',
                        default=_default_report,
                        type=str,
                        help='''Markdown file where to store the high-leakage channels in a human-readable format (default=%s)''' % _default_report)
    parser.add_argument('--leakage_rate',
                        default=_default_rate,
                        type=int,
                        help='''Leakage rate above which a channel is stored in the bad channels JSON (default=%s)''' % _default_rate)
    parser.add_argument('--runtime',
                        default=_default_runtime,
                        type=float,
                        help='''Duration for run (in seconds) (default=%s)''' % _default_runtime)
    args = parser.parse_args()
    c = main(**vars(args))
