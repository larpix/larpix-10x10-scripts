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
_default_outdir='./'
_default_disabled_channels=None

def main(config_name=_default_config_name, controller_config=_default_controller_config, runtime=_default_runtime, outdir=_default_outdir, disabled_channels=_default_disabled_channels):
    print('START RUN')
    # create controller
    c = None
    if config_name is None:
        c = base.main(controller_config)
    else:
        if controller_config is None:
            c = load_config.main(config_name, logger=True, disabled_channels=disabled_channels)
        else:
            c = load_config.main(config_name, controller_config, logger=True, disabled_channels=disabled_channels)

    external_trigger_channel = 6
    for chip in c.chips:
        print('enabling external triggers')
        c[chip].config.external_trigger_mask[external_trigger_channel] = 0
        c[chip].config.channel_mask[external_trigger_channel] = 0
        c.write_configuration(chip)
    c.io.set_reg(0x02014,0xFFFF) # disable forward triggers to larpix
    #c.io.set_reg(0x02014,0x0000) # enable forward triggers to larpix

    print('Wait 3 seconds for cooling the ASICs...')
    time.sleep(3)

    '''
    if disabled_channels is not None:
        for chip_key in c.chips:
            _disable = []
            for ch in disabled_channels['All']:
                _disable.append(ch)
            if chip_key in disabled_channels:
                for ch_list in disabled_channels[chip_key]:
                    _disable.append(ch_list)
            #print(' chip_key: ', chip_key)
            #print(' disabled: ', _disable)
            #print(' --------- ')
            #print(' len(_disable): ', len(_disable))
            for channel in _disable:
                #sif chip_key==
                #print(' === chip_key, channel: ', chip_key, channel)

                c[chip_key].config.channel_mask[channel] = 1
                c[chip_key].config.csa_enable[channel] = 0
            c.write_configuration(chip_key,'channel_mask')
            c.write_configuration(chip_key,'csa_enable')
            ok,diff = c.enforce_configuration(chip_key,n=10,n_verify=10,timeout=0.01)
            if not ok:
                print('config error',diff)
            else:
                print(chip_key,'ok')
    '''
    if True:
    #while True:
        #break
        counter = 0
        #start_time = time.time()
        #last_time = start_time
        c.logger = larpix.logger.HDF5Logger(directory=outdir)
        print('new run file at ',c.logger.filename)
        c.logger.record_configs(list(c.chips.values()))
        c.logger.enable()
        c.start_listening()
        start_time = time.time()
        last_time = start_time
        while True:
            try:
                pkts, bs = c.read()
                #counter += len(pkts)
                counter += len(pkts)
                c.reads = []
                now = time.time()
                if now > start_time + runtime: break
                if now > last_time + 1:
                    #print('average rate: {:0.2f}Hz\r'.format(counter/(time.time()-start_time)),end='')
                    print('average rate [delta_t = {:0.2f} s]: {:0.2f}Hz\r'.format(now-last_time,counter/(now-last_time)),end='')
                    counter = 0
                    last_time = now
            except:
                c.logger.flush()
                raise
        c.stop_listening()
        c.read()
        c.logger.flush()

    print('END RUN')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config_name', default=_default_config_name, type=str, help='''Directory or filename to load chip configurations from''')
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--outdir', default=_default_outdir, type=str, help='''Directory to send data files to''')
    parser.add_argument('--runtime', default=_default_runtime, type=float, help='''Time duration before flushing remaining data to disk and initiating a new run (in seconds) (default=%(default)s)''')
    parser.add_argument('--disabled_channels', default=_default_disabled_channels, type=json.loads, help='''json-formatted dict of <chip key>:[<channels>] you'd like disabled''')
    args = parser.parse_args()
    c = main(**vars(args))
