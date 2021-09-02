'''
Loads specified configuration file and collects data until killed (cleanly exits)

Usage:
  python3 -i start_run.py --config_name <config file/dir> --controller_config <controller config file>

'''
import larpix
import larpix.io
import larpix.logger
import larpix.format.rawhdf5format as rhdf5
import larpix.format.pacman_msg_format as pacman_msg_fmt

import base
#import load_config
import enforce_loaded_config

import os
import argparse
import json
from collections import defaultdict
import time

_default_config_name=None
_default_controller_config=None
_default_runtime=30*60 # 30-min run files
_default_outdir='./'
_default_disabled_channels=None

def power_registers():
    adcs=['VDDA', 'IDDA', 'VDDD', 'IDDD']
    data = {}
    for i in range(1,9,1):
        l = []
        offset = 0
        for adc in adcs:
            if adc=='VDDD': offset = (i-1)*32+17
            if adc=='IDDD': offset = (i-1)*32+16
            if adc=='VDDA': offset = (i-1)*32+1
            if adc=='IDDA': offset = (i-1)*32
            l.append( offset )
        data[i] = l
    return data

def main(config_name=_default_config_name, controller_config=_default_controller_config, runtime=_default_runtime, outdir=_default_outdir, disabled_channels=_default_disabled_channels):
    print('START RUN')
    startTime = time.time()
    # create controller
    c = None
    if config_name is None:
        c = base.main(controller_config)
    else:
        if controller_config is None:
            c = enforce_loaded_config.main(config_name, logger=False, disabled_channels=disabled_channels)
        else:
            c = enforce_loaded_config.main(config_name, controller_config, logger=False, disabled_channels=disabled_channels)

    print(time.time()-startTime,' seconds to load & enforce configuration')
            
    trigger_forward_enable=False
    if trigger_forward_enable:
        external_trigger_channel = 6
        for chip in c.chips:
            print('enabling external triggers')
            c[chip].config.external_trigger_mask[external_trigger_channel] = 0
            c[chip].config.channel_mask[external_trigger_channel] = 0
            c.write_configuration(chip)
        c.io.set_reg(0x02014,0x0000) # enable forward triggers to larpix
    else:
        c.io.set_reg(0x02014,0xffffffff) # disable forward triggers to larpix

    #c.io.set_reg(0x25014,12)
    #c.io.set_reg(0x25015,0x10)
    #c.enable_analog_monitor('1-25-11',0)
        
    print('Wait 3 seconds for cooling the ASICs...')
    time.sleep(3)

    c.io.disable_packet_parsing = True
    #if True:
    while True:
        counter = 0
        last_count = 0
        c.io.enable_raw_file_writing = True
        c.io.raw_filename = time.strftime(c.io.default_raw_filename_fmt)
        c.io.join()
        rhdf5.to_rawfile(filename=c.io.raw_filename, io_version=pacman_msg_fmt.latest_version)
        print('new run file at ',c.io.raw_filename)

        c.start_listening()
        start_time = time.time()
        last_time = start_time
        print('here')
        while True:
            #try:
            c.read()
            now = time.time()
            if now > start_time + runtime: break
            if now > last_time + 5 and c.io.raw_filename and os.path.isfile(c.io.raw_filename):
                counter = rhdf5.len_rawfile(c.io.raw_filename, attempts=0)
                power = power_registers()
                adc_read = 0x00024001
                val_vdda = c.io.get_reg(adc_read+power[7][0], io_group=1)
                val_idda = c.io.get_reg(adc_read+power[7][1], io_group=1)
                val_vddd = c.io.get_reg(adc_read+power[7][2], io_group=1)
                val_iddd = c.io.get_reg(adc_read+power[7][3], io_group=1)
                vdda=(((val_vdda>>16)>>3)*4)
                idda=(((val_idda>>16)-(val_idda>>31)*65535)*500*0.01)
                vddd=(((val_vddd>>16)>>3)*4)
                iddd=(((val_iddd>>16)-(val_iddd>>31)*65535)*500*0.01)

                print(' average message rate [delta_t = {:0.2f} s]: {:0.2f} ({:0.02f}Hz)   VDDA: {:0.1f} mV    IDDA: {:0.1f} mA    VDDD: {:0.1f} mV    IDDD: {:0.1f} mA\r'.format(now-last_time,counter-last_count,(counter-last_count)/(now-last_time+1e-9),vdda,idda,vddd,iddd),end='')
                last_count = counter
                last_time = now
 
            #except KeyboardInterrupt:
            #    break
        c.stop_listening()
        c.read()
        c.io.join()
        break
    #c.disable_analog_monitor('1-25-11',0)
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
