#!/usr/bin/env python3

import argparse
from copy import deepcopy

import larpix
import larpix.io
import larpix.logger
import numpy as np
import time


_default_pacman_tile=1
_default_io_group=1

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

power_val=dict()
power_val[1]=0b00000001
power_val[2]=0b00000010
power_val[3]=0b00000100
power_val[4]=0b00001000
power_val[5]=0b00010000
power_val[6]=0b00100000
power_val[7]=0b01000000
power_val[8]=0b10000000



def set_pacman_power(io, io_group, tile, vdda=46020, vddd=40605):
    io.set_reg(vdda_reg[tile], vdda, io_group=io_group)
    io.set_reg(vddd_reg[tile], vddd, io_group=io_group)
    io.set_reg(0x00000014, 1, io_group=io_group) # enable global larpix power
    io.set_reg(0x00000010, power_val[tile], io_group=io_group) # enable tiles to be powered
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



def report_power(io, io_group, tile):
    power = power_registers()
    adc_read = 0x00024001
    val_vdda = io.get_reg(adc_read+power[tile][0], io_group=io_group)
    val_idda = io.get_reg(adc_read+power[tile][1], io_group=io_group)
    val_vddd = io.get_reg(adc_read+power[tile][2], io_group=io_group)
    val_iddd = io.get_reg(adc_read+power[tile][3], io_group=io_group)
    print('TILE',tile,
          '\tVDDA:',(((val_vdda>>16)>>3)*4),'mV',
          '\tIDDA:',(((val_idda>>16)-(val_idda>>31)*65535)*500*0.01),'mA'
          '\tVDDD:',(((val_vddd>>16)>>3)*4),'mV'
          '\tIDDD:',(((val_iddd>>16)-(val_iddd>>31)*65535)*500*0.01),'mA'
    )


    
def main(io_group=_default_io_group,
         pacman_tile=_default_pacman_tile,
         **kwargs):

    ###### create controller with pacman io
    c = larpix.Controller()
    c.io = larpix.io.PACMAN_IO(relaxed=True)
    
    ###### set power to tile    
    set_pacman_power(c.io, io_group, pacman_tile)
    report_power(c.io, io_group, pacman_tile)

    ###### disable tile power
    c.io.set_reg(0x00000010, 0, io_group=io_group)
    
    return c



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--io_group', default=_default_io_group, type=int, help='''IO group ''')
    parser.add_argument('--pacman_tile', default=_default_pacman_tile, type=int, help='''PACMAN tile ''')
    args = parser.parse_args()
    c = main(**vars(args))


