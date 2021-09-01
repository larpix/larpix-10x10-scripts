'''
Loads specified configuration file and collects data until killed (cleanly exits)

Usage:
  python3 -i pedestal_raw.py --controller_config <controller config file>

'''
import larpix
import larpix.io
import larpix.logger
import base

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
_default_disabled_channels=None
_default_disabled_list=None
_default_log_simple=False
#_default_log_qc=False
_default_baseline_cut_value=125.
_default_apply_baseline_cut=False
_default_noise_cut_value=3.
_default_apply_noise_cut=False
_default_refine=False

def configure_pedestal(c, periodic_trigger_cycles, disabled_channels):
    c.io.group_packets_by_io_group = True
    c.io.double_send_packets = True

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
        
    print('enforcing correct configuration...')
    ok,diff = c.enforce_configuration(list(c.chips.keys()), timeout=0.01, connection_delay=0.01, n=10, n_verify=10)
    if not ok:
        raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))    
    c.io.group_packets_by_io_group = False
    c.io.double_send_packets = False


    
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



def evaluate_pedestal(datalog_file, baseline_cut_value, apply_baseline_cut, noise_cut_value, apply_noise_cut):
    f = h5py.File(datalog_file,'r')
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
        if apply_baseline_cut:
            if np.mean(adc)>=baseline_cut_value: flag=True
        if apply_noise_cut:
            if np.std(adc)>=noise_cut_value or np.std(adc)==0: flag=True
        if flag==True:
            _chip_key_ = from_unique_to_chip_key(unique)
            _chip_key_string_ = chip_key_string(_chip_key_)
            if _chip_key_ in record: record[_chip_key_string_]=[]
            record[_chip_key_string_].append( from_unique_to_channel_id(unique) )    
    record["All"]=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57] # channels NOT routed out to pixel pads for LArPix-v2
    return record



def save_simple_json(record):
    now = time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
    with open('bad-channels-'+now+'.json','w') as outfile: json.dump(record, outfile, indent=4)



def main(controller_config=_default_controller_config,
         periodic_trigger_cycles=_default_periodic_trigger_cycles,
         runtime=_default_runtime,
         disabled_list=_default_disabled_list,
         log_simple=_default_log_simple,
         #log_qc=_default_log_qc,
         baseline_cut_value=_default_baseline_cut_value,
         apply_baseline_cut=_default_apply_baseline_cut,
         noise_cut_value=_default_noise_cut_value,
         apply_noise_cut=_default_apply_noise_cut,
         refine=_default_refine):

    if refine:
        if log_simple and apply_baseline_cut==False and apply_noise_cut==False:
            print('Insufficient input for refined pedestal measurement.')
            #print('No revised disabled channels list. Save to --log_simple and/or --log_qc to generate a new disabled channels list.')
            print('No revised disabled channels list. Save to --log_simple to generate a new disabled channels list.')
            print('==> EXITING')
            return

    #if (log_simple or log_qc) and apply_baseline_cut==False and apply_noise_cut==False:
    if log_simple and apply_baseline_cut==False and apply_noise_cut==False:
        print('To save revised bad channels list, --apply_baseline_cut and/or --apply_noise_cut')
        print('==> EXITING ')
        return

    disabled_channels = list()
    now = time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
    ped_fname="pedestal_%s" % now
    if disabled_list:
        print('applying disabled list: ',disabled_list)
        with open(disabled_list,'r') as f: disabled_channels = json.load(f)
        ped_fname=ped_fname+"____"+str(disabled_list.split(".json")[0])
    else:
        disabled_channels["All"]=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57] # channels NOT routed out to pixel pads for LArPix-v2
        print('WARNING: no default disabled list applied')
    ped_fname= ped_fname+".h5"

    c = base.main(controller_config=controller_config, logger=True, filename=ped_fname)
    configure_pedestal(c, periodic_trigger_cycles, disabled_channels)
    print('Wait 3 seconds for cooling the ASICs...'); time.sleep(3)
    base.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
    run_pedestal(c, runtime)

    revised_disabled_channels = defaultdict(list)    
    #if log_simple or log_qc:
    if log_simple:
        revised_disabled_channels = evaluate_pedestal(ped_fname, baseline_cut_value, apply_baseline_cut, noise_cut_value, apply_noise_cut)
        if log_simple: save_simple_json(revised_disabled_channels)
        
    if refine:
        now = time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
        ped_fname="recursive_pedestal_%s.h5" % now
        c = base.main(controller_config=controller_config, logger=True, filename=ped_fname)
        configure_pedestal(c, periodic_trigger_cycles, revised_disabled_channels)
        print('Wait 3 seconds for cooling the ASICs...'); time.sleep(3)
        base.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
        run_pedestal(c, runtime)    

    print('Issue soft reset')
    c.io.reset_larpix(length=24)
        
    return c



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''REQUIRED --- Hydra network configuration file''')
    parser.add_argument('--periodic_trigger_cycles', default=_default_periodic_trigger_cycles, type=int, help='''Periodic trigger rate in LArPix clcock cycles''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Pedestal runtime duration''')
    parser.add_argument('--disabled_list', default=_default_disabled_list, type=str, help='''JSON-formatted dict of <chip key>:[<channels>] you'd like disabled''')
    parser.add_argument('--log_simple', default=_default_log_simple, action='store_true', help='''Log bad channels to simple JSON, dict of <chip key>:['channels']''')
    #parser.add_argument('--log_qc', default=_default_log_qc, action='store_true', help='''Log bad channels to LArPix QC JSON''')
    parser.add_argument('--baseline_cut_value', default=_default_baseline_cut_value, type=float, help='''Pedestal mean cut value: channels with pedestal mean at or exceeding this value are added to disabled list''')
    parser.add_argument('--apply_baseline_cut', default=_default_apply_baseline_cut, action='store_true', help='''Flag that if present, pedestal mean cut value applied''')
    parser.add_argument('--noise_cut_value', default=_default_noise_cut_value, type=float, help='''Pedestal noise standard deviation cut value: channels with pedestal standard deviation at or exceeding this value are added to disabled list''')
    parser.add_argument('--apply_noise_cut', default=_default_apply_noise_cut, action='store_true', help='''Flag that if present, pedestal standard deviation cut value applied''')
    parser.add_argument('--refine', default=_default_refine, action='store_true', help='''Run pedestal recursively to measure pedestal with bad channels removed''')

    args = parser.parse_args()
    c = main(**vars(args))

