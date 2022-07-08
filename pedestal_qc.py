import larpix
import larpix.io
import larpix.logger
import base
import base___no_enforce

from base___no_enforce import power_registers

import argparse
import json
import time
from copy import deepcopy
import h5py
import numpy as np
from collections import defaultdict


_default_controller_config=None
_default_periodic_trigger_cycles=100000
_default_runtime=60
_default_disabled_list=None
_default_no_log_simple=False
#_default_log_qc=False
_default_baseline_cut_value=50.
_default_no_apply_baseline_cut=False
_default_noise_cut_value=10.
_default_no_apply_noise_cut=False
_default_no_refinement=False

vdda_reg = dict()
vdda_reg[1] = 0x00024130
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
        tiles.add( int(get_tile_from_io_channel(io_channel)) )
    return list(tiles)

def get_reg_pairs(io_channels):
    tiles = get_all_tiles(io_channels)
    reg_pairs = []
    for tile in tiles:
        reg_pairs.append( (vdda_reg[tile], vddd_reg[tile]) )
    return reg_pairs


def set_pacman_power(c, vdda=46020, vddd=40605):
    for _io_group, io_channels in c.network.items():
        active_io_channels = []
        for io_channel in io_channels:
            active_io_channels.append(io_channel)
        reg_pairs = get_reg_pairs(active_io_channels)
        for pair in reg_pairs:
            c.io.set_reg(pair[0], vdda, io_group=_io_group)
            c.io.set_reg(pair[1], vddd, io_group=_io_group)
        tiles = get_all_tiles(active_io_channels)
        bit_string = list('00000000')
        for tile in tiles: bit_string[-1*tile] = '1'
        c.io.set_reg(0x00000014, 1, io_group=_io_group) # enable global larpix power
        c.io.set_reg(0x00000010, int("".join(bit_string), 2), io_group=_io_group) # enable tiles to be powered
    time.sleep(0.1)


def configure_pedestal(c, periodic_trigger_cycles, disabled_channels):
    c.io.group_packets_by_io_group = True
    c.io.double_send_packets = True
    set_pacman_power(c, vdda=0)

    print('setting triggers and resets configuration')
    chip_config_pairs = []
    for chip_key, chip in reversed(c.chips.items()):
        initial_config = deepcopy(chip.config)
        chip.config.enable_periodic_trigger = 1
        chip.config.enable_rolling_periodic_trigger = 1
        chip.config.enable_periodic_reset = 1
        chip.config.enable_rolling_periodic_reset = 0
        chip.config.enable_hit_veto = 0
        chip.config.periodic_trigger_cycles = periodic_trigger_cycles
        chip.config.periodic_reset_cycles = 4096
        chip.config.csa_enable = [1]*64
        for disabled_key in disabled_channels:
            if disabled_key == chip_key or disabled_key == 'All':
                for disabled_channel in disabled_channels[disabled_key]:
                    chip.config.csa_enable[disabled_channel] = 0
        chip_config_pairs.append((chip_key,initial_config))

    print('writing triggers and resets configuration')
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    base.flush_data(c)
    #base___no_enforce.flush_data(c)

    print('enforcing correct configuration...')
    ok,diff = c.enforce_configuration(list(c.chips.keys()), timeout=0.01, connection_delay=0.01, n=10, n_verify=10)
    if not ok:
        if any([reg not in range(66,74) for key, regs in diff.items() for reg in regs]):
            raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))

    print('setting channel, trigger masks and CSAs')
    chip_register_pairs = []
    for chip_key, chip in reversed(c.chips.items()):
        chip.config.periodic_trigger_mask = [0]*64
        chip.config.channel_mask = [0]*64
        for disabled_key in disabled_channels:
            if disabled_key == chip_key or disabled_key == 'All':
                for disabled_channel in disabled_channels[disabled_key]:
                    chip.config.periodic_trigger_mask[disabled_channel] = 1
                    chip.config.channel_mask[disabled_channel] = 1
        chip_register_pairs.append( (chip_key, list(range(131,139))+list(range(155,163)) ) )

    print('writing channel, trigger masks and CSAs configuration')
    c.multi_write_configuration(chip_register_pairs)
    c.multi_write_configuration(chip_register_pairs)
    base.flush_data(c)
    #base___no_enforce.flush_data(c)

    print('enforcing correct configuration...')
    ok,diff = c.enforce_configuration(list(c.chips.keys()), timeout=0.01, connection_delay=0.01, n=10, n_verify=10)
    if not ok:
        raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))
    c.io.group_packets_by_io_group = False
    c.io.double_send_packets = False
    set_pacman_power(c, vdda=46020)



