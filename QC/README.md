# Quality control procedure and metrics for LArPix-v2 rev. 2 tiles

## Procedure

The output of the quality control procedure will be a Markdown file containing the relevant metrics and plots called `QC_Tile_[tile_db_number].md` where `[tile_db_number]` is the number of the tile in our database.

### 1. UART test
First we need to establish a working Hydra configuration. To do this we run

```bash
./map_uart_links_test.py [tile_number]
```

where `[tile_number]` is the software tile number. This script will:
- produce a JSON file containing the Hydra configuration in the format `tile-[tile_number]-autoconfig.json`
- write in the Markdown report the broken UARTs.
- if possible, produce a drawing of the network configuration to be put in the Markdown report.

### 2. Leakage test
Here we want to establish which are the channels with high leakage.
To do so we run:

```bash
./leakage_current.py \
--controller_config tile-[tile_number]-autoconfig.json
```

This script will produce a HDF5 file in the format `datalog_yyyy_mm_dd_hh_mm_ss_TZ_leakage.h5` containing the packets. Then, in order to find the high leakage channels we run:

```base
./plot_leakage_channel.py datalog_yyyy_mm_dd_hh_mm_ss_TZ_leakage.h5
```

This script will:
- produce a JSON file called `disabled_channels_[tile_db_number].json` with a list of the chip keys with a leakage above a certain threshold
- write a list of the high leakage chip keys and their relative leakage value to the Markdown report
- plot the mean, standard deviation, and rate of all the channels and save the plot in the Markdown report.

### 3. Pedestal test
Here we want to establish which are the noisy channels. To do this we run

```bash
./pedestal_datalog.py \
--controller_config tile-[tile_number]-autoconfig.json
--runtime 60
--disabled_channels "$(cat disabled_channels_[tile_db_number].json)"
```

This script will produce a HDF5 file in the format `datalog_yyyy_mm_dd_hh_mm_ss_TZ_pedestal.h5` containing the packets. Then, in order to find the noisy channels we run

```bash
./plot_mean_std_rate.py datalog_yyyy_mm_dd_hh_mm_ss_TZ.h5
```
This script will:
- add to the `disabled_channels_[tile_db_number].json` file a list of the chip keys with a noise above a certain threshold
- write a list of the noisy chip keys and their relative noise value to the Markdown report
- plot the mean, standard deviation, and rate of all the channels and save the plot in the Markdown report.

### 4. Corrupt packets
TODO

### 5. Threshold configuration
Here we want to find the threshold for each chip in the tile. To do so we run

```bash
./autoconfig_threshold.py \
--controller_config tile-[tile_number]-autoconfig.json
--disabled_channels "$(cat disabled_channels_[tile_db_number].json)"
mkdir config_[tile_db_number]
mv config-* config_[tile_db_number]
```

### 6. Self-trigger
Here we want to have a self-trigger run and verify that the remaining channels are working correctly.

To do so we run:
```bash
./start_run_log_raw.py \
--config_name config_[tile_db_number]
--controller_config tile-[tile_number]-autoconfig.json
--disabled_channels "$(cat disabled_channels_[tile_db_number].json)"
```

TODO: what do we want to do with the output of this script?

### 7. Internal test pulse
Here we want to issue a set number of test pulses to the tile channels.

```bash
./internal_pulse.py \
--config_name config_[tile_db_number]
--controller_config tile-[tile_number]-autoconfig.json
```

TODO: what do we want to do with the output of this script?