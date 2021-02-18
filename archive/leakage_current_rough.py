import larpix
import larpix.io
import larpix.logger

import base

import argparse
import json

_default_controller_config=None
_default_chip_key=None
_default_threshold=128
_default_runtime=1
_default_channels=range(64)

def main(controller_config=_default_controller_config, chip_key=_default_chip_key, threshold=_default_threshold, runtime=_default_runtime, channels=_default_channels):
    print('START ROUGH LEAKAGE')

    # create controller
    c = base.main(controller_config, logger=True)

    chips_to_test = c.chips.keys()
    if not chip_key is None:
        chips_to_test = [chip_key]

    # set configuration
    print('threshold',threshold)
    print('channels',channels)
    for chip_key in chips_to_test:
        for channel in channels:
            c[chip_key].config.channel_mask[channel] = 0
            c[chip_key].config.threshold_global = threshold

    # write configuration
    c.io.double_send_packets = True
    for chip_key in chips_to_test:
        registers = list(range(131,139)) # channel mask
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)

        registers = [64] # threshold
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)

        ok, diff = c.verify_configuration(chip_key, timeout=0.01)
        if not ok:
            print('config error',diff)
        c.io.double_send_packets = False
        c.logger.record_configs([c[chip_key]])

        base.flush_data(c)
        print('run for',runtime,'sec')
        c.logger.enable()
        c.run(runtime,'collect data')
        c.logger.flush()
        print('packets read',len(c.reads[-1]))
        c.logger.disable()

        print(chip_key,'triggers:',len(c.reads[-1]),'\trate: {:0.2f}Hz (per channel: {:0.2f}Hz)'.format(
            len(c.reads[-1])/runtime, len(c.reads[-1])/runtime/len(channels)))
        
        c.io.double_send_packets = True
        for channel in channels:
            c[chip_key].config.channel_mask[channel] = 1
        c[chip_key].config.threshold_global = 255
        c.write_configuration(chip_key, registers)
        c.write_configuration(chip_key, registers)
        #c.disable(chip_key)

    print('END ROUGH LEAKAGE')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra newtork config file''')
    parser.add_argument('--chip_key', default=_default_chip_key, type=str, help='''If specified, only collect data from specified chip''')
    parser.add_argument('--threshold', default=_default_threshold, type=int, help='''Global threshold value to set (default=%(default)s)''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Duration for run (in seconds) (default=%(default)s)''')
    parser.add_argument('--channels', default=_default_channels, type=json.loads, help='''List of channels to collect data from (json formatted)''')
    args = parser.parse_args()
    c = main(**vars(args))

