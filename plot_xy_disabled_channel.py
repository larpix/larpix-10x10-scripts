import h5py
import matplotlib.pyplot as plt
import yaml
import numpy as np
import argparse
import json
from matplotlib.patches import Rectangle
from matplotlib.collections import PatchCollection
from matplotlib import cm
from matplotlib.colors import Normalize

_default_trigger_disabled=None
_default_pedestal_disabled=None
_default_title=None
_default_geometry_yaml='layout-2.4.0.yaml'

pitch=4.4 # mm



def parse_file(filename):
    d = {}
    with open(filename,'r') as f:
        data = json.load(f)
        for key in data.keys():
            chip_id = int(key.split('-')[-1])
            if chip_id not in d: d[chip_id] = []
            for i in data[key]: d[chip_id].append(i)
    return d


    
def plot_xy(trigger, pedestal, title, geometry_yaml):
    with open(geometry_yaml) as fi: geo = yaml.full_load(fi)
    chip_pix = dict([(chip_id, pix) for chip_id,pix in geo['chips']])
    vertical_lines=np.linspace(-1*(geo['width']/2), geo['width']/2, 11)
    horizontal_lines=np.linspace(-1*(geo['height']/2), geo['height']/2, 11)

    nonrouted_v2a_channels=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57]
    routed_v2a_channels=[i for i in range(64) if i not in nonrouted_v2a_channels]
    
    fig, ax = plt.subplots(figsize=(8,8))
    ax.set_xlabel('X Position [mm]'); ax.set_ylabel('Y Position [mm]')
    ax.set_xticks(vertical_lines); ax.set_yticks(horizontal_lines)
    ax.set_xlim(vertical_lines[0]*1.1, vertical_lines[-1]*1.1)
    ax.set_ylim(horizontal_lines[0]*1.1, horizontal_lines[-1]*1.1)
    for vl in vertical_lines:
        ax.vlines(x=vl, ymin=horizontal_lines[0], ymax=horizontal_lines[-1], colors=['k'], linestyle='dotted')
    for hl in horizontal_lines:
        ax.hlines(y=hl, xmin=vertical_lines[0], xmax=vertical_lines[-1], colors=['k'], linestyle='dotted')

    chipid_pos = dict()
    for chipid in chip_pix.keys():
        x,y = [[] for i in range(2)]
        for channelid in routed_v2a_channels:
            x.append( geo['pixels'][chip_pix[chipid][channelid]][1] )
            y.append( geo['pixels'][chip_pix[chipid][channelid]][2] )
        avgX = (max(x)+min(x))/2.
        avgY = (max(y)+min(y))/2.
        chipid_pos[chipid]=dict(minX=min(x), maxX=max(x), avgX=avgX, minY=min(y), maxY=max(y), avgY=avgY)
        plt.annotate(str(chipid), [avgX,avgY], ha='center', va='center')

    trigger_count=0
    for key in trigger.keys():
        chip_id = key
        if chip_id not in range(11,111): continue
        for channel_id in trigger[key]:
            if channel_id in nonrouted_v2a_channels: continue
            if channel_id not in range(64): continue
            trigger_count+=1
            x = geo['pixels'][chip_pix[chip_id][channel_id]][1]
            y = geo['pixels'][chip_pix[chip_id][channel_id]][2]
            weight = 1.0
            r = Rectangle( ( x-(pitch/2.), y-(pitch/2.) ), pitch, pitch, color='r', alpha=weight )
            plt.gca().add_patch( r )

    pedestal_count=0
    for key in pedestal.keys():
        chip_id = int(key)
        if chip_id not in range(11,111): continue
        for channel_id in trigger[key]:
            if channel_id in nonrouted_v2a_channels: continue
            if channel_id not in range(64): continue
            pedestal_count+=1
            x = geo['pixels'][chip_pix[chip_id][channel_id]][1]
            y = geo['pixels'][chip_pix[chip_id][channel_id]][2]
            weight = 1.0
            r = Rectangle( ( x-(pitch/2.), y-(pitch/2.) ), pitch, pitch, color='orange', alpha=weight )
            plt.gca().add_patch( r )

    ax.set_title(title)
    if trigger_count!=0 and pedestal_count==0:
        ax.set_title(title+'\n'+str(trigger_count)+' trigger rate disabled channels (red)')
    if trigger_count==0 and pedestal_count!=0:
        ax.set_title(title+'\n'+str(pedestal_count)+' pedestal disabled channels (orange)')
    if trigger_count!=0 and pedestal_count!=0:
        ax.set_title(title+'\n'+str(trigger_count)+' trigger rate disabled channels (red)'+'\n'+str(pedestal_count)+' pedestal disabled channels (orange)')
    plt.show()


    
def refine_dict(trigger, pedestal):
    result={}
    for key in pedestal.keys():
        for channel in pedestal[key]:
            if key in trigger:
                if channel in trigger[key]: continue
                else:
                    if key not in result: result[key]=[]
                    result[key].append(channel)
    return result


    
def main(trigger_disabled=_default_trigger_disabled,
         pedestal_disabled=_default_pedestal_disabled,
         geometry_yaml=_default_geometry_yaml,
         title=_default_title,
         **kwargs):

    trigger_dict={}
    if trigger_disabled!=None: trigger_dict = parse_file(trigger_disabled)

    pedestal_dict={}
    if pedestal_disabled!=None: pedestal_dict = parse_file(pedestal_disabled)

    if trigger_disabled!=None and pedestal_disabled!=None: pedestal_dict = refine_dict(trigger_dict, pedestal_dict)
    plot_xy(trigger_dict, pedestal_dict, title, geometry_yaml)


    
if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trigger_disabled', default=_default_trigger_disabled, type=str, help='''Disabled list from multi_threshold_qc script''')
    parser.add_argument('--pedestal_disabled', default=_default_pedestal_disabled, type=str, help='''Disabled list from pedestal_qc script''')
    parser.add_argument('--geometry_yaml', default=_default_geometry_yaml, type=str, help='''geometry yaml file (layout 2.4.0 for LArPix-2a 10x10 tile)''')
    parser.add_argument('--title', default=_default_title, type=str, help='''plot title''')
    args = parser.parse_args()
    main(**vars(args))
