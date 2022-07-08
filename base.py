#!/usr/bin/env python3

import argparse
from copy import deepcopy

import larpix
import larpix.io
import larpix.logger
import numpy as np
import time


_default_controller_config=None
_default_pacman_version='v1rev3'
_default_logger=False
_default_reset=True

##### default network (single chip) if no hydra network provided
_default_chip_id = 2
_default_io_channel = 1
_default_miso_ds = 0
_default_mosi = 0
_default_clk_ctrl = 1

##### default IO 
_uart_phase = 0
clk_ctrl_2_clk_ratio_map = {
        0: 2,
        1: 4,
        2: 8,
        3: 16
        }

v2a_nonrouted_channels=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57]

vdda_reg = dict()
vdda_reg[1] = 0x00024130
vdda_reg[2] = 0x00024132
vdda_reg[3] = 0x00024134
vdda_reg[4] = 0x00024136
vdda_reg[5] = 0x00024138
vdda_reg[6] = 0x0002413a
vdda_reg[7] = 0x0002413c
vdda_reg[8] = 0x0002413e

vddd_reg = dict()
vddd_reg[1] = 0x00024131
vddd_reg[2] = 0x00024133
vddd_reg[3] = 0x00024135
vddd_reg[4] = 0x00024137
vddd_reg[5] = 0x00024139
vddd_reg[6] = 0x0002413b
vddd_reg[7] = 0x0002413d
vddd_reg[8] = 0x0002413f

def unique_channel_id(io_group, io_channel, chip_id, channel_id):
    return channel_id + 100*(chip_id + 1000*(io_channel + 1000*(io_group)))

