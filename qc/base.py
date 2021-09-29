#!/usr/bin/env python3

import argparse
from copy import deepcopy

import larpix
import larpix.io
import larpix.logger


_uart_phase = 0

_default_controller_config=None
_default_logger=False
_default_reset=True

_default_chip_id = 2
_default_io_channel = 1
_default_miso_ds = 0
_default_mosi = 0
_default_clk_ctrl = 1
clk_ctrl_2_clk_ratio_map = {
        0: 2,
        1: 4,
        2: 8,
        3: 16
        }

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
    '''
    Continues to read data until data rate is less than rate_limit

    '''
    for _ in range(max_iterations):
        controller.run(runtime, 'flush_data')
        if len(controller.reads[-1])/runtime <= rate_limit:
            break

def main(controller_config=_default_controller_config, logger=_default_logger, reset=_default_reset, **kwargs):

    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)
    print('testing',controller_config)
    vddd = 40605 #42635
    c.io.set_reg(0x00024130, 46020) # write to tile 1 VDDA
    c.io.set_reg(0x00024131, vddd) # write to tile 1 VDDD
    c.io.set_reg(0x00024132, 46020) # write to tile 2 VDDA
    c.io.set_reg(0x00024133, vddd) # write to tile 2 VDDD
    c.io.set_reg(0x00024134, 46020) # write to tile 3 VDDA
    c.io.set_reg(0x00024135, vddd) # write to tile 3 VDDD
    c.io.set_reg(0x00024136, 46020) # write to tile 4 VDDA
    c.io.set_reg(0x00024137, vddd) # write to tile 4 VDDD
    c.io.set_reg(0x00024138, 46020) # write to tile 5 VDDA
    c.io.set_reg(0x00024139, vddd) # write to tile 5 VDDD
    c.io.set_reg(0x0002413a, 46020) # write to tile 6 VDDA
    c.io.set_reg(0x0002413b, vddd) # write to tile 6 VDDD
    c.io.set_reg(0x0002413c, 46020) # write to tile 7 VDDA
    c.io.set_reg(0x0002413d, vddd) # write to tile 7 VDDD
    c.io.set_reg(0x0002413e, 46020) # write to tile 8 VDDA
    c.io.set_reg(0x0002413f, vddd) # write to tile 8 VDDD
    c.io.set_reg(0x00000014, 1) # enable global larpix power
    c.io.set_reg(0x00000010, 0b00000001) # enable tiles to be powered

    power = power_registers()
    adc_read = 0x00024001
    for i in power.keys():
        print(i)
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

    if logger:
        print('logger')
        if 'filename' in kwargs:
            c.logger = larpix.logger.HDF5Logger(filename=kwargs['filename'])
        else:
           c.logger = larpix.logger.HDF5Logger()
        print('filename:',c.logger.filename)
        c.logger.record_configs(list(c.chips.values()))

    if controller_config is None:
        c.add_chip(larpix.Key(1, _default_io_channel, _default_chip_id))
        c.add_network_node(1, _default_io_channel, c.network_names, 'ext', root=True)
        c.add_network_link(1, _default_io_channel, 'miso_us', ('ext',_default_chip_id), 0)
        c.add_network_link(1, _default_io_channel, 'miso_ds', (_default_chip_id,'ext'), _default_miso_ds)
        c.add_network_link(1, _default_io_channel, 'mosi', ('ext', _default_chip_id), _default_mosi)

    else:
        c.load(controller_config)

    if reset:
        c.io.reset_larpix(length=10240)
        # resets uart speeds on fpga
        for io_group, io_channels in c.network.items():
            for io_channel in io_channels:
                c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group)

    # initialize network
    c.io.group_packets_by_io_group = False # throttle the data rate to insure no FIFO collisions
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            c.init_network(io_group, io_channel, modify_mosi=False)

    # set uart speed
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            chip_keys = c.get_network_keys(io_group,io_channel,root_first_traversal=False)
            for chip_key in chip_keys:
                c[chip_key].config.clk_ctrl = _default_clk_ctrl
                c.write_configuration(chip_key, 'clk_ctrl')

    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            print('io_channel:',io_channel,'factor:',c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[_default_clk_ctrl], io_group=io_group))

    c.io.reset_larpix(length=24)

    print('set configuration')
    chip_config_pairs=[]
    for chip_key, chip in reversed(c.chips.items()):
        initial_config = deepcopy(chip.config)
        c[chip_key].config.vref_dac = 185
        c[chip_key].config.vcm_dac = 41
        c[chip_key].config.adc_hold_delay = 15
        c[chip_key].config.enable_miso_differential = [1,1,1,1]
        chip_config_pairs.append((chip_key,initial_config))

    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    chip_register_pairs = c.differential_write_configuration(chip_config_pairs, write_read=0, connection_delay=0.01)
    print('differential write --> complete')
    flush_data(c)
    print('data flush --> complete')

    #c.io.double_send_packets = True
    #ok,diff = c.enforce_configuration(list(c.chips.keys()), timeout=0.01, connection_delay=0.01, n=10, n_verify=10)
    #if not ok:
    #    raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))
    for chip_key in c.chips:
        ok,diff = c.enforce_registers([(chip_key,0)], timeout=0.01, n=10, n_verify=10)
        if not ok:
            raise RuntimeError(diff,'\nconfig error on chips',list(diff.keys()))
    c.io.double_send_packets = False
    print('configuration enforce --> complete')

    if hasattr(c,'logger') and c.logger:
        c.logger.record_configs(list(c.chips.values()))

    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--logger', default=_default_logger, action='store_true', help='''Flag to create an HDF5Logger object to track data''')
    parser.add_argument('--no_reset', default=_default_reset, action='store_false', help='''Flag that if present, chips will NOT be reset, otherwise chips will be reset during initialization''')
    args = parser.parse_args()
    c = main(**vars(args))


