---
created: 2026-11-10
updated: 2026-11-10
tags: [操作层, PPT, pptx, Skill, 文档产出]
type: 操作
status: active
execution: read_only
verified_at: 2026-11-14
review_by: 2027-02-14
---

# 操作-用 Agent Skill 做 PPT（pptx skill）

> [!info] 来源与许可
> 官方仓库 `anthropics/skills` → `skills/pptx`，SKILL.md 声明 `license: Complete terms in LICENSE.txt`（Apache-2.0）。
> 2026-11-10 下载安装到 `C:\Users\Administrator\.workbuddy\skills\pptx\`（用户级 skill，全项目可用）。
> 配套本机说明：`~/.workbuddy/skills/pptx/本机使用说明.md`

---

## 🚀 快速开始

> [!note] 一句话
> 用 `pptx` skill 做 / 改 .pptx，交付前必跑「校验 + 渲染」两步；本机无 LibreOffice，渲染用自建的 `render_qa.py`。

### 前置条件

- WorkBuddy 默认 Python：`C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
- 已装（2026-11-10 验证）：`pptxgenjs`（npm，**已拷到 `C:\node_modules`**）、`python-pptx`、`markitdown[pptx]`、`defusedxml`、`lxml`、`Pillow`、`pymupdf`、`pywin32`
- 已装：WPS Office（`KWPP.Application` COM 可用，用于导 PDF）
- ❌ 本机**没有** LibreOffice / Poppler → 上游 `soffice.py`、`pdftoppm`、`thumbnail.py` 全都跑不通

### 一键入口

```bash
SKILL="C:/Users/Administrator/.workbuddy/skills/pptx"
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 1. 新建：写 pptxgenjs 脚本（先看 SKILL.md 的 10 条避坑规则）
node xxx.js

# 2. 校验（改完必跑）
$PY "$SKILL/scripts/office/validate.py" deck.pptx

# 3. 渲染 QA（改完必跑，PDF/PNG 会同步刷新）
$PY "$SKILL/scripts/render_qa.py" deck.pptx --out-dir qa --labels
```

### 预期输出

```
# validate.py
All validations PASSED!        # 退出码 0 = 结构没问题

# render_qa.py
[OK] PDF 导出：C:/path/qa/deck.pdf
[OK] 渲染 N 页 PNG → C:/path/qa
     网格总览：C:/path/qa/_grid.png
     带标签网格：C:/path/qa/_grid_labeled.png
[下一步] 逐张看 PNG：查中文错别字、溢出/重叠、留白不足、Logo 变形
```

---

## 一、三条路线怎么选

| 任务 | 路线 |
|---|---|
| 新建 PPT | 写 `pptxgenjs` 脚本 |
| 改已有 PPT / 套模板 | 解压 → 改 `ppt/slides/slideN.xml` → 重新打包 |
| 只读内容 | `markitdown deck.pptx`（按 `<!-- Slide number: N -->` 分块） |

---

## 二、上游 10 条 pptxgenjs 避坑（**写错不报错，直接静默损坏文件**）

| 坑 | 正确写法 |
|---|---|
| 布局宽度 | `LAYOUT_16x9` = 10″×5.625″，**不是 13.3″**；要宽屏用 `LAYOUT_WIDE`（13.3×7.5）。超界坐标不报错，图形直接不显示 |
| hex 颜色 | **不能带 `#`、不能 8 位** → `color:"FF0000"`。`"#FF0000"` 和 8 位含 alpha 都会**损坏文件**。半透明用 `transparency:0-100` |
| 选项对象会被改写 | pptxgenjs 会把值就地转成 EMU。**绝不能共用同一个 `shadow`/options 对象**给两个 `add*` 调用 |
| 阴影 offset | **必须 ≥ 0**，负值损坏文件。向上投影用 `angle:270` + 正 offset |
| 字间距 | `letterSpacing` 是哑的，真选项叫 **`charSpacing`** |
| 项目符号 | 用 `bullet:true`，**别手写 `•`**（会出双符号）；除最后一项外每项加 `breakLine:true`；段距用 `paraSpaceAfter` 不是 `lineSpacing` |
| 实例复用 | **一个 `new pptxgen()` 对应一个输出文件**，不要复用 |
| 圆角 | `rectRadius` **只对 `ROUNDED_RECTANGLE` 生效**，`RECTANGLE` 无效 |
| 渐变/透明 | `transparency` 只对 fill 和 image 生效，`opacity` 只对 shadow 生效，**互不通用** |

---

## 三、QA 闭环（交付前必做，不可省）

```bash
# 改完 pptx → 重新校验
$PY "$SKILL/scripts/office/validate.py" deck.pptx
# 套模板生成的必须加 --original，否则模板自身的 XSD 错误会算到你头上
$PY "$SKILL/scripts/office/validate.py" deck.pptx --original template.pptx

# 渲染 → 逐张看图
$PY "$SKILL/scripts/render_qa.py" deck.pptx --out-dir qa --labels
```

