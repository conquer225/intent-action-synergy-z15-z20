from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(r"D:\ican\codex_project")
SLIDE_DIR = ROOT / "tmp" / "ican_slides_doc"
OUT = ROOT / "output" / "documents" / "脑盾工坊_iCAN_16页PPT逐页提示词与三分钟讲稿.docx"

NAVY = "173A63"
PALE_BLUE = "EEF5FB"
PALE_GRAY = "F5F6F8"
ORANGE = RGBColor(216, 91, 24)
GRAY = RGBColor(88, 96, 105)
BLACK = RGBColor(0, 0, 0)


slides = [
    {
        "title": "封面",
        "time": "0:00-0:07",
        "cue": "脑盾工坊  矿井安全  人的疲劳",
        "say": "各位评委老师好，我们是脑盾工坊。我们希望用脑机接口，让矿井安全从只监测环境，进一步看见人的疲劳状态。",
        "point": "看项目名称和右侧脑部图，不展开技术。",
        "next": "我们为什么从矿井安全切入，请看下一页。",
    },
    {
        "title": "产品简介  社会背景",
        "time": "0:07-0:23",
        "cue": "疲劳看不见  环境与人  提前预警",
        "say": "我们关注矿井，是因为井下已有安全帽、气体传感器和监控，但这些设备主要发现环境危险，很难知道佩戴者此刻是否清醒。疲劳看不见，等动作失误再报警往往已经太晚，这就是产品要解决的问题。",
        "point": "先指左侧矿井痛点，再扫到中间脑机接口和右侧政策支持。",
        "next": "除了安全痛点，市场投入也在持续增长。",
    },
    {
        "title": "产品简介  经济背景",
        "time": "0:23-0:30",
        "cue": "安全投入  需求增长  落地空间",
        "say": "图中的投入趋势说明，矿山安全需求仍在增长。企业愿意为风险前移付费，也给智能安全装备留下了实际落地空间。",
        "point": "分别指向历史投入和未来预测两张柱状图，不逐个念数字。",
        "next": "针对这个需求，我们设计了四端协同的系统。",
    },
    {
        "title": "产品简介  架构",
        "time": "0:30-0:44",
        "cue": "采集  处理  显示  执行",
        "say": "系统分为采集、处理、显示和执行四端。OpenBCI采集八通道脑电，Zynq中的FPGA和ARM完成质量检测、特征计算和疲劳判断；ESP32汇集环境与人体传感器，OpenMV补充现场画面，结果在网页显示并触发告警。",
        "point": "按左上、左下、右上、右下的顺序指四端。",
        "next": "四端连接起来以后，数据按照下一页的流程闭环运行。",
    },
    {
        "title": "系统执行流程",
        "time": "0:44-0:56",
        "cue": "采集  信号处理  FPGA  硬件控制",
        "say": "按这张流程图，采集后的脑电先做信号处理，既可由CCA形成控制指令，也可进入疲劳识别。我们把疲劳链路的DE特征和HGB推理迁移到Zynq，FPGA负责并行计算，ARM负责校准、协议和系统控制，使结果能够直接联动硬件。",
        "point": "沿着信号采集、信号处理、控制指令、硬件控制的箭头讲。",
        "next": "下面重点介绍疲劳识别算法如何从研究模型变成板端实现。",
    },
    {
        "title": "技术路线  疲劳识别总览",
        "time": "0:56-1:14",
        "cue": "ViFormerNet参考  多频带DE  八通道  HGB落地",
        "say": "研究端我们参考ViFormerNet的多频带建模，先从不同频段提取差分熵，再结合时空信息判断警觉度。考虑Zynq-7015的资源，当前原型没有照搬完整深度网络，而是把关键思路落成八通道DE加轻量HGB，兼顾实时性和可解释性。",
        "point": "从左到右依次指原始脑电、五个频带、双分支和疲劳等级输出。",
        "next": "其中双分支分别解决时间变化和脑区空间关系。",
    },
    {
        "title": "ViFormerNet双分支结构",
        "time": "1:14-1:27",
        "cue": "全局时空  脑区层次  空间聚合  FPGA特征",
        "say": "图中的全局时空分支关注各通道随时间的变化，脑区层次分支利用不同脑区的空间关系。我们的工程版本保留多频带和空间聚合思路，并把最适合并行的DE特征计算放进FPGA。",
        "point": "先指左侧全局时空分支，再指中间脑区图和右侧两段解释。",
        "next": "模型效果和我们采用的数据基准在下一页。",
    },
    {
        "title": "独立受试者与对比实验",
        "time": "1:27-1:43",
        "cue": "SEED-VIG  PCC 0.9214  约90%  板端一致",
        "say": "这一页是公开研究在SEED-VIG标准数据上的基准，PCC达到0.9214，分类准确率约90%。我们使用同一批有标签数据完成PC与板端逐窗对照，板端分类等级与ARM参考模型保持一致。这里要区分论文指标和当前样机的真人指标。",
        "point": "指表格中的PCC、Acc和ViFormerNet一行，不逐行读表。",
        "next": "算法之外，我们已经完成了可以联调的硬件原型。",
    },
    {
        "title": "实物展示",
        "time": "1:43-1:55",
        "cue": "脑电帽  OpenBCI  传感器  Zynq加速",
        "say": "这里展示的是脑电帽、OpenBCI采集板和环境传感器原型。脑电进入Zynq后，DE特征由ARM约83毫秒降到FPGA的1毫秒以内，保守提升至少80倍；HGB硬件推理约17微秒。",
        "point": "依次指左侧采集板、中间脑电帽和右侧传感器板；若有样机，同时指向实物。",
        "next": "这些模块最终形成下一页的六类安全功能。",
    },
    {
        "title": "功能展示",
        "time": "1:55-2:11",
        "cue": "视觉  气体  补光  求救  心率血氧  疲劳",
        "say": "系统不只看疲劳。ESP32同步采集心率、血氧、有害气体和姿态，OpenMV提供视觉辅助；一旦脑电或环境异常，网页、语音和振动共同提醒。质量不合格的脑电会直接显示无效，避免把噪声误判成疲劳。",
        "point": "沿蓝色路径扫过六项功能，最后停在右下角疲劳值检测。",
        "next": "为了保护整套系统，我们也同步推进知识产权。",
    },
    {
        "title": "项目推进  知识产权",
        "time": "2:11-2:17",
        "cue": "三项软著  发明专利  技术保护",
        "say": "目前团队已经形成三项软件著作权，并推进发明专利，用知识产权保护采集、分析和预警链路。",
        "point": "从左到右快速扫过三张软著和专利材料。",
        "next": "项目同时接受了竞赛和大创项目的阶段检验。",
    },
    {
        "title": "项目推进  竞赛与立项",
        "time": "2:17-2:24",
        "cue": "国赛省赛  发明专利  国家级大创",
        "say": "项目已经获得竞赛成果，并完成发明专利和国家级大学生创新创业训练项目的阶段积累，说明团队在持续迭代一套可以运行的原型。",
        "point": "依次指向竞赛证书、发明专利和右侧大创项目页面。",
        "next": "在落地上，我们先从高风险岗位的小规模试点做起。",
    },
    {
        "title": "商业模式",
        "time": "2:24-2:32",
        "cue": "小规模试点  模块销售  平台服务",
        "say": "商业化先从矿山等高风险岗位的小规模试点开始，按硬件模块和管理平台收费，并通过维护、升级和数据分析形成后续服务。",
        "point": "指中间产品市场，再指右侧产品服务闭环。",
        "next": "早期资金也会围绕落地最需要的环节投入。",
    },
    {
        "title": "融资方案",
        "time": "2:32-2:37",
        "cue": "研发优先  小型化  测试认证",
        "say": "资金将优先投入产品小型化、现场测试和安全认证，再根据试点结果扩展生产与渠道。",
        "point": "重点指右侧资金用途，不详细朗读左侧股权比例。",
        "next": "我们的推进路线也遵循先验证、再试点、后规模化。",
    },
    {
        "title": "未来规划",
        "time": "2:37-2:44",
        "cue": "真人验证  行业试点  标准化  规模应用",
        "say": "下一步先完成真人佩戴验证和结构优化，再进入矿山、危化及长时间值守岗位试点，成熟后推进标准化和规模应用。",
        "point": "从下往上扫时间轴，不逐年照读。",
        "next": "最后回到我们最初想解决的问题。",
    },
    {
        "title": "结束页",
        "time": "2:44-2:50",
        "cue": "理解人  提醒人  主动安全",
        "say": "脑盾工坊希望在危险发生前理解人、提醒人，让安全从被动防护走向主动感知。谢谢各位评委老师。",
        "point": "看向评委，不再看屏幕，结束后停顿。",
        "next": "进入答辩。",
    },
]


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def borders(cell, color="D9D9D9", size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.first_child_found_in("w:tcBorders")
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = tc_borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            tc_borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def margins(cell, top=90, start=110, bottom=90, end=110):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn("w:" + side))
        if node is None:
            node = OxmlElement("w:" + side)
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_font(run, size=10.5, bold=False, color=BLACK):
    run.font.name = "Microsoft YaHei"
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def set_spacing(p, before=0, after=0, line=1.12):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line


