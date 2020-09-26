import larpix
import larpix.io
import larpix.logger

import base
import base_warm

import time
import sys
from copy import copy
import argparse
import json
from collections import defaultdict
import time

_default_config = 'configs/autothreshold_base.json'
_default_channels = [
        0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16,
        17, 18, 19, 20, 21, 26, 27, 28, 29, 30, 31, 32,
        33, 34, 35, 36, 37, 41, 42, 43, 44, 45, 46, 47, 48,
        49, 50, 51, 52, 53, 58, 59, 60, 61, 62, 63
	]
_default_disabled_channels = [
    6,7,8,9,
    22,23,24,25,
    38,39,40,
    54,55,56,57
]
_default_runtime = 1
_default_target_rate = 2

def main(controller_config=None, chip_key=None, channels=_default_channels, disabled_channels=_default_disabled_channels, runtime=_default_runtime, target_rate=_default_target_rate, base_config=_default_config):
    print('configure thresholds')

    # create controller
    c = base.main(controller_config_file=controller_config)    
    #c = base_warm.main(controller_config_file=controller_config)
    #c = base_cold.main(controller_config_file=controller_config)

    # set initial configuration
    if disabled_channels:
        for channel in disabled_channels:
            if channel in channels:
                channels.remove(channel)
    else:
        disabled_channels = list()
    print()
    print('enabled channels',channels)
    print('disabled channels',disabled_channels)
    print('target rate',target_rate)
    print('runtime',runtime)

    test_chip_keys = []
    for io_group in c.network:
        for io_channel in c.network[io_group]:
            test_chip_ids = [chip_id for chip_id,deg in c.network[io_group][io_channel]['miso_us'].out_degree() if deg == 0] # get network leaves
            test_chip_keys += [larpix.Key(io_group,io_channel,chip_id) for chip_id in test_chip_ids]
    print('test packets will be sent to',test_chip_keys)
    read_config_spec = [(key,0) for key in test_chip_keys]
            
    chips_to_configure = c.chips
    if not chip_key is None:
        chips_to_configure = [chip_key]

    channels_to_configure = defaultdict(list, [(chip_key,channels.copy()) for chip_key in chips_to_configure])

    print()
    for chip_key in chips_to_configure:
        c.io.double_send_packets = True
        print('set config',chip_key)
        c[chip_key].config.load(_default_config)

        for channel in channels:
            c[chip_key].config.channel_mask[channel] = 0
        for channel in disabled_channels:
            c[chip_key].config.csa_enable[channel] = 0

        # write configuration
        print('verify',chip_key)
        c.write_configuration(chip_key)
        base.flush_data(c)
        ok, diff = c.verify_configuration(chip_key, timeout=0.1)
        if not ok:
            print('config error',diff[chip_key])
        base.flush_data(c)
        c.io.double_send_packets = True        

        # verify no high rate channels
        print('check rate',chip_key)
        repeat = True
        while repeat:
            repeat = False
            base.flush_data(c)
            c.multi_read_configuration(read_config_spec,timeout=runtime/10,message='rate check')
            triggered_channels = c.reads[-1].extract('channel_id',chip_key=chip_key,packet_type=0)
            for channel in set(triggered_channels):
                rate = triggered_channels.count(channel)/(runtime/10)
                if rate > target_rate and channel in channels_to_configure[chip_key]:
                    print('disable',chip_key,channel,'rate was',rate,'Hz')
                    c.disable(chip_key,[channel])
                    channels_to_configure[chip_key].remove(channel)
                    repeat = True

    # walk down global threshold
    print()
    print('reducing global threshold')
    repeat = defaultdict(lambda : True)
    target_reached = False
    while any(repeat.values()) or not repeat.values():
        # check rate
        print('check rate')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and repeat[chip_key]:
                print('reached target',chip_key,channel,'rate was',rate,'Hz')
                target_reached = True
                repeat[chip_key] = False
                c[chip_key].config.threshold_global = min(c[chip_key].config.threshold_global+1,255)
                c.write_configuration(chip_key,'threshold_global')
                c.write_configuration(chip_key,'threshold_global')                


        # walk down global threshold
        if not target_reached:
            for chip_key in chips_to_configure:
                if repeat[chip_key] and c[chip_key].config.threshold_global > 0:
                    c[chip_key].config.threshold_global -= 1
                    repeat[chip_key] = True
                elif c[chip_key].config.threshold_global == 0:
                    repeat[chip_key] = False
                c.write_configuration(chip_key,'threshold_global')
                c.write_configuration(chip_key,'threshold_global')                            
        target_reached = False
    print('initial global thresholds:',dict([(chip_key,c[chip_key].config.threshold_global) for chip_key in chips_to_configure]))

    print()
    print('increasing global threshold')
    above_target = defaultdict(lambda : False)
    for _ in range(10):
        # check rate
        print('check rate')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and not above_target[chip_key]:
                print('increasing threshold',chip_key,channel,'rate was',rate,'Hz')
                above_target[chip_key] = True
                c[chip_key].config.threshold_global = min(c[chip_key].config.threshold_global+1,255)
                c.write_configuration(chip_key,'threshold_global')
                c.write_configuration(chip_key,'threshold_global')                

        # continue once rate is below target
        if not any(above_target.values()):
            break
        else:
            above_target = defaultdict(lambda : False)
    print('final global thresholds:',dict([(chip_key,c[chip_key].config.threshold_global) for chip_key in chips_to_configure]))

    print()
    print('decreasing pixel trim')
    repeat = defaultdict(lambda : True)
    target_reached = False
    while any(repeat.values()) or not repeat.values():
        # check rate
        print('check rate')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and repeat[(chip_key,channel)]:
                print('reached target',chip_key,channel,'rate was',rate,'Hz')
                target_reached = True
                repeat[(chip_key,channel)] = False
                c[chip_key].config.pixel_trim_dac[channel] = min(c[chip_key].config.pixel_trim_dac[channel]+1,31)
                c.write_configuration(chip_key,'pixel_trim_dac')
                c.write_configuration(chip_key,'pixel_trim_dac')                

        # walk down trims
        if not target_reached:
            for chip_key, channels in channels_to_configure.items():
                for channel in channels:
                    if repeat[(chip_key,channel)] and c[chip_key].config.pixel_trim_dac[channel] > 0:
                        c[chip_key].config.pixel_trim_dac[channel] -= 1
                    elif c[chip_key].config.pixel_trim_dac[channel] == 0:
                        repeat[(chip_key,channel)] = False
                c.write_configuration(chip_key,'pixel_trim_dac')
                c.write_configuration(chip_key,'pixel_trim_dac')                
        target_reached = False
    print('initial pixel trims:')
    for chip_key in chips_to_configure:
        print('\t',chip_key,c[chip_key].config.pixel_trim_dac)

    print()
    print('increasing pixel trim')
    above_target = defaultdict(lambda : False)
    for _ in range(10):
        # check rate
        print('check rate')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and not above_target[(chip_key,channel)]:
                print('increasing pixel trim',chip_key,channel,'rate was',rate,'Hz')
                above_target[(chip_key,channel)] = True
                c[chip_key].config.pixel_trim_dac[channel] = min(c[chip_key].config.pixel_trim_dac[channel]+1,31)
                c.write_configuration(chip_key,'pixel_trim_dac')
                c.write_configuration(chip_key,'pixel_trim_dac')                

        # continue once rate is below target
        if not any(above_target.values()):
            break
        else:
            above_target = defaultdict(lambda : False)
    print('final pixel trims:')
    for chip_key in chips_to_configure:
        print('\t',chip_key,c[chip_key].config.pixel_trim_dac)

    print()
    print('saving configs...')
    for chip_key in chips_to_configure:
        # save config
        time_format = time.strftime('%Y_%m_%d_%H_%M_%S_%Z')
        config_filename = 'config-'+str(chip_key)+'-'+time_format+'.json'
        c[chip_key].config.write(config_filename, force=True)
        print('\t',chip_key,'saved to',config_filename)

    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=None, type=str)
    parser.add_argument('--chip_key', default=None, type=str, help='''defaults to all chips''')
    parser.add_argument('--channels', default=_default_channels, type=json.loads)
    parser.add_argument('--disabled_channels', default=_default_disabled_channels, type=json.loads)
    parser.add_argument('--runtime', default=_default_runtime, type=float)
    parser.add_argument('--target_rate', default=_default_target_rate, type=float)
    args = parser.parse_args()
    c = main(**vars(args))
