import larpix
import larpix.io
import larpix.logger

import base___no_enforce

import argparse
import json
from datetime import datetime
import h5py
import numpy as np
from collections import Counter
import time

from base___no_enforce import power_registers

_default_controller_config=None
_default_chip_key=None
_default_runtime=0.5
_default_disabled_list=None
_default_threshold=[100]
_default_low_dac_threshold = 31
_cryo_default_low_dac_threshold = 49
_default_cryo=False
_default_low_dac_asic_test = False

rate_cut=[10000,1000]#,100] #,10]
suffix = ['no_cut','10kHz_cut','1kHz_cut','100Hz_cut']

v2a_nonrouted_channels=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57]

vdda_reg = dict()
vdda_reg[1] = 0x00024132
vdda_reg[2] = 0x00024132
vdda_reg[3] = 0x00024134
vdda_reg[4] = 0x00024136
vdda_reg[5] = 0x00024138
vdda_reg[6] = 0x0002413a
vdda_reg[7] = 0x0002413c
vdda_reg[8] = 0x0002413e

vddd_reg = dict()
vddd_reg[1] = 0x00024131
vddd_reg[2] = 0x00024133
vddd_reg[3] = 0x00024135
vddd_reg[4] = 0x00024137
vddd_reg[5] = 0x00024139
vddd_reg[6] = 0x0002413b
vddd_reg[7] = 0x0002413d
vddd_reg[8] = 0x0002413f

def get_tile_from_io_channel(io_channel):
    return np.floor( (io_channel-1-((io_channel-1)%4))/4+1)

def get_all_tiles(io_channel_list):
    tiles = set()
    for io_channel in io_channel_list:
        tiles.add(get_tile_from_io_channel(io_channel))
    return list(tiles)

def get_reg_pairs(io_channels):
    tiles = get_all_tiles(io_channels)
    reg_pairs = []
    for tile in tiles:
        reg_pairs.append( (vdda_reg[tile], vddd_reg[tile]) )
    return reg_pairs


def set_pacman_power(c, vdda=46020, vddd=40605):
    active_io_channels = []
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            active_io_channels.append(io_channel)
    reg_pairs = get_reg_pairs(active_io_channels)
    for pair in reg_pairs:
        c.io.set_reg(pair[0], vdda)
        c.io.set_reg(pair[1], vddd)
    c.io.set_reg(0x00000014, 1) # enable global larpix power
    c.io.set_reg(0x00000010, 0b11111111) # enable tiles to be powered
    time.sleep(0.1)

def initial_setup(ctr, controller_config):
    now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    fname="trigger_rate_%s_" % suffix[ctr] #str(rate_cut[ctr])
    fname=fname+str(now)+".h5"
    c = base___no_enforce.main(controller_config, logger=True, filename=fname)
    return c, fname

def initial_setup_low_dac(controller_config):
    now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    fname="low_thresh_trigger_rate_"#str(rate_cut[ctr])
    fname=fname+str(now)+".h5"
    c = base___no_enforce.main(controller_config, logger=True, filename=fname)
    return c, fname

def find_mode(l):
    a = Counter(l)
    return a.most_common(1)

def get_parallel_groups(chip_key_dict):
    #sort by io group, ioc
    groups = []
    ctr = 0
    while True:
        current_group = []
        for key in chip_key_dict:
            if ctr >= len(chip_key_dict[key]): continue
            current_group.append(chip_key_dict[key][ctr])
        ctr += 1
        if len(current_group)==0: break
        groups.append(current_group)
    return groups

