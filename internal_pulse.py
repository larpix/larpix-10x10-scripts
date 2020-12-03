'''
Loads specified configuration file and issues a set number of test pulses to the specified channels

Usage:
  python3 -i internal_pulse.py --config_name <config file/dir> --controller_config <controller config file>

'''
import larpix
import larpix.io
import larpix.logger

import base
import load_config

import argparse
import json
from collections import defaultdict

_default_config_name=None
_default_controller_config=None
_default_chip_key=None
_default_pulse_dac=10
_default_n_pulses=10
_default_channels=[
        0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 14, 15, 16,
        17, 18, 19, 20, 21, 26, 27, 28, 29, 30, 31, 32,
        33, 34, 35, 36, 37, 41, 42, 43, 44, 45, 46, 47, 48,
        49, 50, 51, 52, 53, 58, 59, 60, 61, 62, 63
        ]
_default_runtime=0.1
_default_start_dac=95
_default_track_stats=False

def main(config_name=_default_config_name, controller_config=_default_controller_config, chip_key=_default_chip_key, pulse_dac=_default_pulse_dac, n_pulses=_default_n_pulses, channels=_default_channels, runtime=_default_runtime, start_dac=_default_start_dac, track_stats=_default_track_stats):
    print('START INTERNAL PULSE')
    pulse_dac = int(pulse_dac)
    n_pulses = int(n_pulses)

    # create controller
    c = None
    if config_name is None:
        c = base.main(controller_config, logger=True)
    else:
        if controller_config is None:
            c = load_config.main(config_name, logger=True)
        else:
            c = load_config.main(config_name, controller_config, logger=True)

    # set initial configuration
    print('channels', channels)
    print('pulse_dac', pulse_dac)
    print('n_pulses', n_pulses)

    chips_to_test = c.chips.keys()
    if not chip_key is None:
        chips_to_test = [chip_key]

    c.io.double_send_packets = True
    for chip_key in chips_to_test:
        c[chip_key].config.adc_hold_delay = 15
        registers = [129]
        c.write_configuration(chip_key, registers)
    
    # verify
    #for chip_key in chips_to_test:
    #    ok, diff = c.verify_configuration(chip_key, timeout=0.01)
    #    if not ok:
    #        print('config error',diff)
    #    else:
    #        print('config ok')
    c.logger.record_configs(list(c.chips.values()))

    # speed up data transmission
    c.io.group_packets_by_io_group = True

    # issue pulses
    total_inwindow = defaultdict(int)
    total_outwindow = defaultdict(int)    
    total_expected_inwindow = defaultdict(int)
    total_windows = 0
    print('pulsing...')
    for channel in channels:
        print('channel',channel)
        c.io.double_send_packets = True
        for chip_key in chips_to_test:
            c.enable_testpulse(chip_key, [channel], start_dac)
            total_expected_inwindow[(chip_key,channel)] += n_pulses
        base.flush_data(c, runtime=runtime, rate_limit=len(c.chips)*64)
        c.io.double_send_packets = False        
            
        for i in range(n_pulses):
            for chip_key in chips_to_test:
                c[chip_key].config.csa_testpulse_dac -= pulse_dac
                
            c.logger.enable()
            c.multi_write_configuration(
                [(chip_key, c.chips[chip_key].config.register_map['csa_testpulse_dac'])
                 for chip_key in chips_to_test],
                write_read=runtime,
                connection_delay=0.001
            )
            c.logger.disable()
            for chip_key in chips_to_test:
                c[chip_key].config.csa_testpulse_dac = start_dac
            c.multi_write_configuration(
                [(chip_key, c.chips[chip_key].config.register_map['csa_testpulse_dac'])
                 for chip_key in chips_to_test],
                write_read=0,
                connection_delay=0
            )
            '''
            for chip_key in chips_to_test:
                c.enable_testpulse(chip_key, [channel], start_dac)            
            '''
            total_windows += 1
            if track_stats:
                triggers = map(tuple,c.reads[-1].extract('chip_key','channel_id',packet_type=0))
            else:
                triggers = list()
            for trigger in triggers:
                if trigger[-1] == channel:
                    total_inwindow[trigger] += 1
                else:
                    total_outwindow[trigger] += 1

            print('\tpulse',i+1,'/',n_pulses,len(c.reads[-1]),'packets',end='\r')
        print()
        if track_stats:
            for chip_key in chips_to_test:
                eff = total_inwindow[(chip_key,channel)] / (total_expected_inwindow[(chip_key,channel)] + 1e-15)
                print(chip_key,'-',channel,'trigger eff:','{:0.2f}'.format(eff),
                      '({}/{})'.format(total_inwindow[(chip_key,channel)],total_expected_inwindow[(chip_key,channel)]))
        
        c.reads = []
    
    if track_stats:       
        print()
        print('summary:')
        print('channels responding (>0 efficiency): {}/{} ({:0.2f})'.format(
            channels_responding(total_inwindow), len(chips_to_test)*len(channels),
            channels_responding(total_inwindow)/(len(chips_to_test)*len(channels))
            ))
        print('channels with high efficiency (>0.85 efficiency): {}/{} ({:0.2f})'.format(
            channels_responding_w_high_eff(total_inwindow, total_expected_inwindow, cutoff=0.85),
            len(chips_to_test)*len(channels), \
            channels_responding_w_high_eff(total_inwindow, total_expected_inwindow, cutoff=0.85) / (len(chips_to_test)*len(channels))
            ))
        print('overall efficiency (per channel): {:0.2f}'.format(
            overall_efficiency(total_inwindow, total_expected_inwindow)        
            ))
        print('overall cross-talk (per channel): {:0.2f}'.format(
            overall_cross_talk(n_pulses, total_windows, total_outwindow) / (len(chips_to_test))
            ))

    print('END INTERNAL PULSE')
    return c

