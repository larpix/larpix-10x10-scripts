'''
Creates a base controller object and loads the specified configuration onto the chip

Usage:
    python3 -i load_config.py <configuration name>

'''

import sys
import os
import glob

import larpix
import larpix.io
import larpix.logger

import base

config_format = 'config-{chip_key}-*.json'

def main(config_name, *args, **kwargs):
    print('load config')

    # create controller
    c = base.main(*args, **kwargs)

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
    for chip_key, chip in c.chips.items():
        c.write_configuration(chip_key)
        c.write_configuration(chip_key)

    # verify
    for chip_key in c.chips:
        ok, diff = c.verify_configuration(chip_key, timeout=0.01)
        if not ok:
            print('config error',diff)
    c.io.double_send_packets = False

    return c

if __name__ == '__main__':
    c = main(*sys.argv[1:])
