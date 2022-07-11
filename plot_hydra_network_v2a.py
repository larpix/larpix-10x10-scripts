import matplotlib.pyplot as plt
import yaml
import numpy as np
import argparse
import json
from matplotlib.patches import Rectangle
from matplotlib.collections import PatchCollection

_default_network_json=None
_default_io_group=1
_default_geometry_yaml='layout-2.4.0.yaml'



def parse_hydra_network(network_json, iog):
    chipID_uart, missingIO=[{} for i in range(2)]
    with open(network_json,'r') as f:
        data = json.load(f)
        missingIO=data['bad_uart_links']                    
        mapping=data['network']['miso_us_uart_map']
        hydra=data['network'][str(iog)]
        for ioc in hydra:
            for node in hydra[ioc]["nodes"]:
                chipID_uart[node['chip_id']]=[]
                for i in range(len(node['miso_us'])):
                    if node['miso_us'][i]!=None: chipID_uart[node['chip_id']].append(mapping[i])
    return chipID_uart, missingIO



def start_end(chipID, uart, chipid_pos):
    dX = chipid_pos[chipID]['maxX']-chipid_pos[chipID]['avgX']
    dY = chipid_pos[chipID]['maxY']-chipid_pos[chipID]['avgY']
    
    if uart==2:
        start=( chipid_pos[chipID]['avgX']+(dX/2), chipid_pos[chipID]['avgY'] )
        end=( dX, 0)
    if uart==0:
        start=( chipid_pos[chipID]['avgX']-(dX/2), chipid_pos[chipID]['avgY'] )
        end=( dX*-1, 0)
    if uart==3:
        start=( chipid_pos[chipID]['avgX'], chipid_pos[chipID]['avgY']+(dY/2) )
        end=(0, dY)
    if uart==1:
        start=( chipid_pos[chipID]['avgX'], chipid_pos[chipID]['avgY']-(dY/2) )
        end=( 0, dY*-1)
    return start, end



def plot_hydra_network(geometry_yaml, chipID_uart, missingIO, tile_id, pacman_tile, io_group):
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

    for chipID in chipID_uart.keys():
        if chipID=='ext': continue
        for uart in chipID_uart[chipID]:
            start, end = start_end(int(chipID), uart, chipid_pos)
            plt.arrow( start[0], start[1], end[0], end[1], width=1.0, color='g')

    for i in range(len(missingIO)):
        chipIDpair=missingIO[i]
        A = chipIDpair[0]; B = chipIDpair[1]
        if A>B: A = chipIDpair[1]; B = chipIDpair[0]
        r = Rectangle( (chipid_pos[A]['maxX'],chipid_pos[A]['minY']),
                       abs(chipid_pos[A]['maxX']-chipid_pos[B]['minX']),
                       abs(chipid_pos[A]['maxY']-chipid_pos[A]['minY']),
                       color='r', alpha=0.8)
        if abs(A-B)==10:
            r = Rectangle( (chipid_pos[A]['minX'],chipid_pos[A]['minY']),
                           abs(chipid_pos[A]['maxX']-chipid_pos[A]['minX']),
                           abs(chipid_pos[A]['minY']-chipid_pos[B]['maxY'])*-1,
                           color='r', alpha=0.8)
        plt.gca().add_patch( r ) 

    for chipID in chipid_pos.keys():
        if chipID not in chipID_uart.keys():
            r = Rectangle( (chipid_pos[chipID]['minX'],chipid_pos[chipID]['minY']),
                           abs(chipid_pos[chipID]['maxX']-chipid_pos[chipID]['minX']),
                           abs(chipid_pos[chipID]['maxY']-chipid_pos[chipID]['minY']),
                           color='r', alpha=0.2)
            plt.gca().add_patch( r )

    plt.title('Tile ID '+str(tile_id)+'\n (PACMAN tile '+str(pacman_tile)+', IO group '+str(io_group)+')')
    plt.savefig('hydra-network-tile-id-'+str(tile_id)+'.png')


    
def main(network_json=_default_network_json, geometry_yaml=_default_geometry_yaml, io_group=_default_io_group, **kwargs):
    if network_json==None:
        print('Hydra network JSON configuration file missing.\n',
              '==> Specify with --network_json <filename> commandline argument')
        return
    tile_id = network_json.split('-')[2]
    pacman_tile = network_json.split('-')[5]
    
    chipID_uart, missingIO = parse_hydra_network(network_json, io_group)
    plot_hydra_network(geometry_yaml, chipID_uart, missingIO, tile_id, pacman_tile, io_group)


    
if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--network_json', default=_default_network_json, type=str, help='''Hydra network json configuration file''')
    parser.add_argument('--geometry_yaml', default=_default_geometry_yaml, type=str, help='''geometry yaml (layout 2.4.0 for LArPix-v2a 10x10 tile)''')
    parser.add_argument('--io_group', default=_default_io_group, type=int, help='''PACMAN IO group''')
    args = parser.parse_args()
    main(**vars(args))
