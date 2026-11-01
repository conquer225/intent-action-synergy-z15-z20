# 原样保留的无线启动参考

这些文件来自用户在 2026-09-30 提供的 PYNQ 启动包，SHA256 见 `../../report/wireless_reference.json`，实际解析见 `../../report/boot_reference_analysis.json`。

这里的 BOOT.BIN 是用户原有 Linux FSBL/U-Boot 启动文件；它与 `../../build/BOOT.BIN` 的裸机程序不同。image.ub 启用 USB0 host/okay，根文件系统位置为 SD 第二分区 `/dev/mmcblk0p2`。启动包本身不包含该分区的 rootfs，也不能单凭内核文件确定当前无线网卡型号/驱动。

继续使用已经能连无线网的 SD 卡。眼控服务在 Linux 中动态加载 `../overlay/eye_wifi.bit/hwh`，不自动改写启动分区，也不执行参考 boot.py 中的注释示例。
