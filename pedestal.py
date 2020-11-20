'''
Collect data using LArPix internal periodic trigger

Usage:

        python3 pedestal.py <args>
'''

import sys
import argparse
import json

import larpix
import larpix.io

import base

_default_controller_config=None
_default_periodic_trigger_cycles=100000
_default_runtime=60
_default_channels=range(64)
_default_chip_key=None
_default_disabled_channels=[]

def main(controller_config=_default_controller_config, periodic_trigger_cycles=_default_periodic_trigger_cycles, runtime=_default_runtime, channels=_default_channels, chip_key=_default_chip_key, disabled_channels={None:_default_disabled_channels}.copy(), *args, **kwargs):
    print('START PEDESTAL')

    # create controller
    c = base.main(controller_config=controller_config, logger=True)
    c.io.group_packets_by_io_group = False

    # set args
    chip_keys = [chip_key]
    if chip_key is None:
        chip_keys = list(c.chips.keys())
    if disabled_channels is None:
        disabled_channels = list()

    # set configuration
    c.io.double_send_packets = True
    for chip_key, chip in [(chip_key, chip) for (chip_key, chip) in c.chips.items() if chip_key in chip_keys]:
        #print(' --- chip_key:', chip_key, ' --- ')
        chip.config.periodic_trigger_mask = [1]*64
        chip.config.channel_mask = [1]*64
        for channel in channels:
            chip.config.periodic_trigger_mask[channel] = 0
            chip.config.channel_mask[channel] = 0
        chip.config.periodic_trigger_cycles = periodic_trigger_cycles
        chip.config.enable_periodic_trigger = 1
        chip.config.enable_rolling_periodic_trigger = 1
        chip.config.enable_periodic_reset = 1
        chip.config.enable_rolling_periodic_reset = 0
        chip.config.enable_hit_veto = 0
        chip.config.periodic_reset_cycles = 4096

        # Disable channels
        #print(' disabling channels: ')
        for disabled_key in disabled_channels:
            if disabled_key == chip_key or disabled_key == 'All':
                for disabled_channel in disabled_channels[disabled_key]:
                    chip.config.csa_enable[disabled_channel] = 0
                    #print('     ', disabled_channel)

        # write configuration
        registers = list(range(155,163)) # periodic trigger mask
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)
        registers = list(range(131,139)) # channel mask
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)
        registers = list(range(166,170)) # periodic trigger cycles
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)
        registers = [128] # periodic trigger, reset, rolling trigger, hit veto
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, 'enable_rolling_periodic_reset')
        c.write_configuration(chip_key, 'enable_rolling_periodic_reset')
        c.write_configuration(chip_key, 'periodic_reset_cycles')
        c.write_configuration(chip_key, 'periodic_reset_cycles')
        c.write_configuration(chip_key, 'csa_enable')
        c.write_configuration(chip_key, 'csa_enable')

    for chip_key in c.chips:
        ok, diff = c.verify_configuration(chip_key, timeout=0.01)
        if not ok:
            print('config error',diff)
    c.io.double_send_packets = True
    c.logger.record_configs(list(c.chips.values()))

    print('start pedestal run')
    base.flush_data(c, rate_limit=(1+1/(periodic_trigger_cycles*1e-7)*len(c.chips)))
    c.logger.enable()
    c.run(runtime,'collect data')
    c.logger.flush()
    print('packets read',len(c.reads[-1]))
    c.logger.disable()

    print('END PEDESTAL')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--periodic_trigger_cycles', default=_default_periodic_trigger_cycles, type=int, help='''Periodic trigger rate in LArPix clock cycles (default=%(default)s))''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Duration to collect data (in seconds (default=%(default)s)''')
    parser.add_argument('--channels', default=_default_channels, type=json.loads, help='''List of channels to collect data from (json formatting)''')
    parser.add_argument('--chip_key', default=_default_chip_key, type=str, help='''If specified, only collect data from specified chip key''')
    parser.add_argument('--disabled_channels', default=_default_disabled_channels, type=json.loads, help='''List of channels to disable (json formatting)''')
    args = parser.parse_args()
    c = main(**vars(args))

