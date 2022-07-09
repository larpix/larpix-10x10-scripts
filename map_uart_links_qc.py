import sys
import time
import argparse
import graphs
import larpix
import larpix.io
import larpix.logger
import generate_config
import base
import numpy as np

from base import *

def convert_voltage_for_pacman(voltage):
	max_voltage, max_scale = 1.8, 46020
	v = voltage
	if v > max_voltage: v=max_voltage
	return int( (v/max_voltage)*max_scale )

arr = graphs.NumberedArrangement()

def get_temp_key(io_group, io_channel):
	return larpix.key.Key(io_group, io_channel, 1)

def get_good_roots(c, io_group, io_channels):
	#root chips with external connections to pacman
	root_chips = [11, 41, 71, 101]

	good_tile_channel_indices = []
	for n, io_channel in enumerate(io_channels):

		#writing initial config
		key = larpix.key.Key(io_group, io_channel, 1)
		c.add_chip(key)

		c[key].config.chip_id = root_chips[n]
		c.write_configuration(key, 'chip_id')
		c.remove_chip(key)

		key = larpix.key.Key(io_group, io_channel, root_chips[n])
		c.add_chip(key)
		c[key].config.chip_id = key.chip_id

		c[key].config.enable_miso_downstream = [1,0,0,0]
		c[key].config.enable_miso_differential = [1,1,1,1]
		c.write_configuration(key, 'enable_miso_downstream')

		###############################################################################


		#resetting clocks

		c[key].config.enable_miso_downstream=[0]*4
		c[key].config.enable_miso_upstream=[0]*4
		c.write_configuration(key, 'enable_miso_downstream')
		c.write_configuration(key, 'enable_miso_upstream')
		c[key].config.clk_ctrl = base._default_clk_ctrl
		c.write_configuration(key, 'clk_ctrl')
		c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[base._default_clk_ctrl], io_group=io_group)

		################################################################################

		#rewriting config
		c[key].config.enable_miso_downstream = [1,0,0,0]
		c[key].config.enable_miso_differential = [1,1,1,1]
		c.write_configuration(key, 'enable_miso_differential')
		c.write_configuration(key, 'enable_miso_downstream')

		#enforcing configuration on chip
		ok,diff = c.enforce_registers([(key,122), (key, 125)], timeout=0.1, n=5, n_verify=5)
		if ok:
			good_tile_channel_indices.append(n)
			print('verified root chip ' + str(root_chips[n]))
		else:
			print('unable to verify root chip ' + str(root_chips[n]))

	#checking each connection for every chip
	good_roots = [root_chips[n] for n in good_tile_channel_indices]
	good_channels = [io_channels[n] for n in good_tile_channel_indices]

	print('Found working root chips: ', good_roots)

	return good_roots, good_channels

def get_initial_controller(io_group, io_channels, vdda=0, pacman_version='v1rev3'):
	#creating controller with pacman io
	c = larpix.Controller()
	c.io = larpix.io.PACMAN_IO(relaxed=True)
	c.io.double_send_packets = True
	print('getting initial controller')
	print(pacman_version, pacman_version == 'v1rev3' )
	if pacman_version == 'v1rev3':
		print('setting power,', vdda)
		vddd_voltage = 1.6
		vddd = convert_voltage_for_pacman(vddd_voltage)
		vdda = convert_voltage_for_pacman(vdda)
		reg_pairs = get_reg_pairs(io_channels)
		for pair in reg_pairs:
			c.io.set_reg(pair[0], vdda, io_group=io_group)
			c.io.set_reg(pair[1], vddd, io_group=io_group)
		tiles = get_all_tiles(io_channels)
		bit_string = list('00000000')
		for tile in tiles: bit_string[-1*tile] = '1'
		c.io.set_reg(0x00000014, 1, io_group=io_group) # enable global larpix power
		c.io.set_reg(0x00000010, int("".join(bit_string), 2), io_group=io_group) # enable tiles to be powered

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
				  '\tIDDD:',(((val_iddd>>16)-(val_iddd>>31)*65535)*500*0.01))

	if pacman_version == 'v1rev2':
		_vddd_dac = 0xd2cd # for ~1.8V operation on single chip testboard
		_vdda_dac = 0xd2cd # for ~1.8V operation on single chip testboard
		#_vddd_dac = 0xd8e4 # for ~1.8V operation on 10x10 tile
		#_vdda_dac = 0xd8e4 # for ~1.8V operation on 10x10 tile
		_uart_phase = 0
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

	#adding pacman!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
	for io_channel in io_channels:
		c.add_network_node(io_group, io_channel, c.network_names, 'ext', root=True)
	#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

	#resetting larpix
	c.io.reset_larpix(length=10240)
	for io_channel in io_channels:
		c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group)
	###################################################################################

	return c

