#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cp ../z15_usb_host_candidate/kernel.bin kernel.bin
cp ../z15_usb_host_candidate/usb_host.dtb usb_host_phy.dtb

fdtput -c usb_host_phy.dtb /phy0@e0002000
fdtput -t s usb_host_phy.dtb /phy0@e0002000 compatible ulpi-phy
fdtput -t x usb_host_phy.dtb /phy0@e0002000 '#phy-cells' 0
fdtput -t x usb_host_phy.dtb /phy0@e0002000 reg 0xe0002000 0x1000
fdtput -t x usb_host_phy.dtb /phy0@e0002000 view-port 0x170
fdtput -t x usb_host_phy.dtb /phy0@e0002000 phandle 0x100
fdtput usb_host_phy.dtb /phy0@e0002000 drv-vbus
fdtput -t x usb_host_phy.dtb /amba/usb@e0002000 usb-phy 0x100

mkimage -f image_usb_host_phy.its image_usb_host_phy.ub
dumpimage -T flat_dt -p 1 -o fit_extracted.dtb image_usb_host_phy.ub
cmp usb_host_phy.dtb fit_extracted.dtb
