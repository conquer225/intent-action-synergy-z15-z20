from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(r"D:\ican\codex_project")
OUT = ROOT / "output" / "documents" / "脑盾工坊_iCAN创新赛道_三分钟答辩讲稿_顺讲版.docx"

NAVY = "17365D"
PALE_BLUE = "EAF1F8"
PALE_GRAY = "F6F7F8"
LIGHT_BORDER = "D9D9D9"
ORANGE = RGBColor(198, 89, 17)
BLACK = RGBColor(0, 0, 0)
GRAY = RGBColor(89, 89, 89)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color=LIGHT_BORDER, size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def set_cell_margins(cell, top=90, start=110, bottom=90, end=110):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn("w:" + m))
        if node is None:
            node = OxmlElement("w:" + m)
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_run_font(run, name="Microsoft YaHei", size=11, bold=False, color=BLACK):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def set_para_spacing(p, before=0, after=6, line=1.25):
    fmt = p.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line


def add_body(doc, text, bold_lead=None):
    p = doc.add_paragraph(style="Body Text")
    set_para_spacing(p, after=7, line=1.32)
    if bold_lead and text.startswith(bold_lead):
        r1 = p.add_run(bold_lead)
        set_run_font(r1, bold=True)
        r2 = p.add_run(text[len(bold_lead):])
        set_run_font(r2)
    else:
        r = p.add_run(text)
        set_run_font(r)
    return p


def add_bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    set_para_spacing(p, after=4, line=1.22)
    for run in p.runs:
        set_run_font(run, size=10.5)
    if not p.runs:
        set_run_font(p.add_run(text), size=10.5)
    else:
        p.runs[0].text = text
    return p


def add_heading(doc, text, level=1):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run(text)
    set_run_font(r, size=16 if level == 1 else 12.5, bold=True, color=BLACK)
    return p


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    set_run_font(run, size=9, color=GRAY)


doc = Document()
sec = doc.sections[0]
sec.page_width = Inches(8.5)
sec.page_height = Inches(11)
sec.top_margin = Inches(0.68)
sec.bottom_margin = Inches(0.65)
sec.left_margin = Inches(0.78)
sec.right_margin = Inches(0.78)

styles = doc.styles
for style_name in ("Normal", "Body Text", "List Bullet"):
    style = styles[style_name]
    style.font.name = "Microsoft YaHei"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(11)
    style.font.color.rgb = BLACK

title_style = styles["Title"]
title_style.font.name = "Microsoft YaHei"
title_style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
title_style.font.size = Pt(25)
title_style.font.bold = True
title_style.font.color.rgb = BLACK
title_ppr = title_style._element.get_or_add_pPr()
title_border = title_ppr.find(qn("w:pBdr"))
if title_border is not None:
    title_ppr.remove(title_border)

for section in doc.sections:
    footer = section.footer
    fp = footer.paragraphs[0]
    left = fp.add_run("脑盾工坊  iCAN 创新赛道答辩材料")
    set_run_font(left, size=8.5, color=GRAY)
    fp.add_run(" " * 12)
    add_page_number(fp)

p = doc.add_paragraph(style="Title")
p.alignment = WD_ALIGN_PARAGRAPH.LEFT
p.paragraph_format.space_before = Pt(18)
p.paragraph_format.space_after = Pt(8)
ppr = p._p.get_or_add_pPr()
p_border = ppr.find(qn("w:pBdr"))
if p_border is not None:
    ppr.remove(p_border)
r = p.add_run("脑盾工坊 iCAN 创新赛道三分钟答辩讲稿顺讲版")
set_run_font(r, size=25, bold=True)

p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(18)
r = p.add_run("配套 ican.pptx 逐页讲解  一条故事线顺讲")
set_run_font(r, size=12, color=GRAY)

