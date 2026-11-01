# Z15 板卡基线

目标：正点原子 Z15，xc7z015clg485-2，OV5640 接 P2，PL USB UART 接电脑，HDMI OUT 在 v2 三分区功能中必接（v1 仅可选预览）。实物 PCB 修订尚未核对。

唯一约束为 constraints/z15_eye.xdc 与 constraints/z15_eye_timing.xdc。PL 50 MHz 时钟使用原厂例程的 Y14；摄像头 DVP 是 1.8 V Bank 信号，SCCB 是 3.3 V，不得按通用开发板示例替换电平。P2 模块有参考振荡器，顶层不输出 XCLK。

引脚来源：底板原理图 P2 页面和原厂 26_ov5640_hdmi P2 XDC。IO 表中的 D4/PWDN 对调，当前取 D4=U1、PWDN=K7。摄像头 PCLK 在 U2，沿用非专用时钟输入的布线例外；DVP 0–8 ns 输入时序包络是待实测假设，不能当作示波器测量结果。

PL USB UART 位于 J23；J24 的 1–3、2–4 接 USB 通路，另一组位置连接 ATK。完整接线与 JTAG 下载见 [新版使用说明](../docs/screen_gaze.md)。目前没有执行下载或 Flash 烧写。

上电前按实际 PCB 核对 Bank 电压。提供的 1V1 底板原理图物理第 3 页将 J4（B34）、J3（B35）画为三针，2 脚为 Bank 电源、3 脚为 1.8V，当前设计应各短接 2–3。手册 p106 的六针图是不同版本，不能混用针号。BOOT_CFG 1、2 都 ON 为 JTAG；JTAG 接口为 J18。

底板原理图物理第 11 页的用户 LED 经 S8050 驱动，高电平点亮。v1 RTL 输出 ~ready、~valid，就绪/有效时熄灭；v2 输出 ready、valid，就绪/有效时点亮。核心板 DONE 灯另作配置完成指示。
