import sys
import time
import argparse

import larpix
import larpix.io
import larpix.logger

#_vddd_dac = 0xd2cd # for ~1.8V operation on single chip testboard
#_vdda_dac = 0xd2cd # for ~1.8V operation on single chip testboard
_vddd_dac = 0xd8e4 # for ~1.8V operation on 10x10 tile
_vdda_dac = 0xd8e4 # for ~1.8V operation on 10x10 tile
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

def flush_data(controller, runtime=0.1, rate_limit=0., max_iterations=10):
    '''
    Continues to read data until data rate is less than rate_limit

    '''
    for _ in range(max_iterations):
        controller.run(runtime, 'flush_data')
        if len(controller.reads[-1])/runtime <= rate_limit:
            break

def main(controller_config=_default_controller_config, logger=_default_logger, reset=_default_reset, **kwargs):
    print('START BASE')

    # create controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)

    # set larpix power voltages (pacman only)
    print('Setting larpix power...')
    mask = c.io.enable_tile()[1]
    print('tile enabled?:',hex(mask))
    c.io.set_vddd(_vddd_dac)[1]
    c.io.set_vdda(_vdda_dac)[1]
    vddd,iddd = c.io.get_vddd()[1]
    vdda,idda = c.io.get_vdda()[1]
    print('VDDD:',vddd,'mV')
    print('IDDD:',iddd,'mA')
    print('VDDA:',vdda,'mV')
    print('IDDA:',idda,'mA')
    for ch in range(1,5):
        c.io.set_reg(0x1000*ch + 0x2014, _uart_phase)
    print('set phase:',_uart_phase)

    if logger:
        print('logger')
        c.logger = larpix.logger.HDF5Logger()
        print('filename:',c.logger.filename)
        c.logger.enable()

    if controller_config is None:
        c.add_chip(larpix.Key(1, _default_io_channel, _default_chip_id))
        c.add_network_node(1, _default_io_channel, c.network_names, 'ext', root=True)
        c.add_network_link(1, _default_io_channel, 'miso_us', ('ext',_default_chip_id), 0)
        c.add_network_link(1, _default_io_channel, 'miso_ds', (_default_chip_id,'ext'), _default_miso_ds)
        c.add_network_link(1, _default_io_channel, 'mosi', ('ext', _default_chip_id), _default_mosi)

    else:
        c.load(controller_config)

    if reset:
        # issues hard reset to larpix
        print('resetting larpix...')
        c.io.reset_larpix(length=10240)
        # resets uart speeds on fpga
        for io_group, io_channels in c.network.items():
            for io_channel in io_channels:
                print('reset uart speed on channel',io_channel,'...')
                c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group)

    # initialize network
    c.io.group_packets_by_io_group = False # throttle the data rate to insure no FIFO collisions
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            print('init network {}-{}'.format(io_group,io_channel))
            c.init_network(io_group, io_channel, modify_mosi=False)

    # set uart speed
    print('set uart speed and diff signaling...')
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            chip_keys = c.get_network_keys(io_group,io_channel,root_first_traversal=False)
            for chip_key in chip_keys:
                c[chip_key].config.clk_ctrl = _default_clk_ctrl
                c.write_configuration(chip_key, 'clk_ctrl')
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            print('io_channel:',io_channel,'factor:',c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[_default_clk_ctrl], io_group=io_group))

    # set any other configuration registers
    for chip_key in c.chips:
        registers = []
        register_map = c[chip_key].config.register_map

        c[chip_key].config.vref_dac = 185
        registers += list(register_map['vref_dac'])
        registers += list(register_map['vcm_dac'])
        c[chip_key].config.vcm_dac = 41
        c[chip_key].config.csa_gain = 0 # high gain
        #c[chip_key].config.csa_gain = 1 # low gain
        registers += list(register_map['csa_gain'])
        c[chip_key].config.adc_hold_delay = 15
        registers += list(register_map['adc_hold_delay'])
        c[chip_key].config.enable_miso_differential = [1,1,1,1]
        registers += list(register_map['enable_miso_differential'])

        c.write_configuration(chip_key, registers)

    # verify
    c.io.double_send_packets = True
    for chip_key in c.chips:
        ok,diff = c.enforce_registers([(chip_key,0)],timeout=0.01, n=10, n_verify=10)
        if not ok:
            for key in diff:
                print('config error',key,diff[key])
    c.io.double_send_packets = False
    #c.io.group_packets_by_io_group = True

    if hasattr(c,'logger') and c.logger:
        c.logger.record_configs(list(c.chips.values()))

    print('END BASE')
    return c

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller_config', default=_default_controller_config, type=str, help='''Hydra network configuration file''')
    parser.add_argument('--logger', default=_default_logger, action='store_true', help='''Flag to create an HDF5Logger object to track data''')
    parser.add_argument('--no_reset', default=_default_reset, action='store_false', help='''Flag that if present, chips will NOT be reset, otherwise chips will be reset during initialization''')
    args = parser.parse_args()
    c = main(**vars(args))