def add_label_para(cell, label, text, label_color=BLACK, size=9.6, after=2):
    p = cell.add_paragraph()
    set_spacing(p, after=after, line=1.12)
    r = p.add_run(label)
    set_font(r, size=size, bold=True, color=label_color)
    r = p.add_run(text)
    set_font(r, size=size, color=BLACK)
    return p


def add_slide_block(doc, idx, data):
    h = doc.add_paragraph()
    set_spacing(h, before=1, after=4, line=1.0)
    r = h.add_run(f"第{idx}页  {data['title']}  {data['time']}")
    set_font(r, size=12.2, bold=True)

    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    left, right = table.rows[0].cells
    left.width = Inches(2.45)
    right.width = Inches(4.65)
    for cell in (left, right):
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        borders(cell)
        margins(cell)
    shade(left, PALE_BLUE)
    shade(right, "FFFFFF")

    p_img = left.paragraphs[0]
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.add_run().add_picture(str(SLIDE_DIR / f"slide-{idx:02}.jpg"), width=Inches(2.22))

    p0 = right.paragraphs[0]
    set_spacing(p0, after=3, line=1.0)
    r = p0.add_run("提示词  ")
    set_font(r, size=9.8, bold=True, color=ORANGE)
    r = p0.add_run(data["cue"])
    set_font(r, size=9.8, bold=True)
    add_label_para(right, "讲稿  ", data["say"], size=10.0, after=3)
    add_label_para(right, "指画面  ", data["point"], label_color=GRAY, size=8.7, after=2)
    add_label_para(right, "翻页  ", data["next"], label_color=RGBColor(32, 91, 145), size=8.7, after=0)

    spacer = doc.add_paragraph()
    set_spacing(spacer, after=1, line=0.8)


