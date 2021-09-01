import larpix
import larpix.io
import larpix.logger
import base

import time
import argparse
import json
from copy import deepcopy
from statistics import mode

_default_controller_config=None
_default_chip_key=None
_default_threshold=128
_default_runtime=1
_default_channels=range(64)
_default_disabled_channels=None
_default_leakage_cut=10.



def run(c, runtime):
    print('run for',runtime,'sec')
    c.logger.enable()
    c.run(runtime,'collect data')
    c.logger.flush()
    print('packets read',len(c.reads[-1]))
    c.logger.disable()


    
def enable_chip(c, chip_key, channels, threshold, disabled_channels):
    chip_config_pairs=[]
    initial_config = deepcopy(c[chip_key].config)
    c[chip_key].config.threshold_global = threshold
    for channel in channels:
        if chip_key in disabled_channels:
            if channel in disabled_channels[chip_key]: continue
        if channel in disabled_channels['All']: continue
        c[chip_key].config.channel_mask[channel] = 0
        c[chip_key].config.csa_enable[channel] = 1
    chip_config_pairs.append((chip_key,initial_config))
    c.io.double_send_packets = True
    c.io.group_packets_by_io_group = True
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    base.flush_data(c)

    ok, diff = c.enforce_configuration(chip_key, timeout=0.01, n=10, n_verify=10)
    if not ok: print('config error',diff)
    c.io.double_send_packets = False
    c.io.group_packes_by_io_group = False
    c.logger.record_configs([c[chip_key]])
    base.flush_data(c)


    
def disable_chip(c, chip_key, channels):
    c.io.double_send_packets = True
    c.io.group_packes_by_io_group = True
    chip_config_pairs=[]
    initial_config = deepcopy(c[chip_key].config)
    c[chip_key].config.threshold_global = 255
    for channel in channels:
        c[chip_key].config.channel_mask[channel] = 1
        c[chip_key].config.csa_enable[channel] = 0
    chip_config_pairs.append((chip_key,initial_config))            
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    base.flush_data(c)

    ok, diff = c.enforce_configuration(chip_key, timeout=0.01, n=10, n_verify=10)
    if not ok: print('config error',diff)
    c.io.double_send_packets = False
    c.logger.record_configs([c[chip_key]])


    
def save_simple_json(record):
    now = time.strftime("%Y_%m_%d_%H_%M_%S_%Z")
    with open('bad-channels-'+now+'.json','w') as outfile: json.dump(record, outfile, indent=4)

    
    
def main(controller_config=_default_controller_config,
         chip_key=_default_chip_key,
         threshold=_default_threshold,
         runtime=_default_runtime,
         channels=_default_channels,
         disabled_channels=_default_disabled_channels,
         leakage_cut=_default_leakage_cut):
    print('START ROUGH LEAKAGE')

    bad_channel_list = deepcopy(disabled_channels)
    
    # create controller
    c = base.main(controller_config, logger=True)

    chips_to_test = c.chips.keys()
    if not chip_key is None:
        chips_to_test = [chip_key]

    # test ASIC one by one
    for chip_key in chips_to_test:

        avg_chan_trig_rate=leakage_cut+1
        while avg_chan_trig_rate>=leakage_cut:

            enable_chip(c, chip_key, channels, threshold, bad_channel_list)        
            run(c, runtime)

            avg_trig_rate = len(c.reads[-1])/runtime
            avg_chan_trig_rate = len(c.reads[-1])/runtime/len(channels)
            print(chip_key,'triggers:',len(c.reads[-1]),'\trate: {:0.2f}Hz (per channel: {:0.2f}Hz)'.format(avg_trig_rate, avg_chan_trig_rate))
            if avg_chan_trig_rate>leakage_cut:
                triggered_channels = c.reads[-1].extract('channel_id')
                mode_channel = mode(triggered_channels)
                print('channel id ',mode_channel,' added to disabled list')
                if chip_key not in bad_channel_list: bad_channel_list[chip_key]=[]
                bad_channel_list[chip_key].append(mode_channel)
                c.io.reset_larpix(length=24)
            disable_chip(c, chip_key, channels)                

    print('END ROUGH LEAKAGE')
    save_simple_json(bad_channel_list)
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra newtork config file''')
    parser.add_argument('--chip_key', default=_default_chip_key, type=str, help='''If specified, only collect data from specified chip''')
    parser.add_argument('--threshold', default=_default_threshold, type=int, help='''Global threshold value to set (default=%(default)s)''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Duration for run (in seconds) (default=%(default)s)''')
    parser.add_argument('--channels', default=_default_channels, type=json.loads, help='''List of channels to collect data from (json formatted)''')
    parser.add_argument('--disabled_channels', default=_default_disabled_channels, type=json.loads, help='''json-formatted dict of <chip key>:[<channels>] to disable''')
    parser.add_argument('--leakage_cut', default=_default_leakage_cut, type=float, help='''Leakage rate cut: ASIC channel average leakage rate not be exceeded''')
    args = parser.parse_args()
    c = main(**vars(args))

