'''
Creates a base controller object and loads the specified configuration onto the chip

Usage:
    python3 -i load_config.py --config_name <configuration name>

'''

import sys
import os
import glob
import argparse
from copy import deepcopy

import larpix
import larpix.io
import larpix.logger
import time

import base

_default_config_name='configs/'
_default_controller_config=None
_default_disabled_channels=None

config_format = 'tile-id-{tile_id}-config-{chip_key}-*.json'

def set_pacman_power(c, vdda=46020, vddd=40605):
    c.io.set_reg(0x00024130, vdda) # tile 1 VDDA
    c.io.set_reg(0x00024131, vddd) # tile 1 VDDD
    c.io.set_reg(0x00024132, vdda) # tile 2 VDDA
    c.io.set_reg(0x00024133, vddd) # tile 2 VDDD
    c.io.set_reg(0x00024134, vdda) # tile 3 VDDA
    c.io.set_reg(0x00024135, vddd) # tile 3 VDDD
    c.io.set_reg(0x00024136, vdda) # tile 4 VDDA
    c.io.set_reg(0x00024137, vddd) # tile 4 VDDD
    c.io.set_reg(0x00024138, vdda) # tile 5 VDDA
    c.io.set_reg(0x00024139, vddd) # tile 5 VDDD
    c.io.set_reg(0x0002413a, vdda) # tile 6 VDDA
    c.io.set_reg(0x0002413b, vddd) # tile 6 VDDD
    c.io.set_reg(0x0002413c, vdda) # tile 7 VDDA
    c.io.set_reg(0x0002413d, vddd) # tile 7 VDDD
    c.io.set_reg(0x0002413e, vdda) # tile 8 VDDA
    c.io.set_reg(0x0002413f, vddd) # tile 8 VDDD
    c.io.set_reg(0x00000014, 1) # enable global larpix power
    c.io.set_reg(0x00000010, 0b1011111111) # enable tiles to be powered
    c.io.set_reg(0x101C, 4) # set master clock to 10 MHz
    c.io.set_reg(0x18, 0xffffffff) #enable uarts
    time.sleep(0.1)