def reset_board_get_controller(c, io_group, io_channels):
	#resetting larpix
	c.io.reset_larpix(length=10240)
	for io_channel in io_channels:
		c.io.set_uart_clock_ratio(io_channel, clk_ctrl_2_clk_ratio_map[0], io_group=io_group)
	c.chips.clear()
	###################################################################################
	return c

def init_initial_network(c, io_group, io_channels, paths):
	root_chips = [path[0] for path in paths]

	still_stepping = [True for root in root_chips]
	ordered_chips_by_channel = [ [] for io_channel in io_channels  ]

	for ipath, path in enumerate(paths):

		step = 0

		while step < len(path)-1:
			step += 1
			next_key = larpix.key.Key(io_group, io_channels[ipath], path[step])
			prev_key = larpix.key.Key(io_group, io_channels[ipath], path[step-1])

			if prev_key.chip_id in root_chips:
				#this is the first step. need to re-add root chip
				temp_key = get_temp_key(io_group, io_channels[ipath])
				c.add_chip(temp_key)
				c[temp_key].config.chip_id = prev_key.chip_id
				c.write_configuration(temp_key, 'chip_id')
				c.remove_chip(temp_key)
				c.add_chip(prev_key)
				c[prev_key].config.chip_id = prev_key.chip_id
				c[prev_key].config.enable_miso_downstream = arr.get_uart_enable_list(prev_key.chip_id)
				c[prev_key].config.enable_miso_differential = [1,1,1,1]
				c.write_configuration(prev_key, 'enable_miso_downstream')
				c.write_configuration(prev_key, 'enable_miso_differential')
				ordered_chips_by_channel[ipath].append(prev_key.chip_id)
			
			c[prev_key].config.enable_miso_upstream = arr.get_uart_enable_list(prev_key.chip_id, next_key.chip_id)
			c.write_configuration(prev_key, 'enable_miso_upstream')

			temp_key = get_temp_key(io_group, io_channels[ipath])
			c.add_chip(temp_key)
			c[temp_key].config.chip_id = next_key.chip_id
			c.write_configuration(temp_key, 'chip_id')
			c.remove_chip(temp_key)

			c.add_chip(next_key)
			c[next_key].config.chip_id = next_key.chip_id
			c[next_key].config.enable_miso_downstream = arr.get_uart_enable_list(next_key.chip_id, prev_key.chip_id)
			c[next_key].config.enable_miso_differential =[1,1,1,1]
			c.write_configuration(next_key, 'enable_miso_downstream')
			ordered_chips_by_channel[ipath].append(next_key.chip_id)
			
		for chip_ids in ordered_chips_by_channel[ipath][::-1]:
			key = larpix.key.Key(io_group, io_channels[ipath], chip_ids)
			c[key].config.enable_miso_downstream=[0]*4
			c[key].config.enable_miso_upstream=[0]*4
			c.write_configuration(key, 'enable_miso_downstream')
			c.write_configuration(key, 'enable_miso_upstream')
			c[key].config.clk_ctrl = base._default_clk_ctrl
			c.write_configuration(key, 'clk_ctrl')
		c.io.set_uart_clock_ratio(io_channels[ipath], clk_ctrl_2_clk_ratio_map[base._default_clk_ctrl], io_group=io_group)

	return True

