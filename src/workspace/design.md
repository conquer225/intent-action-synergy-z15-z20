# 我们意念合一：展示界面规范

全部当前 HDMI、网页和手机界面采用暖色仪表界面：奶油白底 #fbf7ee，米白内容面 #fffcf5，淡黄分区 #f2e8d3，细边界 #d9ccb6，深褐正文 #332c22，次级正文 #74644d，铜金重点 #855f22。精确颜色以 integrations/vision_demo/presentation_theme.py 为准，生成运行目录同名模块与 presentation.css；构建时核对源与副本。

实际波形、热图、窗口进度和执行回执承担主要信息。图表使用金、橄榄与褐色区分数据；停止和错误保留红色。中文使用本地微软雅黑／Droid 中文字体，明确字级与数字对齐，不加载 CDN。正文直接写操作与结果，开发信息进入技术说明。

保留 HDMI 三个等宽眼控区域、标定目标位置、原白点深色采样画面、阅读保护和 SSVEP 光刺激。其余菜单和眼控定位页统一暖色。连续视频像素保持原貌，换肤只改周边框架。

脑电展示默认载入真实 LEMON 记录，标明记录来源，四页共享时间。网页原实时接口保留保护，展示不调用实时采集／校准／执行端。桌面 1920×1080、1366×768 与 390×844 手机竖屏检查；HDMI 1280×720 独立渲染。

## EEG heatmap views

EEG presentation is designed for passive 1280×720 HDMI and physical key switching. Use dominant eight-channel traces, actual feature heatmaps and concise state values. No interactive chart library. The browser four-page preview renders exactly the native frames. All channels share an explicit microvolt scale. Spectral display is limited to the actual display branch Nyquist frequency; it never substitutes for inference features. Log-covariance heatmaps reconstruct the original weighted feature vector without recomputation. Keep the approved ivory/gold palette; aubergine marks low spectral power and negative covariance, with a visible scale.

## Music audio analysis layout

The music spectrum leads as a full-width 1166-pixel plot with a 20 Hz–20 kHz logarithmic axis. Its waterfall sits below on the same frequency axis. Stereo traces share the lower row with a common FS scale and separate measured levels; three energy bands form one horizontal strip. Avoid stacking charts and playback labels in a narrow right sidebar. Preserve actual FFT bins and playback position; do not smooth or fabricate values for appearance.

The visible spectrum uses 64 log-frequency peak columns to avoid overdraw at high frequencies. Each column is the actual maximum of its input bins, explicitly labelled as a band peak; empty bands remain empty. Raw FFT results, global peak frequency and low/mid/high energy percentages remain unchanged.
