'''
Creates a base controller object and loads the specified configuration onto the chip

Usage:
    python3 -i load_config.py --config_name <configuration name>

'''

import sys
import os
import glob
import argparse

import larpix
import larpix.io
import larpix.logger

import base

_default_config_name='configs/'
_default_controller_config=None

config_format = 'config-{chip_key}-*.json'

def main(config_name=_default_config_name, controller_config=_default_controller_config, *args, **kwargs):
    print('START LOAD CONFIG')

    # create controller
    c = base.main(controller_config, *args, **kwargs)

    # set configuration
    if not os.path.isdir(config_name):
        for chip_key,chip in c.chips.items():
            print('loading',config_name)
            chip.config.load(config_name)
    else:
        # load all configurations in directory for chips
        for chip_key,chip in c.chips.items():
            config_files = sorted(glob.glob(os.path.join(config_name, config_format.format(chip_key=chip_key))))
            if config_files:
                print('loading',config_files[-1])
                chip.config.load(config_files[-1])

    # write configuration
    c.io.double_send_packets = True
    c.io.group_packets_by_io_group = False
    for chip_key, chip in reversed(c.chips.items()):
        print('write',chip_key)
        c.write_configuration(chip_key)
        c.write_configuration(chip_key)
    base.flush_data(c)

    # verify
    print('verifying')
    print('SKIPPING VERIFY!!!')
    #for chip_key in c.chips:
    #    ok, diff = c.verify_configuration(chip_key, timeout=0.1)
    #    if not ok:
    #        print('config error',diff)
    #        print('packets',len(c.reads[-1].extract('packet_type',packet_type=0)))
    c.io.double_send_packets = False

    print('END LOAD CONFIG')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--config_name', default=_default_config_name, type=str, help='''Directory or file to load chip configurations from (default=%(default)s)''')
    args = parser.parse_args()
    c = main(**vars(args))
