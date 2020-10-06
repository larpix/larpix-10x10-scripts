# Overview
This directory contains the PACMAN firmware and software.

# Updating
To update the PACMAN firmware, copy firmware/BOOT.BIN and firmware/image.ub to the BOOT partition of the
PACMAN microSD. Then expand the firmware/rootfs.tar.gz into the rootfs partition with `tar -C <path to rootfs partition> xvf firmware/rootfs-wlocal.tar.gz`.

The PACMAN will come up with an initial hostname of `pacman`. This can be modified via `vi /etc/hostname`
after ssh'ing into the running PACMAN, and then rebooting the card. We have used the common format of
`pacman##`.

# Installing from raw microSD
If you need to replace the microSD of the PACMAN, use your favorite disk management tool to create two
partitions on the microSD::

           Partition Number     Format          Name            Approx. size
           0                    FAT             BOOT            ~100MB
           1                    ext4            rootfs          remaining (>1GB)

Then follow the instructions for updating the firmware.