doc = Document()
section = doc.sections[0]
section.page_width = Cm(21.0)
section.page_height = Cm(29.7)
section.top_margin = Cm(1.35)
section.bottom_margin = Cm(1.25)
section.left_margin = Cm(1.45)
section.right_margin = Cm(1.45)

styles = doc.styles
styles["Normal"].font.name = "Microsoft YaHei"
styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
styles["Normal"].font.size = Pt(10.5)
title_style_ppr = styles["Title"]._element.get_or_add_pPr()
title_style_border = title_style_ppr.find(qn("w:pBdr"))
if title_style_border is not None:
    title_style_ppr.remove(title_style_border)

title = doc.add_paragraph(style="Title")
title.alignment = WD_ALIGN_PARAGRAPH.LEFT
set_spacing(title, after=8, line=1.0)
ppr = title._p.get_or_add_pPr()
pbdr = ppr.find(qn("w:pBdr"))
if pbdr is not None:
    ppr.remove(pbdr)
r = title.add_run("脑盾工坊 iCAN 16页PPT逐页讲稿")
set_font(r, size=25, bold=True)

sub = doc.add_paragraph()
set_spacing(sub, after=18, line=1.0)
r = sub.add_run("配套 ican.pptx  每页有提示词  讲稿  指画面位置和翻页衔接")
set_font(r, size=11, color=GRAY)