def unique_channel_id(io_group, io_channel, chip_id, channel_id): return channel_id + 100*(chip_id + 1000*(io_channel + 1000*(io_group)))



def from_unique_to_chip_id(unique): return (int(unique)//100)%1000



def from_unique_to_channel_id(unique): return int(unique) % 100



def from_unique_to_chip_key(unique):
    io_group = (unique // (100*1000*1000)) % 1000
    io_channel = (unique // (100*1000)) % 1000
    chip_id = (unique // 100) % 1000
    return larpix.Key(io_group, io_channel, chip_id)



def chip_key_string(chip_key):
    return '-'.join([str(int(chip_key.io_group)),str(int(chip_key.io_channel)),str(int(chip_key.chip_id))])



def run_pedestal(c, runtime):
    print('START PEDESTAL RUN')
    c.logger.enable()
    c.run(runtime, 'collect data')
    c.logger.flush()
    print('packets read',len(c.reads[-1]))
    c.logger.disable()
    print('END PEDESTAL RUN')



def evaluate_pedestal(datalog_file, disabled_channels, baseline_cut_value, no_apply_baseline_cut, noise_cut_value, no_apply_noise_cut):
    
    n_bad_channels=0
    f = h5py.File(datalog_file,'r')
    unixtime = f['packets']['timestamp'][f['packets']['packet_type'] == 4]
    livetime = np.max(unixtime) - np.min(unixtime)
    
    data_mask=f['packets'][:]['packet_type']==0
    valid_parity_mask=f['packets'][data_mask]['valid_parity']==1
    data=(f['packets'][data_mask])[valid_parity_mask]

    io_group=data['io_group'].astype(np.uint64)
    io_channel=data['io_channel'].astype(np.uint64)
    chip_id=data['chip_id'].astype(np.uint64)
    channel_id=data['channel_id'].astype(np.uint64)
    unique_channels = set(unique_channel_id(io_group, io_channel, chip_id, channel_id))

    record = defaultdict(list)
    for unique in sorted(unique_channels):
        flag=False
        channel_mask = unique_channel_id(io_group, io_channel, chip_id, channel_id) == unique
        adc = data[channel_mask]['dataword']
        if len(adc)<2: continue
        if no_apply_baseline_cut==False:
            if np.mean(adc)>=baseline_cut_value: flag=True
        if no_apply_noise_cut==False:
            if np.std(adc)>=noise_cut_value or np.std(adc)==0: flag=True
        rate = len(adc)/ (livetime + 1e-9)
        if rate>2.: flag=True
        if flag==True:
            n_bad_channels+=1
            _chip_key_ = from_unique_to_chip_key(unique)
            _chip_key_string_ = chip_key_string(_chip_key_)
            if _chip_key_ in record: record[_chip_key_string_]=[]
            record[_chip_key_string_].append( from_unique_to_channel_id(unique) )
            print(_chip_key_,'  ', (unique % 100),'\t disabled')

    for key in disabled_channels.keys():
        record[key]+=disabled_channels[key]
    
    return record, n_bad_channels



def save_simple_json(record):
    now = time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
    with open('pedestal-bad-channels-'+now+'.json','w') as outfile:
        json.dump(record, outfile, indent=4)
        return now



def main(controller_config=_default_controller_config,
         periodic_trigger_cycles=_default_periodic_trigger_cycles,
         runtime=_default_runtime,
         disabled_list=_default_disabled_list,
         no_log_simple=_default_no_log_simple,
         #log_qc=_default_log_qc,
         baseline_cut_value=_default_baseline_cut_value,
         no_apply_baseline_cut=_default_no_apply_baseline_cut,
         noise_cut_value=_default_noise_cut_value,
         no_apply_noise_cut=_default_no_apply_noise_cut,
         no_refinement=_default_no_refinement):

    if no_refinement==False:
        if no_log_simple==False and no_apply_baseline_cut==True and apply_noise_cut==False:
            print('Insufficient input for refined pedestal measurement.')
            print('No revised disabled channels list. Omit --no_log_simple to generate a new disabled channels list.')
            print('==> EXITING')
            return
        
    if no_log_simple==False and no_apply_baseline_cut==True and no_apply_noise_cut==True:
        print('To save revised bad channels list, remove --no_apply_baseline_cut and/or add --no_apply_noise_cut at the command line')
        print('==> EXITING ')
        return

    disabled_channels = dict()
    now = time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
    ped_fname="pedestal_%s" % now
    if disabled_list:
        print('applying disabled list: ',disabled_list)
        with open(disabled_list,'r') as f: disabled_channels = json.load(f)
        ped_fname=ped_fname+"____"+str(disabled_list.split(".json")[0])
    else:
        nonrouted_channels=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57] # channels NOT routed out to pixel pads for LArPix-v2
        disabled_channels["All"]=nonrouted_channels
        print('No disabled list applied. Using the default bad channels list.')
        ped_fname=ped_fname+"____default_bad_channels"
    ped_fname= ped_fname+".h5"
    print('initial disabled list: ',disabled_channels)

    c = base.main(controller_config=controller_config, logger=True, filename=ped_fname, vdda=0)
    #c = base___no_enforce.main(controller_config=controller_config, logger=True, filename=ped_fname)
    configure_pedestal(c, periodic_trigger_cycles, disabled_channels)
    print('Wait 3 seconds for cooling the ASICs...'); time.sleep(3)
    base.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
    #base___no_enforce.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
    run_pedestal(c, runtime)

    revised_disabled_channels = defaultdict(list)
    revised_bad_channel_filename=None
    #if no_log_simple==False or log_qc:
    if no_log_simple==False:
        revised_disabled_channels, n_bad_channels = evaluate_pedestal(ped_fname, disabled_channels, baseline_cut_value, no_apply_baseline_cut, noise_cut_value, no_apply_noise_cut)
      #  revised_bad_channel_filename=save_simple_json(revised_disabled_channels)
        print('\n\n\n===========\t',n_bad_channels,' bad channels\t ===========\n\n\n')

    if no_refinement==False:
        ped_fname="recursive_pedestal_%s.h5" % revised_bad_channel_filename
        c = base.main(controller_config=controller_config, logger=True, filename=ped_fname, vdda=0)
        #c = base___no_enforce.main(controller_config=controller_config, logger=True, filename=ped_fname)
        configure_pedestal(c, periodic_trigger_cycles, revised_disabled_channels)
        print('Wait 3 seconds for cooling the ASICs...'); time.sleep(3)
        base.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
        #base___no_enforce.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
        run_pedestal(c, runtime)

    revised_bad_channel_filename=None
    #if no_log_simple==False or log_qc:
    if no_log_simple==False:
        revised_disabled_channels, n_bad_channels = evaluate_pedestal(ped_fname, revised_disabled_channels, baseline_cut_value, no_apply_baseline_cut, noise_cut_value, no_apply_noise_cut)
        revised_bad_channel_filename=save_simple_json(revised_disabled_channels)
        print('\n\n\n===========\t',n_bad_channels,' bad channels\t ===========\n\n\n')

    print('Soft reset issued')
    c.io.reset_larpix(length=24)

    return c


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''REQUIRED --- Hydra network configuration file''')
    parser.add_argument('--periodic_trigger_cycles', default=_default_periodic_trigger_cycles, type=int, help='''Periodic trigger rate in LArPix clcock cycles''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Pedestal runtime duration''')
    parser.add_argument('--disabled_list', default=_default_disabled_list, type=str, help='''File containing JSON-formatted dict of <chip key>:[<channels>] you'd like disabled''')
    parser.add_argument('--no_log_simple', default=_default_no_log_simple, action='store_true', help='''Disable log bad channels to simple JSON, dict of <chip key>:['channels']''')
    #parser.add_argument('--log_qc', default=_default_log_qc, action='store_true', help='''Log bad channels to LArPix QC JSON''')
    parser.add_argument('--baseline_cut_value', default=_default_baseline_cut_value, type=float, help='''Pedestal mean cut value: channels with pedestal mean at or exceeding this value are added to disabled list''')
    parser.add_argument('--no_apply_baseline_cut', default=_default_no_apply_baseline_cut, action='store_true', help='''If flag is present, disable pedestal mean cut value applied''')
    parser.add_argument('--noise_cut_value', default=_default_noise_cut_value, type=float, help='''Pedestal noise standard deviation cut value: channels with pedestal standard deviation at or exceeding this value are added to disabled list''')
    parser.add_argument('--no_apply_noise_cut', default=_default_no_apply_noise_cut, action='store_true', help='''If flag present, disable pedestal standard deviation cut value applied''')
    parser.add_argument('--no_refinement', default=_default_no_refinement, action='store_true', help='''If flag present, pedestal is not run recursively to measure pedestal with bad channels removed''')

    args = parser.parse_args()
    c = main(**vars(args))