def main(config_name=_default_config_name, controller_config=_default_controller_config, disabled_channels=_default_disabled_channels, *args, **kwargs):
    print('START LOAD CONFIG')

    replica_dict = dict()
    
    # create controller
    c = base.main(controller_config, vdda=0, *args, **kwargs)

    c.io.group_packets_by_io_group = True
    c.io.double_send_packets = True
    
    #chip_register_pairs = []
    #possible_chip_ids = range(11,111)
    #for chip_id in possible_chip_ids:
    #    for io_group in c.network:
    #        for io_channel in c.network[io_group]:
    #            candidate_chip_key = larpix.Key(io_group, io_channel, chip_id)
    #            if candidate_chip_key in c.chips:

    # set configuration
    #chip_register_pairs = []
    chip_config_pairs = []
    for chip_key, chip in reversed(c.chips.items()):

        initial_config = deepcopy(chip.config)
        if not os.path.isdir(config_name):
            print('loading',config_name)
            chip.config.load(config_name)
        else:
            config_files = sorted(glob.glob(os.path.join(config_name, config_format.format(tile_id='*', chip_key=chip_key))))
            if config_files:
                print('loading',config_files[-1])
                chip.config.load(config_files[-1])

        # save channel mask, csa enable to apply later
        replica_dict[chip_key] = dict(
            replica_channel_mask = c[chip_key].config.channel_mask,
            replica_csa_enable = c[chip_key].config.csa_enable)

        # mask off and disable all channels
        c[chip_key].config.channel_mask=[1]*64
        c[chip_key].config.csa_enable=[0]*64
        #c[chip_key].config.enable_hit_veto = 0

        chip_config_pairs.append((chip_key,initial_config))
        #register_names = list(chip.config.compare(initial_config).keys())
        #register_addresses = sorted(list(set([addr for name in register_names for addr in chip.config.register_map[name]])))

        #for addr in register_addresses:
        #    chip_register_pairs.append( (chip_key,addr) )

        #c.write_configuration(chip_key)
        #c.write_configuration(chip_key)

        #chip_register_pairs.append( (chip_key, list(range(0,237)) ) )

    # write all config registers
    #c.io.double_send_packets = True
    #c.multi_write_configuration(chip_register_pairs, write_read=0, connection_delay=0.01)
    #c.multi_write_configuration(chip_register_pairs, write_read=0, connection_delay=0.01)
    print('writing configuration (all channels disabled)...')
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    base.flush_data(c)
            
    # enforce all config registers
    print('enforcing correct configuration...')
    ok,diff = c.enforce_configuration(list(c.chips.keys()), timeout=0.01, connection_delay=0.01, n=10, n_verify=10)
    if not ok:
        if any([reg not in range(66,74) for key,regs in diff.items() for reg in regs]):
            raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))
    #for chip_key, chip in reversed(c.chips.items()):
    #    ok, diff = c.enforce_configuration(chip_key, timeout=0.01, n=10, n_verify=10)
    #    if not ok:
    #        for key in diff:
    #            print('config error',diff)
    #        sys.exit('Failed to configure all registers \t EXITING')
    #print('LOADED CONFIGURATIONS')

            
    # enable frontend
    chip_register_pairs = []
    for chip_key, chip in reversed(c.chips.items()):
        c[chip_key].config.csa_enable=replica_dict[chip_key]['replica_csa_enable'] ### comment out to hold front end in reset

        #c[chip_key].config.csa_enable[35]=0
        #c[chip_key].config.csa_enable[36]=0
        #c[chip_key].config.csa_enable[37]=0
        
        # disable select channels
        if disabled_channels is not None:
            if 'All' in disabled_channels:
                for channel in disabled_channels['All']:
                    c[chip_key].config.csa_enable[channel] = 0
            if chip_key in disabled_channels:
                for channel in disabled_channels[chip_key]:
                    c[chip_key].config.csa_enable[channel] = 0

        chip_register_pairs.append( (chip_key, list(range(66,74)) ) )

    # write csa enable registers
    print('enabling CSAs...')
    c.io.double_send_packets = True
    c.multi_write_configuration(chip_register_pairs)
    c.multi_write_configuration(chip_register_pairs)
    base.flush_data(c)
            
    # enforce csa enable registers
    print('enforcing configuration...')
    for chip_key, chip in reversed(c.chips.items()):
        ok, diff = c.enforce_registers([(chip_key,list(range(66,74)) )], timeout=0.01, n=10, n_verify=10)
        if not ok:
            for key in diff:
                #print('config error',key,diff[key])
                raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys())) # BR 3/31/21
            #sys.exit('Failed to configure CSA\t EXITING')
    print('ENABLED FRONTEND')

            
    # channel mask
    chip_register_pairs = []
    for chip_key, chip in reversed(c.chips.items()):
        c[chip_key].config.channel_mask=replica_dict[chip_key]['replica_channel_mask']

        #c[chip_key].config.channel_mask[35]=1
        #c[chip_key].config.channel_mask[36]=1
        #c[chip_key].config.channel_mask[37]=1
        
        # disable select channels
        if disabled_channels is not None:
            if 'All' in disabled_channels:
                for channel in disabled_channels['All']:
                    c[chip_key].config.channel_mask[channel] = 1
            if chip_key in disabled_channels:
                for channel in disabled_channels[chip_key]:
                    c[chip_key].config.channel_mask[channel] = 1

        chip_register_pairs.append( (chip_key, list(range(131,139)) ) )

    # write channel mask registers
    print('writing channel mask...')
    c.multi_write_configuration(chip_register_pairs)
    c.multi_write_configuration(chip_register_pairs)
    set_pacman_power(c, vdda=46020)
    base.flush_data(c)
            
    # enforce channel mask registers
    #print('enforcing configuration...')
    #for chip_key, chip in reversed(c.chips.items()):
    #    ok, diff = c.enforce_registers([(chip_key,list(range(131,139)) )], timeout=0.01, n=10, n_verify=10)
    #    if not ok:
    #        for key in diff:
    #            print('config error',key,diff[key])
    #        #sys.exit('Failed to configure channel masks\t EXITING')
    print('APPLIED CHANNEL MASKS')

            
    c.io.double_send_packets = False

    if hasattr(c,'logger') and c.logger:
        c.logger.record_configs(list(c.chips.values()))

    print('END LOAD CONFIG')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--config_name', default=_default_config_name, type=str, help='''Directory or file to load chip configurations from (default=%(default)s)''')
    parser.add_argument('--disabled_channels', default=_default_disabled_channels, type=json.loads, help='''Json-formatted dict of <chip_key>:[<channels>] to disable (default=%(default)s)''')
    args = parser.parse_args()
    c = main(**vars(args))
