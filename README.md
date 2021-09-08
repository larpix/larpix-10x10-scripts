# LArPix Anode Tile Quality Control

## NOTE: The below is work in progress. Use the provided documentation Google slides documentation from russell@lbl.gov, for step-by-step QC guide in the interim.

## Overview

The quality control procedure noted here will produce two output files: 

- a Markdown file containing the CI-level summary metrics and plots called `QC_Tile_[tile_id_number].md`
- a JSON file composed of dictionaries to track tile, ASIC, channel performance at various stages of the LArPix QC process. 

(TODO: The naming scheme of the JSON file is TBD.) 

The `[tile_id_number]` is the tile ID assigned in the LArPix-v2 System Parts Database spreadsheet. This tile ID can be cross checked against two ASIC serial numbers to confirm physical tile identity. 

Module-1 anode tile testing initiates the start of QC metric tracking. The goal is for ASIC and tile performance to be tracked from individual ASIC testing (at Caltech), to warm and cold tile testing (at Berkeley and UTA, respectively), to module checkout (at Bern and FNAL), through LArTPC operation (at Bern, FNAL, and SingleCube sites). Evaluation of system performance at each stage is crucial to system design and robustness. Open an `issue` if a new failure mode has been identified for which the QC process should monitor.

### 0. Tile-ASIC mapping
(TO DO: Scan ASICs & map ASIC serial no. against tile placement per the appropriate tile layout as defined in larpix-geometry. The QR code printed to LArPix-v2a packaged ASICs is unscannable. To be determined, if the QR code is scannable on the new LArPix-v2b packaged ASIC. For the time being, we manually save to file packaged chip serial numbers for ASICs with broken UARTs and tile-identifying ASICs (chip IDs 11 and 110 as defined in larpix-geometry layout 2.3.0).)

This script will:
- save figure visually noting tile serial number, larpix-geometry ASIC x-y position, and larpix-geometry chip ID to Markdown file
- save dictionary to JSON file formatted as follows: ```[< tile ID >][< QC stage >]['ASIC'][< serial no., larpix-geometry chip ID, boolean true if original or false if replaced >]```


### 1. UART test
This test produces a Hydra network configuration and tracks broken UARTs on ASICs. The algorithm first tests `root` chips to find eligible ASICs within a tile from which a Hydra network may originate. From eligible `root` ASICs, an ASIC network is constructed, whereby after configuring each ASIC in the network chip-by-chip loopback between ASICs determines which ASICs can be reached. If a broken UART is encountered, the Hydra network is re-routed around the broken UART connection and re-checks remaining UARTs until the largest possible network is initialized. Once a network is constructed, the two-way connection between each ASIC and its neighbor is tested. Note that ASIC UARTs absent of an ASIC neighbor are not tested given the geometrical constraints of the anode tile. To run the algorithm:

```bash
./map_uart_links_test.py [tile_number]
```

where `[tile_number]` is the software tile number defining connections to PACMAN UARTs. This script will:
- produce a JSON file containing the tile Hydra network configuration in the format `tile-[software_tile_number]-autoconfig.json` 

(TO DO: (1) include tile ID in filename; (2) only save ASIC-to-ASIC network connections; in separate algorithm combine to operational network JSON --> additional script needed; therefore, remove software tile number from filename)

- save figure of network map to Markdown file, noting broken UARTs
- save dictionary to JSON file formatted as follows: ```[< tile ID >][< QC stage >]['Broken_UART'][< ASIC serial no. >][< (MOSI, MISO) >]```

### 2. Leakage test
Here we want to establish which are the channels with high leakage.
To do so we run:

```bash
./leakage_qc.py \
--controller_config tile-[tile_number]-autoconfig.json
```

This script will produce a HDF5 file in the format `datalog_yyyy_mm_dd_hh_mm_ss_TZ_leakage.h5` containing the packets. Then, in order to find the high leakage channels we run:

```base
./plot_leakage_channel.py datalog_yyyy_mm_dd_hh_mm_ss_TZ_leakage.h5
```

This script will:
- produce a JSON file called `disabled_channels_[tile_number].json` with a list of the chip keys with a leakage above a certain threshold
- write a list of the high leakage chip keys and their relative leakage value to the Markdown report
- plot the mean, standard deviation, and rate of all the channels and save the plot in the Markdown report.

### 3. Pedestal test
Here we want to establish which are the noisy channels. To do this we run

```bash
./pedestal_datalog.py \
--controller_config tile-[tile_number]-autoconfig.json
--runtime 60
--disabled_channels "$(cat disabled_channels_[tile_number].json)"
```

This script will produce a HDF5 file in the format `datalog_yyyy_mm_dd_hh_mm_ss_TZ_pedestal.h5` containing the packets. Then, in order to find the noisy channels we run

```bash
./plot_mean_std_rate.py datalog_yyyy_mm_dd_hh_mm_ss_TZ.h5
```
This script will:
- add to the `disabled_channels_[tile_number].json` file a list of the chip keys with a noise above a certain threshold
- write a list of the noisy chip keys and their relative noise value to the Markdown report
- plot the mean, standard deviation, and rate of all the channels and save the plot in the Markdown report.

### 4. Corrupt packets
TODO

### 5. Threshold configuration
Here we want to find the threshold for each chip in the tile. To do so we run

```bash
./autoconfig_threshold.py \
--controller_config tile-[tile_number]-autoconfig.json
--disabled_channels "$(cat disabled_channels_[tile_number].json)"
mkdir config_[tile_number]
mv config-* config_[tile_number]
```

### 6. Self-trigger
Here we want to have a self-trigger run and verify that the remaining channels are working correctly.

To do so we run:
```bash
./start_run_log_raw.py \
--config_name config_[tile_number]
--controller_config tile-[tile_number]-autoconfig.json
--disabled_channels "$(cat disabled_channels_[tile_number].json)"
```

TODO: what do we want to do with the output of this script?

### 7. Internal test pulse
Here we want to issue a set number of test pulses to the tile channels.

```bash
./internal_pulse.py \
--config_name config_[tile_number]
--controller_config tile-[tile_number]-autoconfig.json
```

TODO: what do we want to do with the output of this script?