def from_unique_to_chip_key(unique):
    io_group = (unique // (100*1000*1000)) % 1000
    io_channel = (unique // (100*1000)) % 1000
    chip_id = (unique // 100) % 1000
    return larpix.Key(io_group, io_channel, chip_id)

def from_unique_to_channel_id(unique):
    return int(unique) % 100

def from_unique_to_chip_id(unique):
    return int(unique//100) % 1000

def chip_key_to_string(chip_key):
    return '-'.join([str(int(chip_key.io_group)),str(int(chip_key.io_channel)),str(int(chip_key.chip_id))])

def get_tile_from_io_channel(io_channel):
    return np.floor( (io_channel-1-((io_channel-1)%4))/4+1)

def get_all_tiles(io_channel_list):
    tiles = set()
    for io_channel in io_channel_list:
        tiles.add(int(get_tile_from_io_channel(io_channel)) )
    return list(tiles)

def get_reg_pairs(io_channels):
    tiles = get_all_tiles(io_channels)
    reg_pairs = []
    for tile in tiles:
        reg_pairs.append( (vdda_reg[tile], vddd_reg[tile]) )
    return reg_pairs


def set_pacman_power(c, vdda=46020, vddd=40605):
    for _io_group, io_channels in c.network.items():
        active_io_channels = []
        for io_channel in io_channels:
            active_io_channels.append(io_channel)
        reg_pairs = get_reg_pairs(active_io_channels)
        for pair in reg_pairs:
            c.io.set_reg(pair[0], vdda, io_group=_io_group)
            c.io.set_reg(pair[1], vddd, io_group=_io_group)
        tiles = get_all_tiles(active_io_channels)
        bit_string = list('00000000')
        for tile in tiles: bit_string[-1*tile] = '1'
        c.io.set_reg(0x00000014, 1, io_group=_io_group) # enable global larpix power
        c.io.set_reg(0x00000010, int("".join(bit_string), 2), io_group=_io_group) # enable tiles to be powered
    time.sleep(0.1)


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


def flush_data(controller, runtime=0.1, rate_limit=0., max_iterations=10):
    ###### continues to read data until data rate is less than rate_limit
    for _ in range(max_iterations):
        controller.run(runtime, 'flush_data')
        if len(controller.reads[-1])/runtime <= rate_limit:
            break

def reset(c, config=None):
    ##### issue hard reset (resets state machines and configuration memory)
    if not config is None:
        new_controller = main(controller_config=config, modify_power=False, verbose=False)
        return new_controller

    c.io.reset_larpix(length=10240)
    # resets uart speeds on fpga
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group)

                
    ##### re-initialize network
    c.io.group_packets_by_io_group = False # throttle the data rate to insure no FIFO collisions
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            c.init_network(io_group, io_channel, modify_mosi=False)

            
    ###### set uart speed (v2a at 2.5 MHz transmit clock, v2b fine at 5 MHz transmit clock)
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            chip_keys = c.get_network_keys(io_group,io_channel,root_first_traversal=False)
            for chip_key in chip_keys:
                c[chip_key].config.clk_ctrl = _default_clk_ctrl
                c.write_configuration(chip_key, 'clk_ctrl')

    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[_default_clk_ctrl], io_group=io_group)
            #print('io_channel:',io_channel,'factor:',c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[_default_clk_ctrl], io_group=io_group))

    ##### issue soft reset (resets state machines, configuration memory untouched)
    c.io.reset_larpix(length=24)

    ##### setup low-level registers to enable loopback
    chip_config_pairs=[]
    for chip_key, chip in reversed(c.chips.items()):
        initial_config = deepcopy(chip.config)
        c[chip_key].config.vref_dac = 185 # register 82
        c[chip_key].config.vcm_dac = 41 # register 83
        c[chip_key].config.adc_hold_delay = 15 # register 129
        c[chip_key].config.enable_miso_differential = [1,1,1,1] # register 125
        chip_config_pairs.append((chip_key,initial_config))
    c.io.double_send_packets = True
    c.io.gruop_packets_by_io_group = True
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    flush_data(c)

    #for chip_key in c.chips:
    #    chip_registers = [(chip_key, i) for i in [82,83,125,129]]
    #    ok,diff = c.enforce_registers(chip_registers, timeout=0.01, n=10, n_verify=10)
    #    if not ok:
    #        raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))
    c.io.double_send_packets = False
    c.io.gruop_packets_by_io_group = False
    
    if hasattr(c,'logger') and c.logger: c.logger.record_configs(list(c.chips.values()))
    return c
        
def main(controller_config=_default_controller_config, pacman_version=_default_pacman_version, logger=_default_logger, vdda=46020, reset=_default_reset, enforce=True, **kwargs):
    print('[START BASE]')
    ###### create controller with pacman io
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)

     ##### setup hydra network configuration
    if controller_config is None:
        c.add_chip(larpix.Key(1, _default_io_channel, _default_chip_id))
        c.add_network_node(1, _default_io_channel, c.network_names, 'ext', root=True)
        c.add_network_link(1, _default_io_channel, 'miso_us', ('ext',_default_chip_id), 0)
        c.add_network_link(1, _default_io_channel, 'miso_ds', (_default_chip_id,'ext'), _default_miso_ds)
        c.add_network_link(1, _default_io_channel, 'mosi', ('ext', _default_chip_id), _default_mosi)
    else:
        c.load(controller_config)

    
    ###### set power to tile    
    if pacman_version=='v1rev3':
        set_pacman_power(c)

        power = power_registers()
        adc_read = 0x00024001
        for i in power.keys():
            val_vdda = c.io.get_reg(adc_read+power[i][0], io_group=1)
            val_idda = c.io.get_reg(adc_read+power[i][1], io_group=1)
            val_vddd = c.io.get_reg(adc_read+power[i][2], io_group=1)
            val_iddd = c.io.get_reg(adc_read+power[i][3], io_group=1)
            print('TILE',i,
                  '\tVDDA:',(((val_vdda>>16)>>3)*4),
                  '\tIDDA:',(((val_idda>>16)-(val_idda>>31)*65535)*500*0.01),
                  '\tVDDD:',(((val_vddd>>16)>>3)*4),
                  '\tIDDD:',(((val_iddd>>16)-(val_iddd>>31)*65535)*500*0.01),
              )

    if pacman_version=='v1rev2':
        mask=c.io.enable_tile()[1]; print('Tile enabled? ',hex(mask))
        
        # !!!!! for single chip testboard, use vdda, vddd 0xd2cd
        vddd=0xd8e4 # for 100 chip tile w/ O(1m) cable
        vdda=0xd8e4 # for 100 chip tile w/ O(1m) cable
        c.io.set_vddd(vddd)[1]
        c.io.set_vdda(vdda)[1]

        vddd,iddd = c.io.get_vddd()[1]
        vdda,idda = c.io.get_vdda()[1]
        print('VDDD: ',vddd,' mV\t IDDD: ',iddd,' mA\nVDDA: ',vdda,' mV\t IDDA: ',idda,' mA')
        for ch in range(1,5): c.io.set_reg(0x1000*ch + 0x2014, 0)

    
    if logger:
        print('logger enabled')
        if 'filename' in kwargs: c.logger = larpix.logger.HDF5Logger(filename=kwargs['filename'])
        else: c.logger = larpix.logger.HDF5Logger()
        print('filename:',c.logger.filename)
        c.logger.record_configs(list(c.chips.values()))


    ##### issue hard reset (resets state machines and configuration memory)
    if reset:
        c.io.reset_larpix(length=10240)
        # resets uart speeds on fpga
        for io_group, io_channels in c.network.items():
            for io_channel in io_channels:
                c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group)

                
    ##### initialize network
    c.io.group_packets_by_io_group = False # throttle the data rate to insure no FIFO collisions
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            c.init_network(io_group, io_channel, modify_mosi=False)

            
    ###### set uart speed (v2a at 2.5 MHz transmit clock, v2b fine at 5 MHz transmit clock)
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            chip_keys = c.get_network_keys(io_group,io_channel,root_first_traversal=False)
            for chip_key in chip_keys:
                c[chip_key].config.clk_ctrl = _default_clk_ctrl
                c.write_configuration(chip_key, 'clk_ctrl')

    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[_default_clk_ctrl], io_group=io_group)
            #print('io_channel:',io_channel,'factor:',c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[_default_clk_ctrl], io_group=io_group))


    ##### issue soft reset (resets state machines, configuration memory untouched)
    c.io.reset_larpix(length=24)


    ##### setup low-level registers to enable loopback
    print('set base configuration: Vref DAC, Vcm DAC, ADC hold delay, MISO differential')
    chip_config_pairs=[]
    for chip_key, chip in reversed(c.chips.items()):
        initial_config = deepcopy(chip.config)
        c[chip_key].config.vref_dac = 185 # register 82
        c[chip_key].config.vcm_dac = 41 # register 83
        c[chip_key].config.adc_hold_delay = 15 # register 129
        c[chip_key].config.enable_miso_differential = [1,1,1,1] # register 125
        chip_config_pairs.append((chip_key,initial_config))
    c.io.double_send_packets = True
    c.io.gruop_packets_by_io_group = True
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    flush_data(c)

    if not enforce: 
        if hasattr(c,'logger') and c.logger: c.logger.record_configs(list(c.chips.values()))
        print('[FINISH BASE]')
        return c

    for chip_key in c.chips:
        chip_registers = [(chip_key, i) for i in [82,83,125,129]]
        ok,diff = c.enforce_registers(chip_registers, timeout=0.01, n=10, n_verify=10)
        if not ok:
            raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))
    c.io.double_send_packets = False
    c.io.gruop_packets_by_io_group = False
    print('base configuration successfully enforced')
    
    if hasattr(c,'logger') and c.logger: c.logger.record_configs(list(c.chips.values()))
    print('[FINISH BASE]')
    return c


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--pacman_version', default=_default_pacman_version, type=str, help='''Pacman version in use''')
    parser.add_argument('--logger', default=_default_logger, action='store_true', help='''Flag to create an HDF5Logger object to track data''')
    parser.add_argument('--no_reset', default=_default_reset, action='store_false', help='''Flag that if present, chips will NOT be reset, otherwise chips will be reset during initialization''')
    args = parser.parse_args()
    c = main(**vars(args))


