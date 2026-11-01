# 原调试保持更新的固定输入

这里保存原调试保持安装器的历史载荷与测试基线。当前设备菜单修订使用独立配套更新，历史安装器继续核对原来的摘要，不混入需要新控制器的运行服务。

`baseline_20261018` 的显示、设备控制器及通信服务从已解包的 `local/release_20261025/presentation_release/integrations/eye_c3/runtime` 保存，对应原眼控安装基线。它们用于重建旧版本的安装测试，不是当前维护源码。

`device_link.py` 从 `z20_compute/report/eye_audio_20261028/board-device_link.py` 按字节复制，SHA256 为 `251d35c0396266b8cb5fbd02629d5e1b53c73d7281b3897be4360ecaba993f09`，与原调试保持清单一致。`system_hdmi.py` 是既有的旧主题调试载荷。
