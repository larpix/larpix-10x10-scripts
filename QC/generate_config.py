import graphs
import json
import argparse


_name = 'tile-6'
_excluded_chips = []
_good_root_connections = [11, 41, 71, 101]
_io_channels =           [21, 22, 23, 24]
_excluded_links = [ (61, 71), (24, 34), (44, 43), (64, 74), (49, 59), (43, 44), (22, 32)]

_io_group = 1


_header = {"_config_type": "controller", "name": _name, "asic_version": 2,"layout": "2.5.0", "network" : {str(_io_group) : {}}}



def main(_name=_name, _io_group=_io_group, _good_root_connections=_good_root_connections, _io_channels=_io_channels, _excluded_links=_excluded_links, _excluded_chips=_excluded_chips, verbose=False):
	nchips_hit = 0
	na = graphs.NumberedArrangement()
	for link in _excluded_links:
		na.add_onesided_excluded_link(link)
	for chip in _excluded_chips:
		na.add_excluded_chip(chip)

	_dict = {}

	paths = na.get_path([ [root] for root in _good_root_connections  ])

	for i in range(11, 111):
		if not any([i in path for path in paths]):
			print(i)

	for n, path in enumerate(paths):
		root_connection = _good_root_connections[n]
		nchips_hit += len(path)
		print(len(path))

		_header['network'][str(_io_group)][str(_io_channels[n])] = {}

		nodes = [ {"chip_id" : 'ext', "miso_us": [None,None,None,root_connection], "root" : True} ]
		for k, chip in enumerate(path):
			if k < len(path)-1:
				nodes.append({'chip_id' : chip, "miso_us" : na.get_map(chip, path[k+1])})
			else:
				nodes.append({'chip_id' : chip, "miso_us" : [None, None, None, None]})
		
		_header['network'][str(_io_group)][str(_io_channels[n])]['nodes'] = nodes


	_header['network']["miso_us_uart_map"] = [ 3, 0, 1, 2 ]
	_header['network']["miso_ds_uart_map"] = [ 1, 2, 3, 0 ]
	_header['network']["mosi_uart_map"] = [ 2, 3, 0, 1 ]

	print(nchips_hit)


	jsonString = json.dumps(_header, indent=4)
	jsonFile = open(_name + ".json", "w")
	jsonFile.write(jsonString)
	jsonFile.close()
	





if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('--verbose', default=True, type=bool, help='''Print status of algorithm at each step''')
	args = parser.parse_args()
	c = main(**vars(args))