**看图要查的 5 项**：
1. 中文错别字 / 乱码方块（放大 200% 逐字核对）
2. 文字溢出框、元素重叠
3. 留白不足（拥挤）
4. Logo / 图形变形
5. 整组风格是否统一（看 `_grid.png`）

> ⚠️ **PDF/PNG 不会自动刷新**，改完 pptx 必须重跑 `render_qa.py`。

---

## 四、本机适配：为什么不用上游的 soffice + pdftoppm

上游标准链路是 `soffice --headless --convert-to pdf` → `pdftoppm -jpeg`。
本机两者都没有，`scripts/thumbnail.py` 更会因为 `socket.AF_UNIX`（Linux 专有）直接报错。

**替代方案（本机新增 `scripts/render_qa.py`）**：

```
WPS COM (KWPP.Application)  →  PDF
PyMuPDF (pymupdf)           →  逐页 PNG
Pillow                     →  _grid.png + _grid_labeled.png（带 slideN.xml 标签）
```

| 上游写法 | 本机改成 |
|---|---|
| `python scripts/office/soffice.py --headless --convert-to pdf deck.pptx` | `python scripts/render_qa.py deck.pptx --out-dir qa --labels` |
| `pdftoppm -jpeg -r 150 output.pdf slide` | 同上（脚本内自动） |
| `python scripts/thumbnail.py deck.pptx [prefix]` | 同上 → `qa/_grid_labeled.png` |

**上游脚本在本机的可用性**：

| 脚本 | 可用 | 备注 |
|---|---|---|
| `scripts/office/validate.py` | ✅ | 退出码 0 = 全过 |
| `scripts/add_slide.py` | ✅ | 见下方正确用法 |
| `scripts/clean.py` | ✅ | 必须在 `sldIdLst` 定稿后跑 |
| `scripts/office/soffice.py` | ❌ | 无 LibreOffice |
| `scripts/thumbnail.py` | ❌ | 用 `render_qa.py --labels` 代替 |

---

## 五、add_slide.py 正确用法

```bash
# 复制第 2 页到新文件
python scripts/add_slide.py deck.pptx slide2.xml -o out.pptx
# 从版式建新页
python scripts/add_slide.py deck.pptx slideLayout3.xml -o out.pptx
# 插到指定页之后
python scripts/add_slide.py deck.pptx slide2.xml --after slide1.xml -o out.pptx
```

成功后新页是 `ppt/slides/slideN.xml`，**要改内容得先解压**。

---

## 六、本机专属坑

| 坑 | 症状 | 解法 |
|---|---|---|
| `require('pptxgenjs')` 找不到 | MODULE_NOT_FOUND | 本机 `npm install -g` 装到的是 node 运行时目录（`~/.workbuddy/binaries/node/versions/22.22.2-6/node_modules`），**不在任何工作目录的祖先链上** → 全局装了 ≠ 能 require。已把包**拷到 `C:\node_modules`**（Node 逐级向上找到盘根），任意目录可 require |
| NODE_PATH 不可靠 | 设了用户级 NODE_PATH 但新 shell 读不到 | WorkBuddy 的 Bash 会话不继承用户级环境变量。别依赖 NODE_PATH，靠 `C:\node_modules` 的物理位置 |
| `/tmp` 路径歧义 | 文件写到 `C:\tmp\` 而不是 `%TEMP%` | node 脚本里**一律用 Windows 绝对路径**（`C:/tmp/xxx.pptx`） |
| WPS 残留进程 | 后台一堆 wpp.exe | 每次 `Presentations.Open` 后必须 `Close()` + `app.Quit()` |
| 渲染字体差异 | WPS 渲染宽度 ≠ 真实 PowerPoint | 文字溢出以「放大 200% 逐字核对」为准，别只信渲染图 |
| `validate.py` 误报 | 套模板后报一堆 schema 错 | 加 `--original template.pptx` 做基线比对 |

---

## 七、和 `workbuddy-pptx` 的分工

| 工具 | 定位 | 何时用 |
|---|---|---|
| `pptx`（本 skill） | 产出**文件**，pptxgenjs / XML，有完整 QA 闭环 | 要交付 .pptx、要套模板、要校验 |
| `workbuddy-pptx`（WorkBuddy 内置） | 走 `editor_sdk` 驱动**本地 Office/WPS 实时文档**，所见即所得 | 改已有 PPT、要在编辑器里实时看效果 |

**可配合**：workbuddy-pptx 出初稿 → 本 skill 跑 `validate.py` + `render_qa.py` 做交付前 QA。

---

## 相关

- [[项目-edge-bridge]] · [[操作层规范]] · [[脚本索引]]
- Skill 目录：`~/.workbuddy/skills/pptx/`（含 `本机使用说明.md`）
