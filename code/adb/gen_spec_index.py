# -*- coding: utf-8 -*-
"""生成《上品资料索引》—— spec 模板 + 上品结果记录 + 原始文档"""
import io
import os
import re
import json
import glob
import datetime

PROJ = r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41"
VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"
OUT = os.path.join(VAULT, "上品资料索引.md")


def read(p):
    return io.open(p, encoding="utf-8", errors="ignore").read()


def main():
    _today = datetime.date.today()
    L = []
    L.append("---")
    L.append("created: 2026-11-05")
    L.append("updated: " + _today.isoformat())
    L.append("tags: [上品, spec, 模板, 记录, 索引]")
    L.append("type: 索引")
    L.append("status: active")
    L.append("execution: read_only")
    L.append("verified_at: " + _today.isoformat())
    L.append("review_by: " + (_today + datetime.timedelta(days=90)).isoformat())
    L.append("---")
    L.append("")
    L.append("# 📦 上品资料索引")
    L.append("")
    L.append(f"> **自动生成，手改无效**（`tools/adb/gen_spec_index.py`）")
    L.append(f"> 源目录：`{PROJ}`")
    L.append("> 重新生成：`python C:/Users/Administrator/.workbuddy/tools/adb/gen_spec_index.py`")
    L.append("")
    L.append("> [!tip] 这两类资产最值钱")
    L.append("> **spec_*.json** = 一条龙的现成输入（SKU 定义 / 货源 / 利润率）—— 改改就能跑")
    L.append("> **上品结果-*.md** = 每次上品的**决策记录**（产品线怎么判定、档位怎么取舍、货源怎么选）")
    L.append("> 遇到新商品不知道怎么做时，**先翻上品结果找同类**，别从零想。")
    L.append("")

    # ── 1. spec 模板 ──
    specs = sorted(glob.glob(os.path.join(PROJ, "spec_*.json")))
    L.append("---")
    L.append("")
    L.append(f"## 📋 spec 模板（{len(specs)} 份）")
    L.append("")
    L.append("> `deploy.py spec.json --dry` 的输入文件。字段结构见下方「字段说明」。")
    L.append("")
    L.append("> [!warning] ⚠️ 老模板的货源/利润率口径已过期")
    L.append("> 现行口径（2026-11-11 同步）：**默认利润率 6.6%**（售价 = 进价 ÷ 0.934）、**禁止亏本档**；")
    L.append("> 货源池 = **志远 95425 / 商战 96810 / 思券 99569**（点名思券按指定走）；旧 `93310` 千城 / 省省 / 星芒 / 追梦已弃用。")
    L.append("> 标 🔴 的模板**结构可参考，但 `acct` 与成本必须重新核**；给了对标闲鱼链接时按各档照抄价，不套 6.6%。")
    L.append("")
    L.append("| 商品ID | 品类 | 属性维度 | 类型 | SKU数 | 货源账号 | 利润率 | 文件 |")
    L.append("|---|---|---|---|---|---|---|---|")
    CUR_ACCT = {"95425", "96810", "99569"}
    for p in specs:
        try:
            d = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            L.append(f"| — | — | — | — | — | — | — | `{os.path.basename(p)}` |")
            continue
        skus = d.get("skus") or []
        profit = d.get("profit")
        profit_s = str(profit) if profit is not None else "—"
        if isinstance(profit, dict):
            profit_s = "/".join(str(v) for v in list(profit.values())[:2])
        acct = str(d.get("acct", "—"))
        # 非现行货源 → 🔴 标记
        mark = "" if acct in CUR_ACCT else "🔴 "
        L.append(
            f"| {mark}{d.get('goods','—')} | {d.get('var_name') or d.get('category') or '—'} "
            f"| {d.get('property','—')} | {d.get('type','—')} | {len(skus)} "
            f"| {acct} | {profit_s} | `{os.path.basename(p)}` |"
        )
    L.append("")
    L.append("**🔴 = 非现行货源账号（`93310` 等已弃用），`acct` 须改为 95425 / 96810 / 99569 之一并重比成本。**")
    L.append("")
    L.append("### 字段说明")
    L.append("")
    L.append("| 字段 | 含义 | 注意 |")
    L.append("|---|---|---|")
    L.append("| `goods` | 目标商品 ID | — |")
    L.append("| `template_goods` | 克隆的模板商品 ID | 用来拿默认字段，**别改** |")
    L.append("| `property` | 规格维度名（如「时长」「面额」） | 最多 2 个维度 |")
    L.append("| `type` | `fixed` / `range` 等 | 决定档位怎么算 |")
    L.append("| `var_key` / `var_name` / `var_value` | 货源参数三元组 | ⚠️ 键名必须与货源接口一致 |")
    L.append("| `spType` | 销售类型 | 账号型=4 / 直充=3；卡密型 SKU 级 `spType=6, productType=2`、`sendTypeOption=28` |")
    L.append("| `ppt` | 是否同步订单金额 | 旧「首单档设 1」口径已取消，现行全档 `ppt=2` |")
    L.append("| `acct` | alds 供货商账号 ID | **志远 95425 / 商战 96810 / 思券 99569** |")
    L.append("| `profit` | 加价率 / 利润率 | 省略即 **6.6%**；低价引流档仍须 ≥ 进价，**无亏本档** |")
    L.append("| `autoprice_skip` | 关自动改价的档名 | 照抄链接价时须覆盖全部档名，只写 `autoprice:false` 无效 |")
    L.append("| `skus` | SKU 档位数组 | 每档含名称 / 价格 / 成本 |")
    L.append("")

    # ── 2. 上品结果记录 ──
    results = sorted(glob.glob(os.path.join(PROJ, "上品结果-*.md")))
    L.append("---")
    L.append("")
    L.append(f"## 📝 上品结果记录（{len(results)} 份）")
    L.append("")
    L.append("> 每次上品的**完整决策过程** —— 含产品线判定、档位取舍、货源比价。")
    L.append("> 复用时先在这里找同类。")
    L.append("")
    L.append("| 日期 | 商品 | ID | 类型 | 维度 | SKU数 | 货源 |")
    L.append("|---|---|---|---|---|---|---|")
    for p in results:
        s = read(p)
        fn = os.path.basename(p)
        m = re.search(r'上品结果[·-](.+?)-(\d{13})-\d{8}\.md$', fn)
        if not m:
            m2 = re.search(r'上品结果[·-](.+?)-\d{8}\.md$', fn)
            name = m2.group(1) if m2 else fn.replace("上品结果-", "").replace(".md", "")
            gid = "—"
        else:
            name, gid = m.group(1), m.group(2)
        # 从正文抽字段
        t = re.search(r'\*\*类型\*\*：([^\s｜|]+)', s)
        dim = re.search(r'\*\*维度名\*\*：([^\s｜|]+)', s)
        n = re.search(r'\*\*SKU 数\*\*：(\d+)', s)
        src = re.search(r'\*\*货源\*\*：([^\n]+)', s)
        dt = re.search(r'\*\*时间\*\*：([\d\- ]+)', s)
        L.append(
            f"| {dt.group(1).strip() if dt else '—'} | {name} | {gid} "
            f"| {t.group(1) if t else '—'} | {dim.group(1) if dim else '—'} "
            f"| {n.group(1) if n else '—'} | {(src.group(1).strip()[:26] if src else '—')} |"
        )
    L.append("")

    # ── 3. 原始文档 ──
    docs = []
    for p in glob.glob(os.path.join(PROJ, "*.md")):
        fn = os.path.basename(p)
        if fn.startswith("上品结果-"):
            continue
        if re.match(r'^(SKU|双维度|引流价|文案清理|晋江币|阿木文娱|喜柿卡卷)', fn):
            continue
        if re.search(r'\d{8}-\d{4}\.md$', fn):
            continue
        docs.append(p)
    L.append("---")
    L.append("")
    L.append(f"## 📄 原始文档（{len(docs)} 份）")
    L.append("")
    L.append("| 文档 | 首行摘要 |")
    L.append("|---|---|")
    for p in sorted(docs):
        s = read(p)
        first = ""
        for ln in s.split("\n")[:8]:
            ln = ln.strip().lstrip("# ").strip()
            if ln and not ln.startswith("-"):
                first = ln[:56]
                break
        L.append(f"| `{os.path.basename(p)}` | {first} |")
    L.append("")

    # ── 4. 其它数据文件 ──
    extras = []
    for pat in ("*.json", "*.xlsx"):
        for p in glob.glob(os.path.join(PROJ, pat)):
            fn = os.path.basename(p)
            if fn.startswith("spec_") or fn.startswith("backup_") or fn.startswith("x_source"):
                continue
            extras.append(p)
    L.append("---")
    L.append("")
    L.append(f"## 📦 其它数据文件（{len(extras)} 份）")
    L.append("")
    L.append("> 快照 / 导出 / 中间产物 —— 出问题时的回溯依据。")
    L.append("")
    L.append("| 文件 | 大小 |")
    L.append("|---|---|")
    for p in sorted(extras)[:40]:
        L.append(f"| `{os.path.basename(p)}` | {os.path.getsize(p)//1024} KB |")
    if len(extras) > 40:
        L.append(f"| … 另有 {len(extras)-40} 份 | |")
    L.append("")

    L.append("---")
    L.append("")
    L.append("## 🔗 相关")
    L.append("")
    L.append("- [[操作-阿奇索上品一条龙]] —— 主流程（吃 spec.json）")
    L.append("- [[项目-剪映主图与商品补全]] —— 端到端实跑（主图上传 / 空壳补全 / 标题 / 四个坑）")
    L.append("- [[脚本索引]] —— 706 个脚本")
    L.append("- [[操作层规范]] —— 写笔记必带「🚀 快速开始」")
    L.append("")

    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print(f"✓ 已生成 {OUT}")
    print(f"  spec {len(specs)} / 上品结果 {len(results)} / 原始文档 {len(docs)} / 数据文件 {len(extras)}")


if __name__ == "__main__":
    main()
