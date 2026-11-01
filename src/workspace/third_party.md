# Third-party sources

This repository is not uniformly licensed. No blanket MIT grant is made over vendor material.

## Project F display_controller

URL: https://github.com/projf/display_controller
Commit: `dafbe3385749da4ae2100bba2945350ace7ec04e`
Copyright (C) 2019 Will Green. MIT; full license retained at `src/third_party/projectf/LICENSE`.

Reused: `async_reset.v`, `display_clocks.v`, `dvi_generator.v`, `serializer_10to1.v`, `tmds_encoder_dvi.v`.
Changes: removed per-pixel `$display` debug prints from TMDS encoder; tied MMCM PWRDWN low. The top overrides the clock parameters for 50 MHz input, 25.2 MHz pixel and 126 MHz serial clocks. RTL headers preserved.

## ALIENTEK / 正点原子

The local `32_fmc_ov5640_udp_pc/rtl/ov5640/i2c_ov5640_rgb565_cfg.v` says Copyright(C) 正点原子 2018–2028, All rights reserved. Its register settings are adapted into `src/eye/camera_rom.v` (v1) and `src/screen/camera_rom.v` (v2). Preserve this attribution. This is not a claim that vendor code has an open-source license.

Changes to register data: skip original ROM's two ID-read entries because a new SCCB sequencer explicitly reads and verifies 0x5640; output 320×240 for v1, 640×480 for v2; HTS=1896, VTS=984; maximum auto-exposure limited to VTS; table represented as distributed ROM. SCCB master, power/reset/retry sequencer and capture modules are newly written.

Hardware references (read, not copied wholesale):

- `E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/26_ov5640_hdmi`: P2 constraints, camera initialization and capture format.
- `E:/cankao/XC7Z015/XC7Z015/17_uart_loopback`: PL UART pins and clock.
- `E:/cankao/XC7Z015/XC7Z015/21_hdmi_colorbar`: HDMI output pins.
- `E:/see/参考文档/ZYNQ7015_开发板底板原理图_1V1.pdf`: connector, level translation and pin cross-checks.

The source bundle is for this local competition project. Before any public redistribution, check the vendor's redistribution terms; do not relabel the adapted register table as MIT.

## AMD XPM and device primitives

`xpm_fifo_async`, BUFG, MMCM, OSERDESE2 and OBUFDS are resolved from the installed Vivado 2023.1 distribution. No AMD source library is vendored here. Use under the installed tool's license.

## Algorithm references (no source copied)

- Antoine Lamé, GazeTracking, MIT, https://github.com/antoinelame/GazeTracking, commit `fce71359acd5ce6843630eaf3b85558a734b0dfe`.
- forever_00_, 2024 FPGA infrared pupil tracking competition project: https://blog.csdn.net/forever_00_/article/details/145709587 . Page declares CC BY-SA 4.0; no code from the page is included in this repository.
- PuRe and ElSe research papers; citations, inspected sections and implementation differences are in `docs/eye_research.md`. Original PDFs are local research copies, excluded from the source distribution.
