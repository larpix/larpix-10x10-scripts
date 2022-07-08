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

_default_filename=None
_default_geometry_yaml='layout-2.4.0.yaml'
_default_title=None
_default_metric='mean'

pitch=4.4 # mm



def unique_channel_id(d): return((d['io_group'].astype(int)*256+d['io_channel'].astype(int))*256 + d['chi\
p_id'].astype(int))*64 + d['channel_id'].astype(int)



def parse_file(filename):
    d = dict()
    f = h5py.File(filename,'r')
    data_mask = f['packets'][:]['packet_type']==0
    valid_parity_mask = f['packets'][:]['valid_parity']==1
    mask = np.logical_and(data_mask, valid_parity_mask)
    adc = f['packets']['dataword'][mask]
    unique_id = unique_channel_id(f['packets'][mask])
    unique_id_set = np.unique(unique_id)
    for i in unique_id_set:
        id_mask = unique_id == i
        masked_adc = adc[id_mask]
        d[i]=dict(
            mean = np.mean(masked_adc),
            std = np.std(masked_adc),
            rate = len(masked_adc) )
    return d



def find_channel_id(u): return u % 64



def find_chip_id(u): return (u//64) % 256



def plot_1d(d, metric, title):
    fig, ax = plt.subplots(figsize=(8,8))
    a = [d[key][metric] for key in d.keys()]
    min_bin = int(min(a))-1
    max_bin = int(max(a))+1
    n_bins = max_bin-min_bin
    ax.hist(a, bins=np.linspace(min_bin, max_bin, n_bins))
    ax.grid(True)
    if metric=='mean': ax.set_xlabel('ADC Mean')
    if metric=='std': ax.set_xlabel('ADC RMS')
    if metric=='rate': ax.set_xlabel('Trigger Rate')
    ax.set_ylabel('Channel Count')
    ax.set_title(title)
    plt.show()




def plot_xy(d, metric, title, geometry_yaml, normalization):
    with open(geometry_yaml) as fi: geo = yaml.full_load(fi)
    chip_pix = dict([(chip_id, pix) for chip_id,pix in geo['chips']])
    vertical_lines=np.linspace(-1*(geo['width']/2), geo['width']/2, 11)
    horizontal_lines=np.linspace(-1*(geo['height']/2), geo['height']/2, 11)

    nonrouted_v2a_channels=[6,7,8,9,22,23,24,25,38,39,40,54,55,56,57]
    routed_v2a_channels=[i for i in range(64) if i not in nonrouted_v2a_channels]
    
    fig, ax = plt.subplots(figsize=(10,8))
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

    for key in d.keys():
        channel_id = find_channel_id(key)
        chip_id = find_chip_id(key)
        if chip_id not in range(11,111): continue
        if channel_id in nonrouted_v2a_channels: continue
        if channel_id not in range(64): continue
        x = geo['pixels'][chip_pix[chip_id][channel_id]][1]
        y = geo['pixels'][chip_pix[chip_id][channel_id]][2]
        weight = d[key][metric]/normalization
        if weight>1.0: weight=1.0
        r = Rectangle( ( x-(pitch/2.), y-(pitch/2.) ), pitch, pitch, color='k', alpha=weight )
        plt.gca().add_patch( r )

    fig.colorbar(cm.ScalarMappable(norm=Normalize(vmin=0, vmax=normalization), cmap='Greys'), ax=ax)

    if metric=='mean': ax.set_title(title+'\nADC Mean')
    if metric=='std': ax.set_title(title+'\nADC RMS')
    if metric=='rate': ax.set_title(title+'\nTrigger Rate')
    plt.show()


    
def main(filename=_default_filename,
         geometry_yaml=_default_geometry_yaml,
         title=_default_title,
         metric=_default_metric,
         **kwargs):

    d = parse_file( filename )

    normalization=50
    if metric=='std': normalization=5
    if metric=='rate': normalization=10
    plot_xy(d, metric, title, geometry_yaml, normalization)

    plot_1d(d, metric, title)


    
if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--filename', default=_default_filename, type=str, help='''HDF5 fielname''')
    parser.add_argument('--geometry_yaml', default=_default_geometry_yaml, type=str, help='''geometry yaml file (layout 2.4.0 for LArPix-v2a 10x10 tile)''')
    parser.add_argument('--title', default=_default_title, type=str, help='''plot title''')
    parser.add_argument('--metric', default=_default_metric, type=str, help='''metric to plot; options: 'mean', 'std', 'rate' ''')
    args = parser.parse_args()
    main(**vars(args))
