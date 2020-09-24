import sys
import time

import larpix
import larpix.io
import larpix.logger

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
        if len(controller.reads[-1])/runtime < rate_limit:
            break
        
def main(controller_config_file=None, logger=False, reset=True):
    print('base config')

    # create controller
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)

    # set larpix power voltages (pacman only)
    print('Setting larpix power...')
    #c.io.set_vddd()[1] # default (VDDD~1.8V)
    c.io.set_vddd(vddd_dac=0xb620)[1] # default (VDDD~1.2V)        
    #c.io.set_vddd(vddd_dac=0xbbd0)[1] # mid-power (VDDD~1.6V)
    #c.io.set_vddd(vddd_dac=0x95a3)[1] # low-power (VDDD~1.3V)
    #c.io.set_vddd(vddd_dac=0x9498)[1] # low-power (VDDD~1.285V)

    #c.io.set_vddd(vddd_dac=0xdee4)[1] 
    
    #c.io.set_vdda()[1]
    c.io.set_vdda(vdda_dac=0xeee4)[1]    
    mask = c.io.enable_tile()[1]
    print('tile enabled?:',hex(mask))
    vddd,iddd = c.io.get_vddd()[1]
    vdda,idda = c.io.get_vdda()[1] 
    print('VDDD:',vddd,'mV')
    print('IDDD:',iddd,'mA')
    print('VDDA:',vdda,'mV')
    print('IDDA:',idda,'mA')
    phase = 0
    for ch in range(1,5):
        c.io.set_reg(0x1000*ch + 0x2014, phase)
    print('set phase:',phase)
    
    if logger:
        print('logger')
        c.logger = larpix.logger.HDF5Logger()
        print('filename:',c.logger.filename)
        c.logger.disable()

    if controller_config_file is None:
        channel = 1 # fpga channel
        chip_id = 2
        #c.add_chip(larpix.Key(1,channel,1))
        c.add_chip(larpix.Key(1,channel,chip_id))
        # create node for fpga
        c.add_network_node(1,channel,c.network_names, 'ext', root=True)
        # create upstream link for fpga
        #c.add_network_link(1,channel,'miso_us',('ext',1),1)
        c.add_network_link(1,channel,'miso_us',('ext',chip_id),0)
        # create downstream link on miso_0
        #c.add_network_link(1,channel,'miso_ds',(1,'ext'),1)
        c.add_network_link(1,channel,'miso_ds',(chip_id,'ext'),0)
        # create mosi link on mosi_1
        #c.add_network_link(1,channel,'mosi',('ext',1),1)
        c.add_network_link(1,channel,'mosi',('ext',chip_id),0)

    else:
        c.load(controller_config_file)

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
            c.init_network(io_group, io_channel)
    
    # set uart speed
    clk_ctrl = 1
    print('set uart speed and diff signaling...')
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            chip_keys = c.get_network_keys(io_group,io_channel,root_first_traversal=False)
            for chip_key in chip_keys:
                print('set',chip_key)
                c[chip_key].config.clk_ctrl = clk_ctrl
                c.write_configuration(chip_key, 'clk_ctrl')
    for io_group, io_channels in c.network.items():
        for io_channel in io_channels:
            print(io_channel, c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[clk_ctrl], io_group=io_group))

    # set other configuration registers
    for chip_key in c.chips:
        registers = []
        register_map = c[chip_key].config.register_map

        c[chip_key].config.csa_gain = 0 # high gain
        #c[chip_key].config.csa_gain = 1 # low gain        
        registers += list(register_map['csa_gain'])
        c[chip_key].config.adc_hold_delay = 15
        registers += list(register_map['adc_hold_delay'])
        c[chip_key].config.enable_miso_differential = [1,1,1,1]
        registers += list(register_map['enable_miso_differential'])

        c.write_configuration(chip_key, registers)

    # verify
    ok,diff = c.verify_configuration(timeout=1)
    for chip_key in diff:
        c.write_configuration(chip_key, diff[chip_key].keys())
    ok,diff = c.verify_configuration(timeout=1)
    if not ok:
        for key in diff:
            print('config error',key,diff[key])
    c.io.group_packets_by_io_group = True
    return c

if __name__ == '__main__':
    c = main(*sys.argv[1:])