def test_network(c, io_group, io_channels, paths):
	root_chips = [path[0] for path in paths]
	step = 0
	still_stepping = [True for path in paths]
	valid = [True for path in paths]
	while any(still_stepping):
		step += 1

		for ipath, path in enumerate(paths):
			
			if not still_stepping[ipath] or not valid[ipath]:
				continue

			if step > len(path)-1:
				still_stepping[ipath] = False
				continue

			next_key = larpix.key.Key(io_group, io_channels[ipath], path[step])
			prev_key = larpix.key.Key(io_group, io_channels[ipath], path[step-1])

			if prev_key.chip_id in root_chips:
				c[prev_key].config.chip_id = prev_key.chip_id
				c[prev_key].config.enable_miso_downstream = arr.get_uart_enable_list(prev_key.chip_id)
				c[prev_key].config.enable_miso_differential = [1,1,1,1]
				c.write_configuration(prev_key, 'enable_miso_downstream')

			c[prev_key].config.enable_miso_upstream = arr.get_uart_enable_list(prev_key.chip_id, next_key.chip_id)
			c.write_configuration(prev_key, 'enable_miso_upstream')

			c[next_key].config.chip_id = next_key.chip_id
			c[next_key].config.enable_miso_downstream = arr.get_uart_enable_list(next_key.chip_id, prev_key.chip_id)
			c[next_key].config.enable_miso_differential =[1,1,1,1]
			c.write_configuration(next_key, 'enable_miso_downstream')

			if (path[step-1], path[step]) in arr.good_connections:
				#already verified links
				print(next_key, 'already verified')
				continue

			ok, diff = c.enforce_registers([(next_key, 122)], timeout=0.5, n=3)
			print(next_key, ok )

			if ok:
				arr.add_good_connection((path[step-1], path[step]))
				continue

			else:
				#planned path to traverse has been interrupted... restart with adding excluded link
				arr.add_onesided_excluded_link((prev_key.chip_id, next_key.chip_id))
				still_stepping[ipath] = False
				valid[ipath] = False

	return all(valid)