h = doc.add_paragraph()
set_spacing(h, after=5)
r = h.add_run("使用方法")
set_font(r, size=15, bold=True)
for text in (
    "整篇按2分50秒设计，现场停顿和指画面后约为3分钟。",
    "忘词时先看橙色提示词，再用自己的话复述讲稿，不必逐字背诵。",
    "第5页借硬件控制引出FPGA；第6至8页说明ViFormerNet是研究参考，当前板端采用八通道DE加HGB。",
    "第9页可直接说：DE特征由ARM约83毫秒降到FPGA的1毫秒以内，至少提升80倍；HGB硬件推理约17微秒。",
    "第8页的PCC 0.9214和约90%准确率属于公开研究基准，不能表述为当前样机真人准确率。",
):
    p = doc.add_paragraph(style="List Bullet")
    set_spacing(p, after=5, line=1.18)
    set_font(p.add_run(text), size=10.6)

h = doc.add_paragraph()
set_spacing(h, before=10, after=5)
r = h.add_run("整场故事线")
set_font(r, size=15, bold=True)
p = doc.add_paragraph()
set_spacing(p, after=0, line=1.25)
set_font(p.add_run("矿井中人的疲劳难以被发现。团队先在电脑端验证算法，再把质控、特征和推理迁移到Zynq，通过ESP32和OpenMV连接环境感知、网页显示与本地告警，最终形成可持续运行的安全闭环。"), size=11)

doc.add_page_break()

for i in range(1, 17):
    if i % 2 == 1:
        h = doc.add_paragraph()
        set_spacing(h, after=6, line=1.0)
        r = h.add_run(f"第{i}至{min(i + 1, 16)}页逐页讲稿")
        set_font(r, size=16, bold=True)
    add_slide_block(doc, i, slides[i - 1])
    if i % 2 == 0 and i != 16:
        doc.add_page_break()

doc.add_page_break()
h = doc.add_paragraph()
set_spacing(h, after=8)
set_font(h.add_run("一页速记卡"), size=18, bold=True)
p = doc.add_paragraph()
set_spacing(p, after=8)
set_font(p.add_run("忘词时只看每页编号后的关键词。"), size=10.5, color=GRAY)

quick = doc.add_table(rows=8, cols=2)
quick.alignment = WD_TABLE_ALIGNMENT.CENTER
quick.autofit = False
for row in range(8):
    for col in range(2):
        idx = row + 1 + col * 8
        cell = quick.cell(row, col)
        cell.width = Inches(3.55)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        borders(cell)
        margins(cell, top=110, bottom=110)
        shade(cell, "FFFFFF" if row % 2 == 0 else PALE_GRAY)
        p = cell.paragraphs[0]
        set_spacing(p, line=1.08)
        r = p.add_run(f"{idx}  {slides[idx - 1]['title']}\n")
        set_font(r, size=9.8, bold=True)
        r = p.add_run(slides[idx - 1]["cue"])
        set_font(r, size=9.1, color=GRAY)

for sec in doc.sections:
    footer = sec.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_spacing(p, line=1.0)
    set_font(p.add_run("脑盾工坊  iCAN逐页答辩词稿"), size=8.2, color=GRAY)

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(OUT)
