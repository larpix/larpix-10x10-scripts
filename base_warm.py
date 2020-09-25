import sys

import larpix
import larpix.io
import larpix.logger

import base

def main(*args, **kwargs):
    print('base warm config')

    # create controller
    c = base.main(*args, **kwargs)
    c.io.group_packets_by_io_group = False

    # set configuration
    c.io.double_send_packets = True
    for chip_key, chip in c.chips.items():
        chip.config.ibias_buffer = 3
        #chip.config.ibias_buffer = 15 # non-default
        chip.config.ibias_tdac = 7
        #chip.config.ibias_tdac = 15 # non-default
        chip.config.ibias_comp = 1
        chip.config.ibias_csa = 15
        #chip.config.ibias_csa = 1 # non-default

        chip.config.ref_current_trim = 15
        #chip.config.ref_current_trim = 0

        chip.config.vref_dac = 185
        chip.config.vcm_dac = 41
        #chip.config.vref_dac = 145 # non-default
        #chip.config.vcm_dac = 1 # non-default

        chip.config.enable_hit_veto = 1
        c.write_configuration(chip_key, 'enable_hit_veto')

        # write configuration
        registers = [74, 75, 76, 77] # ibias
        registers += [81] # ref current
        registers += [82, 83] # vXX_dac

        c.write_configuration(chip_key, registers)

    # verify
    #for chip_key in c.chips:
    #    ok, diff = c.verify_configuration(chip_key,timeout=0.01)
    #    for chip_key in diff:
    #        c.write_configuration(chip_key, diff[chip_key])
    c.io.double_send_packets = False    

    return c

if __name__ == '__main__':
    c = main(*sys.argv[1:])