add_body(doc, "这份讲稿围绕产品为什么诞生展开。核心故事是：团队先发现传统安全装备能够监测环境，却看不到人的疲劳；电脑端算法虽然能识别，却难以直接部署到现场；因此团队把脑电质控、特征提取和推理逐步迁移到 FPGA 与 ARM，并用 ESP32 和 OpenMV 形成可显示、可告警的闭环。")

table = doc.add_table(rows=2, cols=4)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
widths = [1.05, 1.75, 1.85, 2.2]
headers = ["时长", "主线", "对应页", "评委应记住"]
values = ["3分钟", "问题到产品", "第1至16页", "脑状态边缘识别闭环"]
for row_i, row in enumerate(table.rows):
    for col_i, cell in enumerate(row.cells):
        cell.width = Inches(widths[col_i])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_border(cell)
        set_cell_margins(cell)
        set_cell_shading(cell, NAVY if row_i == 0 else PALE_BLUE)
        p2 = cell.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        text = headers[col_i] if row_i == 0 else values[col_i]
        rr = p2.add_run(text)
        set_run_font(rr, size=9.5, bold=row_i == 0,
                     color=RGBColor(255, 255, 255) if row_i == 0 else BLACK)

add_heading(doc, "使用提示", 1)
add_bullet(doc, "建议自然偏快地讲，目标时长控制在2分50秒至3分05秒。")
add_bullet(doc, "括号内的页码和时间不朗读。第9至10页讲到实物时，指向样机或演示视频。")
add_bullet(doc, "第8页的90%准确率属于公开研究基准，不要说成当前样机真人实测。")

doc.add_page_break()
add_heading(doc, "三分钟一口气顺讲版", 1)

speech_sections = [
    ("第1至3页  0分00秒至0分38秒",
     "各位评委老师好，我们是脑盾工坊。我们在研究矿井和长时间值守场景时注意到一个缺口：现场有安全帽、有气体传感器，也有监控，这些设备能够发现环境风险，却不知道佩戴者此刻是否清醒。传统安全帽能够防撞，手环能够测心率，但都难以直接反映大脑警觉度。等到动作失误，预警往往已经太晚。于是我们想做一套能够看见人的疲劳、并提前发出提醒的安全系统。"),
    ("第4至5页  0分38秒至1分08秒",
     "最初，我们在电脑上用 Python 跑通了脑电算法，但很快发现，依赖电脑和网络、重复等待校准，都不适合真正的作业现场。于是我们重新设计整条链路：OpenBCI 采集八通道脑电；Zynq 中的 FPGA 和 ARM 完成质量检测、特征提取和疲劳判断；ESP32 汇集心率、血氧、气体和姿态；OpenMV 提供视觉辅助。识别到风险后，系统联动网页、声光和振动告警。"),
    ("第6至8页  1分08秒至1分52秒",
     "真正困难的不是在电脑上得到一个结果，而是让算法在边缘端又快又稳定地运行。研究端我们参考 ViFormerNet 的多频带时空建模，工程端针对 Zynq-7015 的资源限制，采用八通道差分熵和轻量级 HGB 模型。原来 ARM 计算一个窗口的 DE 特征约需83毫秒，迁移到 FPGA 后小于1毫秒，保守计算至少提升80倍；HGB 硬件推理核约17微秒。FPGA 还会先检查通道质量，异常数据直接判为无效，而不是给出错误等级。在逐窗验证中，板端分类等级与 ARM 参考模型保持一致，因此我们提升的是计算速度和结果稳定性，并没有用硬件虚构准确率。"),
    ("第9至12页  1分52秒至2分30秒",
     "现在大家看到的是已经联调运行的原型。OpenBCI 数据可以实时进入系统，板端输出正常、轻度、重度和无效四类状态；ESP32 网页同步显示疲劳与环境信息；OpenMV 接入现场画面。个体校准还能写入 QSPI Flash，断电后直接加载，启动约8秒给出第一次结果，随后每2秒更新。我们也使用 SEED-VIG 有标签数据完成了 PC 与板端逐窗对照。PPT 中 PCC 0.9214和90%准确率，是公开研究模型的参考基准。"),
    ("第13至16页  2分30秒至3分00秒",
     "这条链路不是一次搭成的。我们先后解决了串口丢帧、DMA 长度、定点误差、校准等待和网页通信等问题，才把算法一步步搬到 FPGA 与 ARM。我们的竞争力不是简单增加传感器，而是把人的状态、环境风险和现场画面连接起来，形成从识别到告警的闭环。系统采用模块化设计，可面向矿山、危化、驾驶和长时间值守岗位，从小规模试点逐步完成结构优化和行业认证。我们希望安全设备能在风险形成之前理解人、提醒人。脑盾工坊，让安全从被动防护走向主动感知。谢谢。"),
]

