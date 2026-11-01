# Source provenance

This bundle is not uniformly licensed. Preserve individual notices; no blanket license over vendor or AMD material is asserted.

## Embedded Haar model data

All three XML files were byte-compared to the OpenCV **4.10.0** release tag on 2026-09-28:

| File | SHA256 |
| --- | --- |
| haarcascade_frontalface_default.xml | 0f7d4527844eb514d4a4948e822da90fbb16a34a0bbbbc6adc6498747a5aafb0 |
| haarcascade_eye.xml | 71cc64fc305a355dc60067880f6fbbd43dd155bd63ee3844661a1bda34b2fd8c |
| haarcascade_frontalface_alt.xml | 6281df13459cc218ff047d02b2ae3859b12ff14a93ffe8952f7b33fad7b9697b |

Source: https://github.com/opencv/opencv/tree/4.10.0/data/haarcascades . Individual raw URLs append the filename to `https://raw.githubusercontent.com/opencv/opencv/4.10.0/data/haarcascades/`.

Face models: Rainer Lienhart. Eye model: Shameem Hameed. XML notices and the full Intel license are retained in the XML headers and `model/LICENSE.txt`. Generated `src/app/*_model.inc` arrays derive from these XML files and retain their SHA256 and license reference. They are trained generic detection models, not biometric templates identifying the user.

`haar.c` is a standalone C implementation, informed by OpenCV's documented cascade representation and inspection of `modules/objdetect/src/cascadedetect.cpp` at 4.10.0. There is no OpenCV binary dependency on the ARM. Native-scale evaluation, normalization and stage epsilon are checked against direct XML evaluation. Python/OpenCV is only an optional host validation dependency.

## ALIENTEK Z15 camera/HDMI example

Hardware BD, P2 constraints, OV5640 capture IP, DVI transmitter IP and camera/SCCB/display driver files were copied from the prior local PS project, whose reference is `E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/26_ov5640_hdmi`. Original headers remain. In this version SD0 on MIO40..45 with CD MIO10 is enabled by the recreation script; no vendor reference directory is modified.

These files carry ALIENTEK attribution and are included for this user's local board project. Their presence is not a grant of a general open-source redistribution license. Reference manuals and private face photographs are not distributed.

The display-control files also retain Sam Bobrowicz / Digilent Inc. 2014 notices from the vendor's adapted display driver. The PS-driven clock wizard is configured as No_buffer to avoid redefining FCLK as an external primary clock.

## AMD/Xilinx standalone software and tools

`bsp/include`, `bsp/lib/libxil.a`, FSBL, PS initialization and linker startup use Vitis 2023.1 embeddedsw. The distribution license is retained in `bsp/LICENSE.txt`; individual headers have additional notices. FSBL's SD path uses Xilinx xilffs/FatFs, with ChaN's license retained in `hardware/FATFS_LICENSE.txt`. Vivado IP and device primitives resolve from an installed licensed Vivado 2023.1 toolchain. The built bitstream/XSA are implementation outputs, not an independent grant over the tool IP.

`linux/driver` and `linux/include` retain the Vitis 2023.1 AXI VDMA, GPIO PS and VTC driver notices. Only MMIO, timing and memory ownership are adapted for the user's Linux/PYNQ environment. The spare wired transport uses lwIP 2.1.3; its BSD notice is in `bsp/LWIP_LICENSE.txt`.

`linux/boot_reference` contains user-supplied PYNQ boot binaries as unchanged local inspection/recovery references. REVISION identifies the supplied PYNQ build. No ownership or general redistribution permission over these Linux/U-Boot binaries is asserted. The Linux root filesystem and wireless driver package are not supplied by this project.