def test_chip(c, io_group, io_channel, path, ich, all_paths_copy, io_channels_copy, config):
	#-loop over all UARTs on current chip
	#-check if chip in that direction is in current network
	#---if in network:
	# 	shut off all current misos through existing network, 
	#   re-route through current chip using upstrean command from current chip
	#   read configuration through current chip
	# ** if we can't read the command, then either the upstream from current chip isn't working, or the
	# ** mosi on the current chip isn't working, or the downstream miso on next/current mosi bridge isnt working
	# 
	# to test:
	# - upstream on current or downstream on next:
	#----change register through current configuration
	#----disable miso upstream on current
	#----enable miso downstream on next back through og path
	#----read config through original path, verify register
	#----true: upstream miso works, downstream no
	#----false: upstream miso on current doesn't work
	#----***IF upstream miso doesn't work, we need an additional test
	#	   to make sure that the downstream miso on next works
	#	** test:
	#	   -disable miso downstream from previous path
	#	   -enable downstream miso from next to current
	#		-disbale miso us from current (for good measure, we know it doesnt work)
	#		-read register from chip
	
	chip = path[ich]
	
	#directions to 'step' away from current chip for test
	mover_directions = [arr.right, arr.left, arr.up, arr.down]

	for direction in mover_directions:
		next_chip = direction(chip)
		if next_chip <  2: #at the boundary of the board
			continue
		if ich < len(path)-1:
			if next_chip == path[ich+1]: #already know connection works, next chip in hydra network
				continue
		if next_chip == path[ich-1]: #already know connection works, previous chip in current hydra network
			continue

		if (chip, next_chip) in arr.good_connections or (chip, next_chip) in arr.excluded_links: #already tested connection when building existing hydra network
			continue

		#next chip may be in current hydra network or not. For test, we need a key with the real io channel of the chip and the 
		#current io channel of the chip under test
		real_io_channel = -1
		if next_chip in path: 
			real_io_channel = io_channel
		else:
			for _ipath, _path in enumerate(all_paths_copy):
				if next_chip in _path:
					real_io_channel = io_channels_copy[_ipath]
					break


		#---begin testing of uart---
		#base.reset(c, config)


		#TESTING DOWNSTREAM FROM CHIP---WRITE CONFIGURATION THROUGH REAL NETWORK,
		#SEND READ REQUEST THROUGH REAL NETWORK 
		#READ PACKET SENT THROUGH C.O.T.

		#enable downstream miso to current chip
		#--note--can't enforce this configuration, as we won't be able to read from the chip after.
		print('Starting test of', chip, 'to', next_chip)
		real_next_key = larpix.key.Key(io_group, real_io_channel, next_chip)
		next_ds_backup = c[real_next_key].config.enable_miso_downstream.copy()
		c[real_next_key].config.enable_miso_downstream = [0,0,0,0]
		for __ in range(10): c.write_configuration(real_next_key, 'enable_miso_downstream')

		#turn off upstream commands from previous chip in network
		real_hydra_index = io_channels_copy.index(real_io_channel)
		next_chip_index = all_paths_copy[real_hydra_index].index(next_chip)

		prev_us_backup = None
		if next_chip_index > 0:
			#get chip which is writing upstream commands to next_chip 
			prev_chip = all_paths_copy[real_hydra_index][next_chip_index-1]
			prev_key = larpix.key.Key(io_group, real_io_channel, prev_chip)
			prev_us_backup = c[prev_key].config.enable_miso_upstream
			c[prev_key].config.enable_miso_upstream = [0,0,0,0]
			ok,diff = c.enforce_registers([(prev_key, 124)], timeout=0.1, n=5, n_verify=5)

		#TEST CONFIGURATION
		test_key = larpix.key.Key(io_group, io_channel, next_chip)
		if not (real_io_channel==io_channel):
			c.add_chip(test_key)
		
		#enable current chip to write upstream commands to test chip
		curr_key = larpix.key.Key(io_group, io_channel, chip)
		curr_us_backup = c[curr_key].config.enable_miso_upstream
		c[curr_key].config.enable_miso_upstream = arr.get_uart_enable_list(chip, next_chip)
		ok,diff = c.enforce_registers([(curr_key, 124)], timeout=0.1, n=5, n_verify=5)
		if not ok: 
			print('broken')
			arr.add_onesided_excluded_link((chip, next_chip))
			arr.add_onesided_excluded_link((next_chip, chip))
			if not (real_io_channel==io_channel):
				c.remove_chip(test_key)
			base.reset(c, config)
			continue

		c[test_key].config.enable_miso_downstream = arr.get_uart_enable_list(next_chip, chip)
		ok,diff = c.enforce_registers([(test_key, 125)], timeout=0.1, n=5, n_verify=5)

		if not ok: #two-way connection between current chip and next chip is broken
			print('broken')
			arr.add_onesided_excluded_link((chip, next_chip))
			arr.add_onesided_excluded_link((next_chip, chip))
		else:
			print('verified')
			arr.add_good_connection((chip, next_chip))
			arr.add_good_connection((next_chip, chip))

		#return chips to original state
		c[test_key].config.enable_miso_downstream = next_ds_backup
		for __ in range(10): c.write_configuration(test_key, 'enable_miso_downstream')

		if not (real_io_channel==io_channel):
			c.remove_chip(test_key)

		ok1, ok2, ok3 = False, False, False

		c[curr_key].config.enable_miso_upstream = curr_us_backup
		ok1,diff = c.enforce_registers([(curr_key, 124)], timeout=0.2, n=10, n_verify=5)
		if not ok1: 
			print('****** Issue returning current chip', curr_key, 'to original config')
			print(diff)
			print('reset planned')

		if not prev_us_backup is None:
			c[prev_key].config.enable_miso_upstream = prev_us_backup
			ok2,diff = c.enforce_registers([(prev_key, 124)], timeout=0.2, n=10, n_verify=5)
			if not ok2: 
				print('****** Issue returning downstream chip', prev_key, 'to original config')
				print(diff)
				print('reset planned')

		c[real_next_key].config.enable_miso_downstream = next_ds_backup
		ok3,diff = c.enforce_registers([(real_next_key, 125)], timeout=0.2, n=10, n_verify=5)
		if not ok3: 
			print('****** Issue returning N.C.O.T.', real_next_key, 'to original config')
			print(diff)
			print('reset planned')

		if all([ok1, ok2, ok3]): 
			continue
		else:
			base.reset(c, config)



		




		




		continue
	return