def asic_test(c, chips_to_test, forbidden, threshold, runtime, enforce_initial):
    channels = [i for i in range(0,64) if i not in v2a_nonrouted_channels]
    chips = dict()
    reset_threshold = 10000
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            network_ids = c.get_network_ids(io_group, io_channel, root_first_traversal=True)
            network_ids.remove('ext')
            chips[(io_group, io_channel)] = [larpix.key.Key(io_group, io_channel, chip) for chip in network_ids if larpix.key.Key(io_group, io_channel, chip) in chips_to_test ]
    c.io.double_send_packets = False
    grouped_chips_to_test = get_parallel_groups(chips)
    base___no_enforce.reset(c)
    set_pacman_power(c, vdda=46020)
    for chip_key_group in grouped_chips_to_test:
        chip_register_pairs=[]
        for chip_key in chip_key_group:
            for channel in channels: #range(64):
                p = (chip_key,channel)
                if p in forbidden:
                    print(p,' skipped')
                    continue
                c[chip_key].config.channel_mask[channel] = 0
                c[chip_key].config.csa_enable[channel] = 1
            c[chip_key].config.threshold_global = threshold
            c[chip_key].config.enable_hit_veto = 0
         #   c[chip_key].config.pixel_trim_dac = [31]*64
         #   c[chip_key].config.enable_periodic_reset = 1 # registers 128
         #   c[chip_key].config.enable_rolling_periodic_reset = 1 # registers 128
         #   c[chip_key].config.periodic_reset_cycles = 64 # registers [163-165]
         #   chip_register_pairs.append( (chip_key, list(range(0,65))+[128,163,164,165]) )
            chip_register_pairs.append( (chip_key, list(range(131,139))+[64, 128]+list(range(66,74)) ) )
            c.logger.record_configs([c[chip_key]])
     
        c.multi_write_configuration(chip_register_pairs)
        c.multi_write_configuration(chip_register_pairs)
        if enforce_initial: 
            ok, diff = c.enforce_configuration(chip_register_pairs, timeout=0.01, n=3, n_verify=3)
            if not ok: 
                print('***config error on',len(diff), 'registers***')
                set_pacman_power(c, vdda=0)
                ok, diff = c.enforce_configuration(chip_register_pairs, timeout=0.01, n=3, n_verify=3)
                set_pacman_power(c, vdda=46020)

        base___no_enforce.flush_data(c)
        c.logger.enable()
        c.run(runtime,'collect data')
        c.logger.flush()
        c.logger.disable()

        chip_triggers = c.reads[-1].extract('chip_id')
        rate = len(chip_triggers)/runtime
        try:
            for packet in c.reads[-1]:
                if not packet.chip_id in [int(chip_key.chip_id) for chip_key in chip_key_group]: print(packet)
        except:
            print(packet)
        offending_chip = find_mode(chip_triggers)
        print('total rate:', rate, '\toffending chip:', offending_chip)
        for chip_key in chip_key_group:
            channel_triggers = c.reads[-1].extract('channel_id',chip_key=chip_key)
            print(chip_key,' \toffending channel, triggers: {}'.format(find_mode(channel_triggers)))
        if rate > 0:
            if not int(offending_chip[0][0]) in [int(chip_key.chip_id) for chip_key in chip_key_group]: 
                print('Noisy chip elsewhere on board..... resetting')
                base___no_enforce.reset(c)
  
        for chip_key in chip_key_group:
            c[chip_key].config.channel_mask=[1]*64
            c[chip_key].config.csa_enable=[0]*64
            c[chip_key].config.threshold_global = 255
            c[chip_key].config.enable_hit_veto = 1
            c.multi_write_configuration(chip_register_pairs)
            c.multi_write_configuration(chip_register_pairs)
            c.logger.record_configs([c[chip_key]])

        if rate > reset_threshold:
            print('Rate too high: \t',rate, 'Hz --- automatic reset triggered')
            base___no_enforce.reset(c)
        else:
            ok, diff = c.enforce_configuration(chip_key_group, timeout=0.01, n=3, n_verify=3)
            if not ok: 
                print('***config error on',len(diff), 'registers***')
                base___no_enforce.reset(c)

