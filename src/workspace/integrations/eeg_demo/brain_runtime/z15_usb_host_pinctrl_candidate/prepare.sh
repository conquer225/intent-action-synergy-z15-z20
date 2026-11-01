#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

cp ../z15_usb_host_candidate/kernel.bin kernel.bin
cp ../z15_usb_host_phy_candidate/usb_host_phy.dtb usb_host_pinctrl.dtb

pinctrl=/amba/slcr@f8000000/pinctrl@700/usb0-default
fdtput -c -p usb_host_pinctrl.dtb "$pinctrl/mux"
fdtput -c -p usb_host_pinctrl.dtb "$pinctrl/conf"
fdtput -c -p usb_host_pinctrl.dtb "$pinctrl/conf-rx"
fdtput -c -p usb_host_pinctrl.dtb "$pinctrl/conf-tx"
fdtput -t x usb_host_pinctrl.dtb "$pinctrl" phandle 0x101

fdtput -t s usb_host_pinctrl.dtb "$pinctrl/mux" groups usb0_0_grp
fdtput -t s usb_host_pinctrl.dtb "$pinctrl/mux" function usb0
fdtput -t s usb_host_pinctrl.dtb "$pinctrl/conf" groups usb0_0_grp
fdtput -t x usb_host_pinctrl.dtb "$pinctrl/conf" slew-rate 0
fdtput -t x usb_host_pinctrl.dtb "$pinctrl/conf" io-standard 1
fdtput -t s usb_host_pinctrl.dtb "$pinctrl/conf-rx" pins MIO29 MIO31 MIO36
fdtput usb_host_pinctrl.dtb "$pinctrl/conf-rx" bias-high-impedance
fdtput -t s usb_host_pinctrl.dtb "$pinctrl/conf-tx" pins MIO28 MIO30 MIO32 MIO33 MIO34 MIO35 MIO37 MIO38 MIO39
fdtput usb_host_pinctrl.dtb "$pinctrl/conf-tx" bias-disable

usb=/amba/usb@e0002000
fdtput -t s usb_host_pinctrl.dtb "$usb" pinctrl-names default
fdtput -t x usb_host_pinctrl.dtb "$usb" pinctrl-0 0x101

mkimage -f image_usb_host_pinctrl.its image_usb_host_pinctrl.ub
dumpimage -T flat_dt -p 1 -o fit_extracted.dtb image_usb_host_pinctrl.ub
cmp usb_host_pinctrl.dtb fit_extracted.dtb
