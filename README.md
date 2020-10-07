# Overview
This directory contains a variety of scripts and configurations that assess the analog / digital performance
of the LArPix 10x10 tile.

# Structure
This repo contains the following::

     ├── autoconfig_thresholds.py                            - Script to automatically configure channel thresholds
     ├── base.py                                             - Script to bring up communication with tile
     ├── configs                                             - Directory containing chip configurations
     │   └── autothreshold_base.json                         - Base chip config used by autoconfig_thresholds.py
     ├── controller                                          - Directory containing hydra network config files
     │   ├── network-10x10-tile-11only.json                  - Network config with chip 11 enabled only
     │   └── network-10x10-tile-4root-daisychain.json        - Network config with 4 daisy chain networks
     ├── internal_pulse.py                                   - Script to issue test pulses on chips
     ├── io                                                  - Directory containing io config files
     │   └── pacman.json                                     - IO config file for pacman card
     ├── leakage_current_rough.py                            - Script for assessing front-end leakage current
     ├── load_config.py                                      - Helper script for loading chip configurations
     ├── pedestal.py                                         - Script for assessing channel pedestals
     ├── README.md                                           - This is me
     ├── firmware                                            - Directory containing pacman firmware files
     │   ├── BOOT.BIN                                        - Boot binary (contains PL configuration)
     │   ├── image.ub                                        - Petalinux kernel
     │   ├── rootfs-wlocal.tar.gz                            - Custom petalinux rootfs
     │   └── README.md                                       - Firmware description
     └── start_run.py                                        - Script for loading chip configs and collecting self-trigger data


# base.py
This script is runs the baseline bring-up procedure to reset the chip configurations, bring up the hydra
network, and verify communications. For a description of arguments, run::

         python3 base.py --help


# pedestal.py
This script runs the chips using an internal periodic trigger. Enables the internal periodic reset and
samples at the specified rate. Data from this script can be used to debug system noise, bad channels, and is
needed for accurate charge information. At least 1 pedestal run should be collected in liquid argon, prior to
powering on TPC HV. Typical performance should have a pedestal RMS <4mV. For a description of arguments, run::

         python3 pedestal.py --help


# leakage_current_rough.py
This script runs the chips in self-trigger mode without internal periodic reset. A large global threshold is
set to allow leakage current to integrate on the front-end. The self-trigger rate is directly proportional to
the leakage rate. Typical performance at warm is ~3Hz/channel, and in liquid argon this is about 100x
smaller. For a description of arguments, run::

         python3 leakage_current_rough.py --help


# autoconfig_thresholds.py
This script runs a auto-thresholding routine to set each channels' threshold and trim. The routine first sets
an initial global threshold is set by the configuration in configs/autothreshold_base.json. Any channels with
a rate higher than the specified target self-trigger rate are disabled. The global threshold is then reduced
until at least 1 channels' trigger rate is greater than the target rate on each chip. The global threshold
is then increased until all channels are below the target rate. This procedure is then run for the pixel
trim settings. Final configurations are dumped to the current directory. For a description of arguments,
run::

        python3 autoconfig_thresholds.py --help


# load_config.py
This script loads chip configurations with a format "chip-<chip-key>-*.json" from the specified directory and
verifies that the chip configurations were set correctly. For a description of arguments, run::

         python3 load_config.py --help


# start_run.py
This scripts loads chip configurations and then continuously collects data in intervals. Run this to collect
nominal self-trigger data. For a description of arguments, run::

        python3 start_run.py --help