for cue, text in speech_sections:
    p = doc.add_paragraph(style="Body Text")
    set_para_spacing(p, after=5, line=1.16)
    p.paragraph_format.keep_together = True
    cue_run = p.add_run("〔" + cue + "〕 ")
    set_run_font(cue_run, size=9.8, bold=True, color=ORANGE)
    text_run = p.add_run(text)
    set_run_font(text_run, size=10.2)

doc.add_page_break()
add_heading(doc, "故事主线与翻页提示", 1)

story_rows = [
    ("看到什么", "现场设备主要监测环境和撞击，人的疲劳状态缺少直接感知", "第1至3页"),
    ("发现什么不足", "电脑算法依赖主机与网络，重复校准和现场部署不方便", "第4至5页"),
    ("因此做了什么", "将质控、DE特征和HGB推理迁移到FPGA与ARM", "第6至8页"),
    ("产品能做什么", "八通道脑电识别，多传感器融合，网页显示，视觉辅助，本地告警", "第9至10页"),
    ("为什么可信", "完成公开数据回放、板端一致性验证和整条链路联调", "第11至12页"),
    ("为什么有竞争力", "离线边缘计算，质量门控，掉电保存校准，模块化改造", "第13至16页"),
]
table = doc.add_table(rows=1, cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
for i, h in enumerate(("故事节点", "要讲清的内容", "PPT")):
    c = table.rows[0].cells[i]
    set_cell_shading(c, NAVY)
    set_cell_border(c)
    set_cell_margins(c)
    c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    rr = c.paragraphs[0].add_run(h)
    set_run_font(rr, size=9.5, bold=True, color=RGBColor(255, 255, 255))
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
for ridx, row in enumerate(story_rows):
    cells = table.add_row().cells
    for i, val in enumerate(row):
        cells[i].width = Inches([1.35, 4.2, 1.0][i])
        set_cell_shading(cells[i], "FFFFFF" if ridx % 2 == 0 else PALE_GRAY)
        set_cell_border(cells[i])
        set_cell_margins(cells[i])
        cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        pp = cells[i].paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER if i != 1 else WD_ALIGN_PARAGRAPH.LEFT
        rr = pp.add_run(val)
        set_run_font(rr, size=9.2, bold=i == 0)

add_heading(doc, "现场表达提醒", 1)
add_bullet(doc, "开头不要先报技术名词。先讲传统装备看不见人的疲劳，再引出产品。")
add_bullet(doc, "讲第4至8页时，用最初电脑验证和后来边缘部署的变化体现团队思考。")
add_bullet(doc, "讲第9至10页时指向实物，说明哪些功能已经联调运行。")
add_bullet(doc, "结尾落到使用者获得更早提醒、管理者获得统一风险信息，不重复罗列模块。")

doc.add_page_break()
add_heading(doc, "高概率答辩问题与参考回答", 1)

qa = [
    ("1 你们的准确率到底是多少",
     "这里分为三个层次。PPT 中 PCC 0.9214和90%准确率属于公开论文在标准数据集上的模型基准；目前我们完成了 SEED-VIG 有标签数据的 PC 与板端逐窗回放对照，用来验证算法迁移前后的一致性；真人佩戴条件下的泛化准确率还需要扩大样本独立验证。因此当前能够确认的是工程链路和板端算法已经跑通，但不能把论文指标直接当作样机真人准确率。"),
    ("2 PPT 是 ViFormerNet 为什么板端运行 HGB",
     "ViFormerNet 是研究端的建模参考，说明多频带和时空信息怎样用于警觉度估计。当前原型采用八通道 DE 加 HGB，是针对 Zynq-7015 的资源、时延和可解释性做出的工程选择。我们先完成可靠的轻量闭环，再逐步进行深度网络剪枝和量化。"),
    ("3 为什么不用电脑直接运行 Python",
     "电脑适合训练和验证，不适合作为安全装备的最终核心。FPGA 可以并行处理多通道特征，ARM 负责协议、校准和系统控制。这样能够离线运行，减少原始脑电外传，也不会把核心告警建立在云端网络是否稳定之上。"),
    ("4 17微秒是不是整个系统的响应时间",
     "不是。17微秒是 HGB 硬件推理核的实测时间。系统必须先积累8秒脑电窗口，校准参数命中后约8秒输出第一次结果，随后每2秒更新。推理计算时延和生理信号观察窗口是两个概念。"),
    ("5 FPGA 是否提高了识别准确率",
     "FPGA 本身不会让同一个模型变得更准确。它的价值是并行计算、固定时延和稳定执行。当前 DE 特征从 ARM 的约83毫秒降到 FPGA 的1毫秒以内，至少提升80倍；HGB 推理核约17微秒。板端分类等级与 ARM 参考模型逐窗保持一致，质量门控还会过滤异常通道。因此准确的说法是速度和整体可靠性提高，同时保持参考模型的判断结果。"),
    ("6 为什么要校准 每次都要等待两分钟吗",
     "不同人的脑电基线存在差异，首次校准用于建立个体参考。我们已经把校准参数保存到 QSPI Flash，正常掉电后可以直接加载，不必每次采集15个基线窗口。更换佩戴者或电极状态明显变化时才建议重新校准。"),
    ("7 如何避免眨眼和接触不良造成误报",
     "系统在分类前设置 FPGA 质量门控，对幅值、饱和、均值和通道有效性进行检查。质量不合格时输出 INVALID，而不是勉强给出疲劳等级。结果还会经过滑动窗口和平滑，并可与姿态、心率和视觉事件联合复核。"),
    ("8 传感器都是现成的 你们真正创新在哪里",
     "创新在于软硬件协同闭环。我们把八通道脑电算法从 PC 迁移到 FPGA 与 ARM，实现质量门控、DE 特征、HGB 推理和掉电校准保存，再与环境、视觉和执行端联动。我们解决的是从能够采集数据，到能够在边缘端持续决策之间的工程断点。"),
    ("9 为什么选择八通道",
     "八通道在佩戴复杂度、计算资源和有效信息之间更平衡，适合先完成可穿戴原型。当前选择 FT7、FT8、CP1、CP2、P1、PZ、PO3、O1，保留颞区和顶枕区的相关信息。后续会依据真人数据重新完成通道消融和参数优化。"),
    ("10 OpenMV 的作用是什么",
     "OpenMV 是视觉辅助通道，可承担标记识别、作业区提示或事件留证。当前演示由 PC USB 图像桥接入网页，ESP32 传感器和 FPGA 脑电链路仍可独立运行；后续会改成更适合现场部署的直连方式。"),
    ("11 WiFi 中断后系统还能工作吗",
     "WiFi 主要负责网页显示和结果转发，脑电计算在 Zynq 本地完成，ESP32 也保留本地声光和振动执行能力。断网会影响远程查看，但不应中断本地识别和告警。"),
    ("12 这是医疗器械吗",
     "当前定位是非医疗的作业安全辅助设备，不进行疾病诊断。系统输出风险提示，用于提醒、复核和联动，不能代替医生或企业安全管理制度。"),
    ("13 如何证明系统不是只成功运行了一次",
     "我们采用分层验证。先做模型自检，再做 SEED-VIG 有标签回放，随后进行 OpenBCI 模拟信号连续链路测试，同时记录 CRC、丢帧、无效通道和板端结果。系统日志能够区分 UART、DMA、特征和网页通信问题，因此测试可以重复、问题可以定位。"),
    ("14 商业模式是什么",
     "早期通过高校实验平台和高风险岗位的小规模试点验证价值；成熟后与安全帽和工业安全设备企业合作，以硬件模块、管理平台和行业定制服务形成收入。与成熟厂商合作，也能降低从零建立生产和认证体系的成本。"),
    ("15 真正进入矿井还缺什么",
     "还需要真人多被试测试、长期稳定性测试、结构小型化、电磁兼容、本安与防爆认证，以及企业现场试点。当前原型证明的是技术链路和边缘计算可行性，不能把实验室样机直接等同于可以下井的量产设备。"),
    ("16 如果只能保留一个亮点 会保留什么",
     "我会保留脑电算法在 FPGA 与 ARM 边缘端运行，并与安全执行端形成闭环。它决定了系统能否脱离电脑和云端，继续发展为可穿戴安全设备，而不是停留在桌面算法演示。"),
]

for question, answer in qa:
    add_heading(doc, question, 2)
    add_body(doc, answer)

doc.add_page_break()
add_heading(doc, "数据口径与演示准备", 1)
add_heading(doc, "可以直接使用的表述", 2)
for item in (
    "板端 HGB 推理核实测约17微秒。",
    "DE 特征提取由 ARM 的约83毫秒降至 FPGA 的1毫秒以内，保守表述为至少提升80倍。",
    "FPGA 提升计算速度和执行稳定性，板端分类等级与 ARM 参考模型保持一致。",
    "校准参数从 QSPI Flash 加载后，约8秒输出第一次结果，随后每2秒更新。",
    "公开研究模型在标准数据上的基准为 PCC 0.9214和分类准确率90%。",
    "已完成 SEED-VIG 有标签数据的 PC 与板端逐窗回放对照。",
    "系统当前为非医疗作业安全辅助原型。",
):
    add_bullet(doc, item)

add_heading(doc, "暂时不要使用的表述", 2)
for item in (
    "我们的真人疲劳识别准确率已经达到90%。",
    "使用 FPGA 后，模型准确率提高了多少个百分点。",
    "产品现在已经能够直接进入矿井生产环境。",
    "17微秒就是从采集脑电到报警的全部时间。",
    "ViFormerNet 已经完整部署在当前 FPGA 上。",
):
    add_bullet(doc, item)

add_heading(doc, "现场演示清单", 2)
for item in (
    "预先加载已经保存的 QSPI 校准参数，避免现场等待首次校准。",
    "准备 NORMAL、MILD、SEVERE、INVALID 四类状态截图。",
    "准备包含 PL_HGB_FEATURE 和 CALIBRATION_LOAD HIT 的板端日志截图。",
    "准备10至15秒实物录屏，展示网页、传感器和 OpenMV 画面。",
    "断开互联网后仍能本地识别的演示，可用于回答边缘计算价值。",
):
    add_bullet(doc, item)

add_heading(doc, "赛事依据", 2)
add_body(doc, "2026年第二十届 iCAN 大学生创新创业大赛创新赛道以应用创新为主要考察目标。评分由创新性30分、商业性25分、技术方案25分和产品介绍20分组成。讲稿因此优先讲清产品故事、原创工程价值、实物完成度和落地路径。")
add_body(doc, "参考链接：https://seie.hit.edu.cn/2026/0414/c9232a389941/page.htm")
add_body(doc, "赛事官网：https://g-ican.com/competition/ican")

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(OUT)
