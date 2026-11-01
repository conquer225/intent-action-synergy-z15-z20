# PS 眼动开发清单

## 已完成

- 建立独立 Vivado 副本，器件 `xc7z015clg485-2`。
- 保留原厂 PS7、DDR3、HP0、AXI VDMA、OV5640 采集和 HDMI 输出配置。
- 建立 Vitis standalone 应用的可重复构建脚本。
- 启动 OV5640，配置 1280×720 RGB888 帧缓存，启动 VDMA 双向链路和 HDMI。
- 增加 DDR 帧缓存读取、缓存失效、帧签名、VDMA 状态和 UART 诊断输出。
- 增加双眼固定 ROI、自适应灰度暗区、有效性、三点校准、方向分类、停留确认和事件序号。
- 增加独立 HDMI 显示缓存和 PS 状态叠加层：方向条、校准进度、ROI 框和瞳孔中心。
- 完成主机端合成帧测试，覆盖三点校准、左右事件和中心释放。
- 生成 ELF、BOOT.BIN、XSA 和 bitstream 回退件。

## 当前验证

- Vivado BD 校验通过。
- ARM bare-metal ELF 构建通过。
- Bootgen 生成 BOOT.BIN 通过。
- 主机端 C 算法测试通过。
- 真实 Z15 上的相机、DDR、HDMI、帧率和识别准确率尚未在本轮自动化环境中测量。

## 上板后工作

1. 用 JTAG 或 SD 启动，记录 UART0 启动日志。
2. 确认 `OV5640 OK`、`VDMA OK`、`HDMI STARTED`。
3. 确认帧号递增、`vdma_tx/vdma_rx` 没有错误位。
4. 根据串口中 `L=(x,y,nx)` 与 `R=(x,y,nx)` 调整 `main.c` 中两个 ROI。
5. 输入 `c`，按提示依次注视左、中、右，每个方向保持约 4 秒。
6. 观察 `EYE_EVENT` 是否只在左/右停留后出现，回到中心是否释放。
7. 同时确认 HDMI 状态条、ROI 框和十字随串口状态变化。
8. 记录真实帧率、延迟、误检、遮挡和不同光照下的日志，再决定是否转到 640×480 或把状态叠加迁移到 PL。