def main(pacman_tile, io_group, skip_test, tile_id, pacman_version, vdda):
	tile_name = 'id-' + tile_id 
	io_channels = [ 1 + 4*(pacman_tile - 1) + n for n in range(4)]
	#io_channels = [1, 2, 4]
	c = get_initial_controller(io_group, io_channels, vdda, pacman_version)

	root_chips, io_channels = get_good_roots(c, io_group, io_channels)
	print(root_chips)
	c = reset_board_get_controller(c, io_group, io_channels)

	#need to init whole network first and write clock frequency, then we can step through and test

	existing_paths = [ [chip] for chip in root_chips  ]

	#initial network
	paths = arr.get_path(existing_paths)
	print('path including', sum(  [len(path) for path in paths] ), 'chips' )

	#bring up initial network and set clock frequency
	init_initial_network(c, io_group, io_channels, paths)
	#test network to make sure all chips were brought up correctly
	ok = test_network(c, io_group, io_channels, paths)

	while not ok:
		c = reset_board_get_controller(c, io_group, io_channels)

		existing_paths = [ [chip] for chip in root_chips  ]

		#initial network
		paths = arr.get_path(existing_paths)
		print('path inlcuding', sum(  [len(path) for path in paths] ), 'chips' )

		#bring up initial network and set clock frequency
		init_initial_network(c, io_group, io_channels, paths)

		#test network to make sure all chips were brought up correctly
		ok = test_network(c, io_group, io_channels, paths)

	#existing network is full initialized, start tests
	######
	##generating config file
	_name = 'tile-' + tile_name + "-pacman-tile-"+str(pacman_tile)+"-hydra-network"
	if True:
		print('writing configuration', _name + '.json, including', sum(  [len(path) for path in paths] ), 'chips'  )
		generate_config.write_existing_path(_name, io_group, root_chips, io_channels, paths, arr.excluded_links, arr.excluded_chips, asic_version=2)

	##
	##
	if skip_test: return c
	print('\n***************************************')
	print(  '***Starting Test of Individual UARTs***')
	print(  '***************************************\n')
	##
	##
	config = _name+'.json'
	c=base.main(controller_config=config)

	for ipath, path in enumerate(paths):
		for ich in range(len(path)):
			ok = test_chip(c, io_group, io_channels[ipath], path, ich, paths.copy(), io_channels.copy(), config)
			#only returns whether or not a test was performed, not the test status

	print('bad links: ', arr.excluded_links)
	print('tested', len(arr.good_connections) + len(arr.excluded_links), 'uarts')

	return c

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--pacman_tile', default=1, type=int, help='''Pacman software tile number; 1-8  for Pacman v1rev3; 1 for Pacman v1rev2''')
	parser.add_argument('--pacman_version', default='v1rev3', type=str, help='''Pacman version; v1rev2 for SingleCube; otherwise, v1rev3''')
	parser.add_argument('--vdda', default=0, type=float, help='''VDDA setting during test''')
	parser.add_argument('--tile_id', default='1', type=str, help='''Unique LArPix large-format tile ID''')
	parser.add_argument('--io_group', default=1, type=int, help='''IO group to perform test on''')
	parser.add_argument('--skip_test', default=False, type=bool, help='''Flag to only write configuration file with name tile-(tile number).json, skip test''')
	args = parser.parse_args()
	c = main(**vars(args))
	###### disable tile power
	c.io.set_reg(0x00000010, 0, io_group=args['io_group'])

