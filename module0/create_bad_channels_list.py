import larpix
import larpix.io
import larpix.logger

import time
import sys
import h5py
import argparse
import numpy as np
import json

_default_pedestal_file=None
_default_baseline_cut=200.
_default_noise_cut=10.
_default_verbose=False
_default_tile_number=999

nonrouted_channels=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57]

def unique_channel_id(io_group, io_channel, chip_id, channel_id):
    return channel_id + 100*(chip_id + 1000*(io_channel + 1000*(io_group)))

def from_unique_to_channel_id(unique):
    return int(unique) % 100

def from_unique_to_chip_key(unique):
    io_group = (unique // (100*1000*1000)) % 1000
    io_channel = (unique // (100*1000)) % 1000
    chip_id = (unique // 100) % 1000
    return larpix.Key(io_group, io_channel, chip_id)

def chip_key_string(chip_key):
    return '-'.join([str(int(chip_key.io_group)),str(int(chip_key.io_channel)),str(int(chip_key.chip_id))])

def evaluate_pedestal(pedestal_file, baseline_cut, noise_cut, verbose):
    bad_record = {}
    
    count_noisy = 0
    f = h5py.File(pedestal_file,'r')
    data_mask = f['packets'][:]['packet_type']==0
    valid_parity_mask = f['packets'][data_mask]['valid_parity']==1
    good_data = (f['packets'][data_mask])[valid_parity_mask]
    io_group = good_data['io_group'].astype(np.uint64)
    io_channel = good_data['io_channel'].astype(np.uint64)
    chip_id = good_data['chip_id'].astype(np.uint64)
    channel_id = good_data['channel_id'].astype(np.uint64)
    unique_channels = set(unique_channel_id(io_group, io_channel, chip_id, channel_id))

    for unique in sorted(unique_channels):
        channel_mask = unique_channel_id(io_group, io_channel, chip_id, channel_id) == unique

        chip_key = from_unique_to_chip_key(unique)

        if from_unique_to_channel_id(unique) in nonrouted_channels: continue

        adc = good_data[channel_mask]['dataword']
        if np.mean(adc)>baseline_cut or np.std(adc)>noise_cut:
            if verbose: print(from_unique_to_chip_key(unique),' disabling chann\
el',from_unique_to_channel_id(unique),
                              ' with %.2f pedestal ADC RMS'%np.std(adc))
            if chip_key not in bad_record: bad_record[chip_key_string(chip_key)] = []
            bad_record[chip_key_string(chip_key)].append(from_unique_to_channel_id(unique))
            count_noisy += 1
            continue
    print(count_noisy,' channels identified to disable')
    return bad_record

def save_record(record, tile_number):
    time_format = time.strftime('%Y_%m_%d_%H_%S_%Z')
    with open('tile'+str(tile_number)+'-bad-channels-'+time_format+'.json', 'w') as outfile:
        json.dump(record, outfile, indent=4)

def main(pedestal_file=_default_pedestal_file,
         baseline_cut=_default_baseline_cut,
         noise_cut=_default_noise_cut,
         tile_number=_default_tile_number,
      	 verbose=_default_verbose,
         **kwargs):

    bad = evaluate_pedestal(pedestal_file, baseline_cut, noise_cut, verbose)
    bad["All"] = nonrouted_channels

    save_record(bad,tile_number)    
    return

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pedestal_file',
                        default=_default_pedestal_file,
                        type=str,
                        help='''Path to pedestal file''')
    parser.add_argument('--baseline_cut',
                        default=_default_baseline_cut,
                        type=float,
                        help='''Cut pedestal mean if equal or exceed this value''')
    parser.add_argument('--noise_cut',
                        default=_default_noise_cut,
                        type=float,
                        help='''Cut pedestal RMS if equal or exceed this value''')
    parser.add_argument('--tile_number',
                        default=_default_tile_number,
                        type=int,
                        help='''Tile number to save to output file''')
    parser.add_argument('--verbose',
                        default=_default_verbose,
                        action='store_true',
                        help='''Print to screen debugging output''')
    args = parser.parse_args()
    c = main(**vars(args))
