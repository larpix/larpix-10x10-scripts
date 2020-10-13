import larpix
import larpix.io
import larpix.logger

import base

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
_default_disable_threshold = 20
_default_reset_threshold = 10000

def _reset_and_reload(c, controller_config):
    print('start resetting and reloading configs')
    c_new = base.main(controller_config_file=controller_config)
    for chip_key in c.chips:
        print('load config',chip_key)
        c_new[chip_key].config = c[chip_key].config
        c.write_configuration(chip_key)
        ok, diff = c.verify_configuration(chip_key, timeout=0.1)
        if not ok:
            print('config error',diff[chip_key])
    print('done resetting and reloading configs')
    return c_new

def main(controller_config=None, chip_key=None, channels=_default_channels, disabled_channels={None:_default_disabled_channels}.copy(), runtime=_default_runtime, target_rate=_default_target_rate, base_config=_default_config, disable_threshold=_default_disable_threshold, reset_threshold=_default_reset_threshold):
    print('START AUTOCONFIG')
    
    # create controller
    c = base.main(controller_config=controller_config)    

    print()
    print('base config',base_config)
    print('enabled channels',channels)
    print('disabled channels',disabled_channels)
    print('target rate',target_rate)
    print('disable threshold',disable_threshold)
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

    _default_ignore = defaultdict(list)
    for chip_key in chips_to_configure:
        if None in disabled_channels:
            _default_ignore[chip_key] += disabled_channels[None]
        if "All" in disabled_channels:
            _default_ignore[chip_key] += disabled_channels["All"]
        if chip_key in disabled_channels:
            _default_ignore[chip_key] += disabled_channels[chip_key]
        channels_to_configure = defaultdict(list, [(chip_key,channels.copy()) for chip_key in chips_to_configure])

    print()
    for chip_key in chips_to_configure:
        c.io.double_send_packets = True
        print('set config',chip_key)
        c[chip_key].config.load(_default_config)

        for channel in channels:
            if channel not in _default_ignore[chip_key]:
                c[chip_key].config.channel_mask[channel] = 0
        for channel in _default_ignore[chip_key]:
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
        repeat = True
        while repeat:
            print('check rate',chip_key,end=' ')
            repeat = False
            base.flush_data(c)
            c.multi_read_configuration(read_config_spec,timeout=runtime/10,message='rate check')
            triggered_channels = c.reads[-1].extract('chip_key','channel_id',chip_key=chip_key,packet_type=0)
            print('(total rate={}Hz)'.format(len(triggered_channels)/(runtime/10)))
            rates = dict([(channel, triggered_channels.count(list(channel))/(runtime/10)) for channel in set(map(tuple,triggered_channels))])
            if rates:
                max_rate = max(rates.values())
                for channel,rate in rates.items():
                    chip_key,channel = channel
                    if rate > target_rate and channel in channels_to_configure[chip_key] \
                       and chip_key in c.chips and rate == max_rate:
                        print('disable',chip_key,channel,'rate was',rate,'Hz')
                        c.disable(chip_key,[channel])
                        c[chip_key].config.csa_enable[channel] = 0
                        c.write_configuration(chip_key,'csa_enable')
                        channels_to_configure[chip_key].remove(channel)
                        repeat = True
                    if rate > reset_threshold:
                        c = _reset_and_reload(c,controller_config)
            if repeat:
                c.write_configuration(chip_key)
            c.reads = []

    # walk down global threshold
    print()
    print('reducing global threshold')
    repeat = defaultdict(lambda : True, [(key, True) for key in chips_to_configure])
    target_reached = False
    while any(repeat.values()) or not len(repeat.values()):
        # check rate
        print('check rate',end=' ')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        print('(total rate={}Hz)'.format(len(triggered_channels)/runtime))
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and repeat[chip_key] and chip_key in c.chips:
                print('reached target',chip_key,channel,'rate was',rate,'Hz')
                target_reached = True
                repeat[chip_key] = False
                c[chip_key].config.threshold_global = min(c[chip_key].config.threshold_global+1,255)
                print('\tthreshold',c[chip_key].config.threshold_global)
                c.write_configuration(chip_key,'threshold_global')
                c.write_configuration(chip_key,'threshold_global')                
            if rate > reset_threshold:
                c = _reset_and_reload(c,controller_config)

        # walk down global threshold
        if not target_reached:
            print('reducing thresholds')
            for chip_key in chips_to_configure:
                if chip_key in c.chips:
                    if repeat[chip_key] and c[chip_key].config.threshold_global > 0:
                        c[chip_key].config.threshold_global -= 1
                        repeat[chip_key] = True
                    elif c[chip_key].config.threshold_global == 0:
                        repeat[chip_key] = False
                    c.write_configuration(chip_key,'threshold_global')
                    c.write_configuration(chip_key,'threshold_global')                            
        target_reached = False
        c.reads = []        
    print('initial global thresholds:',dict([(chip_key,c[chip_key].config.threshold_global) for chip_key in chips_to_configure if chip_key in c.chips]))

    print()
    print('increasing global threshold')
    above_target = defaultdict(lambda : False)
    for _ in range(10):
        # check rate
        print('check rate',end=' ')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        print('(total rate={}Hz)'.format(len(triggered_channels)/runtime))        
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and not above_target[chip_key] and chip_key in c.chips:
                print('increasing threshold',chip_key,channel,'rate was',rate,'Hz')
                above_target[chip_key] = True
                c[chip_key].config.threshold_global = min(c[chip_key].config.threshold_global+1,255)
                print('\tthreshold',c[chip_key].config.threshold_global)
                c.write_configuration(chip_key,'threshold_global')
                c.write_configuration(chip_key,'threshold_global')
            if rate > reset_threshold:
                c = _reset_and_reload(c,controller_config)

        # continue once rate is below target
        if not above_target or not any(above_target.values()):
            break
        else:
            above_target = defaultdict(lambda : False)
        c.reads = []        
    print('final global thresholds:',dict([(chip_key,c[chip_key].config.threshold_global) for chip_key in chips_to_configure if chip_key in c.chips]))

    print()
    print('decreasing pixel trim')
    repeat = defaultdict(lambda : True, [((key, channel),True) for key,channels in channels_to_configure.items() for channel in channels])
    target_reached = False
    while any(repeat.values()) or not len(repeat.values()):
        # check rate
        print('check rate',end=' ')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        print('(total rate={}Hz)'.format(len(triggered_channels)/runtime))        
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and chip_key in c.chips:
                print('reached target',chip_key,channel,'rate was',rate,'Hz')
                if repeat[(chip_key, channel)]:
                    target_reached = True
                if c[chip_key].config.pixel_trim_dac[channel] == 31 and rate > disable_threshold:
                    c.disable(chip_key,[channel])
                    c[chip_key].config.csa_enable[channel] = 0
                    c.write_configuration(chip_key,'csa_enable')                    
                    print('disable threshold reached')                    
                repeat[(chip_key,channel)] = False
                c[chip_key].config.pixel_trim_dac[channel] = min(c[chip_key].config.pixel_trim_dac[channel]+1,31)
                print('\ttrim',c[chip_key].config.pixel_trim_dac[channel])
                c.write_configuration(chip_key,'pixel_trim_dac')
                c.write_configuration(chip_key,'pixel_trim_dac')
            if rate > reset_threshold:
                c = _reset_and_reload(c,controller_config)            

        # walk down trims
        if not target_reached:
            print('reducing trims')
            for chip_key, channels in channels_to_configure.items():
                if chip_key in c.chips:
                    for channel in channels:
                        if repeat[(chip_key,channel)] and c[chip_key].config.pixel_trim_dac[channel] > 0:
                            c[chip_key].config.pixel_trim_dac[channel] -= 1
                        elif c[chip_key].config.pixel_trim_dac[channel] == 0:
                            repeat[(chip_key,channel)] = False
                    c.write_configuration(chip_key,'pixel_trim_dac')
                    c.write_configuration(chip_key,'pixel_trim_dac')
        target_reached = False
        c.reads = []                
    print('initial pixel trims:')
    for chip_key in chips_to_configure:
        if chip_key in c.chips:
            print('\t',chip_key,c[chip_key].config.pixel_trim_dac)

    print()
    print('increasing pixel trim')
    above_target = defaultdict(lambda : False)
    for _ in range(10):
        # check rate
        print('check rate',end=' ')
        base.flush_data(c)
        c.multi_read_configuration(read_config_spec,timeout=runtime,message='rate check')
        triggered_channels = c.reads[-1].extract('chip_key','channel_id',packet_type=0)
        print('(total rate={}Hz)'.format(len(triggered_channels)/runtime))        
        for chip_key, channel in set(map(tuple,triggered_channels)):
            rate = triggered_channels.count([chip_key,channel])/runtime
            if rate > target_rate and channel in channels_to_configure[chip_key] \
               and not above_target[(chip_key,channel)] and chip_key in c.chips:
                print('increasing pixel trim',chip_key,channel,'rate was',rate,'Hz')
                above_target[(chip_key,channel)] = True
                if c[chip_key].config.pixel_trim_dac[channel] == 31 and rate > disable_threshold:
                    c.disable(chip_key,[channel])
                    c[chip_key].config.csa_enable[channel] = 0
                    c.write_configuration(chip_key,'csa_enable')                    
                    print('disable threshold reached')
                c[chip_key].config.pixel_trim_dac[channel] = min(c[chip_key].config.pixel_trim_dac[channel]+1,31)
                print('\ttrim',c[chip_key].config.pixel_trim_dac[channel])
                c.write_configuration(chip_key,'pixel_trim_dac')
                c.write_configuration(chip_key,'pixel_trim_dac')
            if rate > reset_threshold:
                c = _reset_and_reload(c,controller_config)

        # continue once rate is below target
        if not above_target or not any(above_target.values()):
            break
        else:
            above_target = defaultdict(lambda : False)
        c.reads = []                    
    print('final pixel trims:')
    for chip_key in chips_to_configure:
        if chip_key in c.chips:
            print('\t',chip_key,c[chip_key].config.pixel_trim_dac)

    print()
    print('saving configs...')
    for chip_key in chips_to_configure:
        if chip_key in c.chips:
            # save config
            time_format = time.strftime('%Y_%m_%d_%H_%M_%S_%Z')
            config_filename = 'config-'+str(chip_key)+'-'+time_format+'.json'
            c[chip_key].config.write(config_filename, force=True)
            print('\t',chip_key,'saved to',config_filename)

    print('final configured rate: ',end='')
    base.flush_data(c)    
    c.run(runtime,'final rate')
    n_packets = len(c.reads[-1].extract('io_group',packet_type=0))
    print('{:0.2f}Hz ({:0.2f}Hz/channel)'.format(n_packets/runtime,n_packets/runtime/sum([len(ch) for ch in channels_to_configure.values()])))

    print('END AUTOCONFIG')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=None, type=str)
    parser.add_argument('--base_config', default=_default_config, type=str, help='''Chip configuration to load prior to threshold scan (default=%(default)s)''')    
    parser.add_argument('--chip_key', default=None, type=str, help='''defaults to all chips''')
    parser.add_argument('--channels', default=_default_channels, type=json.loads)
    parser.add_argument('--disabled_channels', default={None:_default_disabled_channels}.copy(), type=json.loads,
                        help='''json-formatted list of channels to disable: {<chip-key>:[<list of channels>]}, use <chip-key>="All" for channels to disable on all chips''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''period to measure rate for (seconds, default=%(default)s)''')
    parser.add_argument('--target_rate', default=_default_target_rate, type=float, help='''target max rate for individual channel (Hz, default=%(default)s)''')
    parser.add_argument('--disable_threshold', default=_default_disable_threshold, type=float, help='''maximum rate allowed with trim at 31 (Hz, default=%(default)s)''')    
    args = parser.parse_args()
    c = main(**vars(args))