def channels_responding(total_inwindow):
    ''' Number of channels with >0 in-window triggers '''
    return len([key for key,trigs in total_inwindow.items() if trigs > 0])

def channels_responding_w_high_eff(total_inwindow, expected_trigs, cutoff=0.75):
    ''' Number of channels that trigger at >cuffoff efficiency '''
    return len([key for key,trigs in expected_trigs.items() if total_inwindow[key]/(trigs + 1e-15) > cutoff])

def overall_efficiency(inwindow_trigs, expected_trigs):
    ''' Average trigger efficiency across channels (includes non-responsive channels)'''
    return sum([min(inwindow_trigs[key]/(expected_trigs[key]+1e-15),1) for key in expected_trigs]) / (len(expected_trigs)+1e-15)

def overall_cross_talk(npulses, total_windows, outwindow_trigs):
    ''' Average number of channels triggering on test pulses to other channels '''
    if len(outwindow_trigs) == 0:
        return 0.
    return sum([trigs for key,trigs in outwindow_trigs]) / (abs(total_windows - npulses * len(outwindow_trigs)) + 1e-15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_name', default=_default_config_name, type=str, help='''Directory or file to load chip configs from''')
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network config file''')
    parser.add_argument('--chip_key', default=_default_chip_key, type=str, help='''If specified, only pulse specified chip key''')
    parser.add_argument('--pulse_dac', default=_default_pulse_dac, type=int, help='''Amplitude for test pulses in DAC counts (default=%(default)s)''')
    parser.add_argument('--n_pulses', default=_default_n_pulses, type=int, help='''Number of test pulses to issue on each channel (default=%(default)s)''')
    parser.add_argument('--channels', default=_default_channels, type=json.loads, help='''List of channels to issue test pulses on (default=%(default)s)''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Time window to collect data after issuing each test pulse (in seconds) (default=%(default)s)''')
    parser.add_argument('--start_dac', default=_default_start_dac, type=int, help='''Starting DAC value to issue test pulses from (default=%(default)s)''')
    parser.add_argument('--track_stats', action='store_true', default=_default_track_stats, help='''Keep track of channel-by-channel triggering statistics and print a summary at the end''')
    args = parser.parse_args()
    c = main(**vars(args))