def low_dac_asic_test(c, chips_to_test, forbidden, threshold, runtime, enforce_initial):
    channels = [i for i in range(0,64) if i not in v2a_nonrouted_channels]
    chips = dict()
    reset_threshold = 10000
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            network_ids = c.get_network_ids(io_group, io_channel, root_first_traversal=True)
            network_ids.remove('ext')
            chips[(io_group, io_channel)] = [larpix.key.Key(io_group, io_channel, chip) for chip in network_ids if larpix.key.Key(io_group, io_channel, chip) in chips_to_test ]
    c.io.double_send_packets = False
    grouped_chips_to_test = get_parallel_groups(chips)
    base___no_enforce.reset(c)
    set_pacman_power(c, vdda=46020)
    for chip_key_group in grouped_chips_to_test:
        chip_register_pairs=[]
        for chip_key in chip_key_group:
            for channel in channels: #range(64):
                p = (chip_key,channel)
                if p in forbidden:
                    print(p,' skipped')
                    continue
                c[chip_key].config.channel_mask[channel] = 0
                c[chip_key].config.csa_enable[channel] = 1
            c[chip_key].config.threshold_global = threshold
            c[chip_key].config.enable_hit_veto = 0
            c[chip_key].config.pixel_trim_dac = [31]*64
            c[chip_key].config.enable_periodic_reset = 1 # registers 128
            c[chip_key].config.enable_rolling_periodic_reset = 1 # registers 128
            c[chip_key].config.periodic_reset_cycles = 64 # registers [163-165]
            chip_register_pairs.append( (chip_key, list(range(0,65))+[128,163,164,165]) )
            chip_register_pairs.append( (chip_key, list(range(131,139))+[64, 128]+list(range(66,74)) ) )
            c.logger.record_configs([c[chip_key]])
        c.multi_write_configuration(chip_register_pairs)
        c.multi_write_configuration(chip_register_pairs)
        all_rates = [0]
        rates = dict()
        it_count = 0
        for key in chip_key_group: rates[key]=0
        while any(all_rates) < 2:
            if it_count >10: break
            it_count += 1
            update_keys = [chipkey for chipkey in chip_key_group if rates[chipkey] < 2]
            for chip_key in update_keys: c[chip_key].config.threshold_global = c[chip_key].config.threshold_global - 1
            for chip_key in [chipkey for chipkey in chip_key_group if not chip_key in update_keys]:
                c[chip_key].channel_mask = [1]*64
                c[chip_key].csa_enable = [0]*64
            c.multi_write_configuration(chip_register_pairs)
            c.multi_write_configuration(chip_register_pairs)
            if enforce_initial: 
                ok, diff = c.enforce_registers(chip_register_pairs, timeout=0.01, n=3, n_verify=3)
            base___no_enforce.flush_data(c)
            #c.logger.enable()
            c.run(runtime,'collect data')
            #c.logger.flush()
            #c.logger.disable()

            chip_triggers = c.reads[-1].extract('chip_id')
            rate = len(chip_triggers)/runtime
            rates = dict()
            all_rates = []
            for chip_key in update_keys: 
                this_chip_count = chip_triggers.count(chip_key.chip_id)
                all_rates.append(this_chip_count)
                rates[chip_key] = this_chip_count
            for chip_key in chip_key_group: 
                if not chip_key in update_keys: rates[chip_key]=9999999
            try:
                for packet in c.reads[-1]:
                    if not packet.chip_id in [int(chip_key.chip_id) for chip_key in chip_key_group]: print(packet)
            except:
                print(packet)
            offending_chip = find_mode(chip_triggers)
            print('total rate:', rate, '\toffending chip:', offending_chip)
            for chip_key in chip_key_group:
                channel_triggers = c.reads[-1].extract('channel_id',chip_key=chip_key)
                print(chip_key,' \toffending channel, triggers: {}'.format(find_mode(channel_triggers)))
            if rate > 0:
                if not int(offending_chip[0][0]) in [int(chip_key.chip_id) for chip_key in chip_key_group]: 
                    print('Noisy chip elsewhere on board..... resetting')
                    base___no_enforce.reset(c)
                    c.multi_write_configuration(chip_register_pairs)
                    c.multi_write_configuration(chip_register_pairs)


        print('Final test:')
        for chip_key in chip_key_group:
            for channel in channels: #range(64):
                p = (chip_key,channel)
                if p in forbidden:
                    print(p,' skipped')
                    continue
                c[chip_key].config.channel_mask[channel] = 0
                c[chip_key].config.csa_enable[channel] = 1

        base___no_enforce.flush_data(c)
        c.logger.enable()
        c.run(runtime,'collect data')
        c.logger.flush()
        c.logger.disable()
        if True:
            chip_triggers = c.reads[-1].extract('chip_id')
            rate = len(chip_triggers)/runtime
            try:
                for packet in c.reads[-1]:
                    if not packet.chip_id in [int(chip_key.chip_id) for chip_key in chip_key_group]: print(packet)
            except:
                print(packet)
            offending_chip = find_mode(chip_triggers)
            print('total rate:', rate, '\toffending chip:', offending_chip)
            for chip_key in chip_key_group:
                channel_triggers = c.reads[-1].extract('channel_id',chip_key=chip_key)
                print(chip_key,' \toffending channel, triggers: {}'.format(find_mode(channel_triggers)))
            if rate > 0:
                if not int(offending_chip[0][0]) in [int(chip_key.chip_id) for chip_key in chip_key_group]: 
                    print('Noisy chip elsewhere on board..... resetting')
                    base___no_enforce.reset(c)

  
        for chip_key in chip_key_group:
            c[chip_key].config.channel_mask=[1]*64
            c[chip_key].config.csa_enable=[0]*64
            c[chip_key].config.threshold_global = 255
            c[chip_key].config.enable_hit_veto = 1
            c.multi_write_configuration(chip_register_pairs)
            c.multi_write_configuration(chip_register_pairs)
            c.logger.record_configs([c[chip_key]])

        if True:
            ok, diff = c.enforce_registers(chip_register_pairs, timeout=0.01, n=3, n_verify=3)
            if not ok: 
                print('***config error on',len(diff), 'registers***')
                base___no_enforce.reset(c)
        
              
