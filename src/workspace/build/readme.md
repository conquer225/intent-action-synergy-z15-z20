# 构建和测试

当前用 screen/create_project.tcl、screen/build.tcl，生成 local/screen_vivado/z15_screen.xpr 和 report/screen/z15_screen_top.bit。screen/test.ps1 运行模块测试，screen/test_pipeline.ps1 运行真实 XPM FIFO 的 VGA 双眼集成测试。详细命令见 docs/screen_gaze.md。eye/ 是保留的 v1。

源路径相对根目录，不依赖 E 盘参考资料。当前没有 PS/DDR 或 HWH。
