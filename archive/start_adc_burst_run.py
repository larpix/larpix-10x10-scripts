'''
Loads specified configuration file and collects data until killed (cleanly exits)

Usage:
  python3 -i start_run.py --config_name <config file/dir> --controller_config <controller config file>

'''
import larpix
import larpix.io
import larpix.logger

import base
import load_config

import argparse
import json
from collections import defaultdict
import time

_default_config_name=None
_default_controller_config=None
_default_runtime=30*60 # 30-min run files
_default_n_adc_burst = 2

def main(config_name=_default_config_name, controller_config=_default_controller_config, runtime=_default_runtime, n_adc_burst=_default_n_adc_burst):
    print('START RUN')
    # create controller
    c = None
    if config_name is None:
        c = base.main(controller_config)
    else:
        if controller_config is None:
            c = load_config.main(config_name, logger=True)
        else:
            c = load_config.main(config_name, controller_config, logger=True)

    chips_to_test = c.chips.keys()
    for chip_key in chips_to_test:
        c[chip_key].config.adc_burst_length = n_adc_burst
        c.write_configuration(chip_key,'adc_burst_length')
        c.write_configuration(chip_key,'adc_burst_length')

    ok, diff = c.enforce_configuration(chip_key, timeout=0.01, n=10, n_verify=10)
    if not ok:
        print('config error',diff)
            
    while True:
        counter = 0
        start_time = time.time()
        last_time = start_time
        c.logger = larpix.logger.HDF5Logger()
        print('new run file at ',c.logger.filename)
        c.logger.enable()
        c.start_listening()
        while True:
            try:
                pkts, bs = c.read()
                counter += len(pkts)
                c.reads = []
                now = time.time()
                if now > start_time + runtime: break
                if now > last_time + 1:
                    print('average rate: {:0.2f}Hz\r'.format(counter/(time.time()-start_time)),end='')
                    last_time = now
            except:
                c.logger.flush()
                raise
        c.stop_listening()
        c.read()
        c.logger.flush()

    print('END RUN')
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_name', default=_default_config_name, type=str, help='''Directory or filename to load chip configurations from''')
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Time duration before flushing remaining data to disk and initiating a new run (in seconds) (default=%(default)s)''')
    parser.add_argument('--n_adc_burst', default=_default_n_adc_burst, type=float, help='''No. Conversions per channel hit''')
    args = parser.parse_args()
    c = main(**vars(args))