def unique_channel_id(io_group, io_channel, chip_id, channel_id):
    return channel_id + 100*(chip_id + 1000*(io_channel + 1000*(io_group)))


def from_unique_to_chip_key(unique):
    io_group = (unique // (100*1000*1000)) % 1000
    io_channel = (unique // (100*1000)) % 1000
    chip_id = (unique // 100) % 1000
    return larpix.Key(io_group, io_channel, chip_id)

def chip_key_to_string(chip_key):
    return '-'.join([str(int(chip_key.io_group)),str(int(chip_key.io_channel)),str(int(chip_key.chip_id))])
              
def from_unique_to_channel_id(unique):
    return int(unique) % 100
              
              
def evaluate_rate(fname, ctr, runtime, forbidden):
    cut = 99999
    if ctr >= 0:
        cut = rate_cut[ctr]
    else:
        cut = 1000.

    f = h5py.File(fname,'r')
    data_mask=f['packets'][:]['packet_type']==0
    data=f['packets'][data_mask]

    io_group=data['io_group'].astype(np.uint64)
    io_channel=data['io_channel'].astype(np.uint64)
    chip_id=data['chip_id'].astype(np.uint64)
    channel_id=data['channel_id'].astype(np.uint64)
    unique_channels = set(unique_channel_id(io_group, io_channel, chip_id, channel_id))

    for unique in sorted(unique_channels):
        channel_mask = unique_channel_id(io_group, io_channel, chip_id, channel_id) == unique
        triggers = len(data[channel_mask]['dataword'])
        if triggers/runtime > cut:
            pair = ( chip_key_to_string(from_unique_to_chip_key(unique)), from_unique_to_channel_id(unique) )
            if pair not in forbidden:
                forbidden.append(pair)
                print(pair,' added to do not enable list')
    return forbidden


def chip_key_string(chip_key):
    return '-'.join([str(int(chip_key.io_group)),str(int(chip_key.io_channel)),str(int(chip_key.chip_id))])

              
def save_do_not_enable_list(forbidden):
    d = {}
    for p in forbidden:
        #ck = chip_key_string(p[0])
        ck = str(p[0])
        #ck = p[0]
        if ck not in d: d[ck]=[]
        if p[1] not in d[ck]: d[ck].append(p[1])        
    now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    with open('trigger-rate-DO-NOT-ENABLE-channel-list-'+now+'.json','w') as outfile:
        json.dump(d, outfile, indent=4)
        return 

              
def main(controller_config=_default_controller_config, chip_key=_default_chip_key, threshold=_default_threshold, runtime=_default_runtime, disabled_list=_default_disabled_list, cryo=_default_cryo, low_dac_asic_test=_default_low_dac_asic_test):
    print('START ITERATIVE TRIGGER RATE TEST')

    c = base___no_enforce.main(controller_config)
    chips_to_test = c.chips.keys()
    if not chip_key is None: chips_to_test = [chip_key]
    print('chips to test: ',chips_to_test)
    print('==> \tfound ASICs to test')

    forbidden=[] # list of (chip key, channel) to disable, to be updated as script progresses
    if disabled_list:
        print('applying disabled list: ', disabled_list)
        with open(disabled_list,'r') as f:
            disable_input=json.load(f)
            for key in disable_input.keys():
                channel_list = disable_input[key]
                for chan in channel_list:
                    forbidden.append((key,chan))
    else:
        print('No disabled list provided. Default disabled list applied.')
        for chip_key in chips_to_test:
            for channel in v2a_nonrouted_channels:
                forbidden.append((chip_key,channel))
    print('==> \tinitial channel disable list set')
    
    if isinstance(threshold, list):
        for ithr, thr in enumerate(threshold):
            enforce_initial = False
            this_it_runtime = runtime
            if ithr > 1: enforce_initial = True
            if ithr==0: this_it_runtime=runtime/2
            for ctr in range(len(rate_cut)):
                c, fname = initial_setup(ctr, controller_config)
                print('==> \ttesting ASICs with ',rate_cut[ctr],' Hz trigger rate threshold, Global DAC', thr)
                asic_test(c, chips_to_test, forbidden, thr, this_it_runtime, enforce_initial)
                if ctr==3: continue
                n_initial=len(forbidden)
                forbidden = evaluate_rate(fname, ctr, this_it_runtime, forbidden)
                n_final=len(forbidden)
                print('==> \tdo not enable list updated with ',n_final-n_initial,' additional channels')
    elif isinstance(threshold, int):
        for ctr in range(len(rate_cut)):
            c, fname = initial_setup(ctr, controller_config)
            print('==> \ttesting ASICs with ',rate_cut[ctr],' Hz trigger rate threshold, Global DAC', threshold)
            enforce_initial = True
            asic_test(c, chips_to_test, forbidden, threshold, runtime, enforce_initial)
            if ctr==3: continue
            n_initial=len(forbidden)
            forbidden = evaluate_rate(fname, ctr, runtime, forbidden)
            n_final=len(forbidden)
            print('==> \tdo not enable list updated with ',n_final-n_initial,' additional channels')
    
    if not low_dac_asic_test: return c

    print('\n========= Performing low Global threshold trigger rate test ============\n')
    ctr = -1
    enforce_initial = True
    low_dac_test_threshold = _default_low_dac_threshold
    if cryo: low_dac_test_threshold = _cryo_default_low_dac_threshold
    c, fname = initial_setup_low_dac(controller_config)
    low_dac_asic_test(c, chips_to_test, forbidden, low_dac_test_threshold, runtime, enforce_initial)
    n_initial=len(forbidden)
    forbidden = evaluate_rate(fname, ctr, runtime, forbidden)
    n_final=len(forbidden)
    print('==> \tdo not enable list updated with ',n_final-n_initial,' additional channels')

    save_do_not_enable_list(forbidden)
    print('END ITERATIVE TRIGGER RATE TEST')
    return c

              
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra newtork config file''')
    parser.add_argument('--chip_key', default=_default_chip_key, type=str, help='''If specified, only collect data from specified chip''')
    parser.add_argument('--threshold', default=_default_threshold, type=int, help='''Global threshold value to set (default=%(default)s)''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Duration for run (in seconds) (default=%(default)s)''')
    parser.add_argument('--disabled_list', default=_default_disabled_list, type=str, help='''File containing json-formatted dict of <chip key>:[<channels>] to disable''')
    parser.add_argument('--cryo',default=_default_cryo,action='store_true',help='''Flag for cryogenic operation''')
    parser.add_argument('--low_dac_asic_test',default=_default_low_dac_asic_test,action='store_true',help='''Flag to perform low dac asic test''')
    args = parser.parse_args()
    c = main(**vars(args))

