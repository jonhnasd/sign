# -*- coding: utf-8 -*-
"""读取三家固定货源素材库：按 pno / 名称关键词 / 来源 / 形态检索，只输出少量行。

用途（解决 AI 直接读 JSON 慢）：
  货源商品清单.json 有 12.5 万行、货源素材_详情.json 有 4.7 万行，
  Read 工具会被 2000 行截断，整份塞进上下文也不可行。
  本脚本是唯一推荐入口：进程内加载一次（约 0.13 s），按需输出几行。

固定字段（本地查）：来源#pno、商品名、形态、商品图、介绍、弹窗/购买须知、充值表单、接口网址。
易变字段（不落表，上架现场取）：进价、库存、可售、余额、限价 —— 本脚本不提供，也不许据此定价。

用法：
  python query_supplier_assets.py --pno 1220
  python query_supplier_assets.py --pno 1220 --source 志远 --full
  python query_supplier_assets.py --keyword 剪映 --limit 10
  python query_supplier_assets.py --keyword 剪映 --keyword SVIP --source 志远 --form 直充
  python query_supplier_assets.py --pno 1220 --show intro --chars 600
  python query_supplier_assets.py --stats
  python query_supplier_assets.py --keyword 剪映 --json --limit 5
  python query_supplier_assets.py --write-digest

输出约定：
  默认紧凑表格，每行一条；素材列是齐备短码 G(图) I(图集) T(介绍) N(须知) F(充值表单)。
  --show 只对单条生效，把 HTML 转纯文本后截断，避免把长正文灌进上下文。
  --json 给其他脚本调用；--write-digest 生成 AI 可整读的 货源素材/AI速查表.md。

依赖：仅标准库；数据源目录默认 Obsidian 货源素材/，可用 --dir 覆盖。
只读：不写数据源 JSON，不调用任何线上接口，不自动上品。
"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_DIR = Path(r"C:\Users\Administrator\Desktop\obisidian\obisidian\货源素材")
LIST_FILE = "货源商品清单.json"
ASSET_FILE = "货源素材_详情.json"
DIGEST_FILE = "AI速查表.md"
FIELDS = (("G", "img"), ("I", "imgs"), ("T", "intro_html"),
          ("N", "notice_html"), ("F", "popup_fields"))
SOURCES = ("志远", "商战", "思券")


def _has(v):
    if v is None:
        return False
    if isinstance(v, (list, dict, tuple)):
        return len(v) > 0
    return str(v).strip() not in ("", "[]", "{}", "None", "null", "0", "False")


def _plain(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    s = str(v or "")
    s = re.sub(r"<(?:br|/p|/div|/li|/tr|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def load(dirpath, with_assets=True):
    lp = dirpath / LIST_FILE
    if not lp.exists():
        raise SystemExit("找不到清单：%s（先跑 fetch_supplier_assets.py）" % lp)
    lst = json.loads(lp.read_text(encoding="utf-8"))
    items = lst.get("items") or []
    idx = {(x["source"], str(x["pno"])): x for x in items}
    assets = {}
    ap = dirpath / ASSET_FILE
    if with_assets and ap.exists():
        for a in (json.loads(ap.read_text(encoding="utf-8")).get("items") or []):
            if not a.get("_err"):
                assets[(a["source"], str(a["pno"]))] = a
    return items, idx, assets, lst.get("抓取时间", "")


def flags(item, asset):
    if not asset:
        return "无素材"
    s = ""
    for code, key in FIELDS:
        v = asset.get(key)
        if code == "G" and not _has(v):
            v = item.get("img")     # 清单里的主图也算
        s += code if _has(v) else "-"
    return s


def row(item, asset, full=False):
    k = (item["source"], str(item["pno"]))
    base = {
        "来源#pno": "%s#%s" % k,
        "形态": item.get("form") or "",
        "名称": item.get("name") or "",
        "素材": flags(item, asset),
    }
    if full:
        base["主图"] = item.get("img") or ""
        base["账号"] = item.get("acct") or ""
        base["素材字段"] = ",".join(sorted(asset.keys())) if asset else "无"
    return base


def pick(args, items, idx, assets):
    if args.pno:
        pnos = []
        for chunk in args.pno:
            pnos.extend(str(p).strip() for p in chunk.split(",") if str(p).strip())
        out = [x for x in items if str(x["pno"]) in set(pnos)]
    else:
        out = items
    if args.source:
        out = [x for x in out if x["source"] in args.source]
    if args.form:
        out = [x for x in out if x["form"] in args.form]
    if args.keyword:
        kws = [k.strip() for k in args.keyword if k.strip()]
        if args.match == "all":
            out = [x for x in out if all(k in (x.get("name") or "") for k in kws)]
        else:
            out = [x for x in out if any(k in (x.get("name") or "") for k in kws)]
    return out


def stats(items, assets):
    by = {}
    for x in items:
        k = (x["source"], x["form"])
        by[k] = by.get(k, 0) + 1
    cover = {}
    for src in SOURCES:
        tot = sum(1 for x in items if x["source"] == src)
        n = sum(1 for k in assets if k[0] == src)
        cover[src] = (tot, n, (100.0 * n / tot if tot else 0))
    return by, cover


def print_stats(items, assets, ts):
    by, cover = stats(items, assets)
    print("数据时间: %s | 清单 %d 条 | 有效素材 %d 条" % (ts or "未知", len(items), len(assets)))
    print("%-6s %-6s %8s" % ("来源", "形态", "条数"))
    for k in sorted(by):
        print("%-6s %-6s %8d" % (k[0], k[1], by[k]))
    print("%-6s %8s %10s %8s" % ("来源", "清单", "有素材", "覆盖率"))
    for src in SOURCES:
        t, n, p = cover[src]
        print("%-6s %8d %10d %7.1f%%" % (src, t, n, p))
    print("合计覆盖率 %.1f%%" % (100.0 * len(assets) / len(items) if items else 0))


def show_detail(hit, asset, what, chars):
    if not asset:
        print("该 pno 暂无详情素材（清单可查，介绍/弹窗需现场抓或补预热）。")
        return
    keys = {"intro": ["intro_html"], "notice": ["notice_html"],
            "popup": ["popup_fields", "card_option"],
            "imgs": ["imgs", "img", "recharge_url", "demo_url"],
            "all": ["intro_html", "notice_html", "popup_fields",
                    "card_option", "imgs", "img"]}
    for key in keys[what]:
        v = asset.get(key)
        txt = _plain(v)
        if not txt:
            continue
        if len(txt) > chars:
            txt = txt[:chars] + " …(截断，--chars 调整)"
        print("--- %s ---" % key)
        print(txt)
    print("--- 提示 ---")
    print("以上是货源内部原文：转买家文案前须过脱敏，删除货源编号、供应商名、网站/域名及到账时效承诺词；价格库存仍须现场取。")


def write_digest(dirpath, items, assets, ts):
    by, cover = stats(items, assets)
    q = str(Path(__file__).resolve()).replace("\\", "/")
    py = sys.executable.replace("\\", "/")
    L = []
    a = L.append
    today = time.strftime("%Y-%m-%d")
    a("---")
    a("created: 2026-11-13")
    a("updated: %s" % today)
    a("tags: [货源, 素材库, AI速查]")
    a("type: 索引")
    a("status: active")
    a("---")
    a("")
    a("# AI 速查 · 三家货源固定素材库")
    a("")
    a("> [!warning] 不要直接 Read 两个 JSON")
    a("> `货源商品清单.json` 12.5 万行 / `货源素材_详情.json` 4.7 万行，Read 会在 2000 行处截断。")
    a("> 本文件可整份读进上下文；查任何商品一律调 `query_supplier_assets.py`。")
    a("")
    a("生成时间：%s ｜ 数据时间：%s ｜ 清单 **%d** 条 ｜ 有效详情素材 **%d** 条 ｜ 只读、不联网、不写线上" %
      (time.strftime("%Y-%m-%d %H:%M:%S"), ts or "未知", len(items), len(assets)))
    a("> 自动维护：每次跑 `fetch_supplier_assets.py` 入库后会自动重建本表；也可手动 `--write-digest`。")
    a("")
    a("## 规模与覆盖率")
    a("")
    a("| 来源 | 卡密 | 直充 | 合计 | 有详情素材 | 覆盖率 |")
    a("|---|---:|---:|---:|---:|---:|")
    for src in SOURCES:
        ka = by.get((src, "卡密"), 0)
        zc = by.get((src, "直充"), 0)
        t, n, p = cover[src]
        a("| %s | %d | %d | %d | %d | %.1f%% |" % (src, ka, zc, t, n, p))
    a("")
    a("> 「查得到」≠「素材齐」：志远/商战详情只预热了候选池，命中后看 `素材` 短码。")
    a("")
    a("## 常用命令（可直接复制）")
    a("")
    a("```bash")
    a('PY="%s"' % py)
    a('Q="%s"' % q)
    a('"$PY" "$Q" --pno 1220                       # 精确查一个编号（跨三家）')
    a('"$PY" "$Q" --keyword 剪映 --limit 10         # 名称模糊搜，只出 10 行')
    a('"$PY" "$Q" --keyword 剪映 --source 志远 --form 直充')
    a('"$PY" "$Q" --pno 1220 --source 志远 --full  # 完整固定字段（含主图 URL）')
    a('"$PY" "$Q" --pno 1220 --show intro --chars 600   # 单条介绍正文，截断输出')
    a('"$PY" "$Q" --stats                          # 统计，零明细')
    a('"$PY" "$Q" --keyword 剪映 --json --limit 5  # 给其他脚本调用')
    a("```")
    a("")
    a("## 输出读法")
    a("")
    a("- `素材` 短码：**G** 主图 / **I** 图集 / **T** 介绍 / **N** 购买须知 / **F** 充值表单；`-` 表示缺，`无素材` 表示未预热。")
    a("- 默认 `--limit 20`；`--show` 只对单条生效，避免长 HTML 灌进上下文。")
    a("- 多关键词默认全部命中（`--match any` 改任一）；`--source/--form/--pno` 可叠加。")
    a("")
    a("## 红线")
    a("")
    a("- 本库只有**固定字段**：编号、名称、形态、图、介绍、弹窗、详情、接口网址。")
    a("- 进价、库存、可售、余额、限价**不在库里**，上架时现场取，不得用本库推算收益。")
    a("- 素材是货源内部原文，买家标题/描述/SKU 说明须脱敏，禁止出现货源编号、供应商名、网站/域名。")
    a("- 数据目录：`%s`；权威说明见库根 `项目-三家货源固定素材库.md`。" %
      str(dirpath).replace("\\", "/"))
    a("")
    p = dirpath / DIGEST_FILE
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def main():
    ap = argparse.ArgumentParser(description="读取三家固定货源素材库（只读、极小输出）")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="数据源目录")
    ap.add_argument("--pno", action="append", help="货源编号，可重复或逗号分隔")
    ap.add_argument("--keyword", action="append", help="商品名关键词，可重复")
    ap.add_argument("--match", choices=("all", "any"), default="all", help="多关键词逻辑")
    ap.add_argument("--source", action="append", choices=SOURCES, help="来源，可重复")
    ap.add_argument("--form", action="append", choices=("卡密", "直充"), help="形态，可重复")
    ap.add_argument("--limit", type=int, default=20, help="最多输出行数，默认 20，上限 200")
    ap.add_argument("--all", action="store_true", help="输出全部命中（慎用）")
    ap.add_argument("--full", action="store_true", help="输出完整固定字段（建议配合单条）")
    ap.add_argument("--show", choices=("intro", "notice", "popup", "imgs", "all"),
                    help="单条详情正文，按需截断")
    ap.add_argument("--chars", type=int, default=800, help="--show 每段最大字符数")
    ap.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    ap.add_argument("--stats", action="store_true", help="只输出统计")
    ap.add_argument("--write-digest", action="store_true", help="生成/更新 AI速查表.md")
    ap.add_argument("--no-assets", action="store_true", help="跳过素材联查（更快）")
    ap.add_argument("--time", action="store_true", help="打印本次耗时")
    args = ap.parse_args()

    t0 = time.perf_counter()
    dirpath = Path(args.dir)
    items, idx, assets, ts = load(dirpath, with_assets=not args.no_assets)

    if args.write_digest:
        p = write_digest(dirpath, items, assets, ts)
        print("已生成 %s（%d 字节，可整份读进上下文）" % (p, p.stat().st_size))
        return

    if args.stats:
        print_stats(items, assets, ts)
    elif args.show:
        hits = pick(args, items, idx, assets)
        if len(hits) != 1:
            raise SystemExit("--show 需要精确命中 1 条，当前 %d 条；请加 --pno/--source 收窄" % len(hits))
        h = hits[0]
        show_detail(h, assets.get((h["source"], str(h["pno"]))), args.show, args.chars)
    else:
        hits = pick(args, items, idx, assets)
        n = len(hits)
        lim = min(n, 2000) if args.all else min(args.limit, 200)
        rows = [row(x, assets.get((x["source"], str(x["pno"]))), args.full)
                for x in hits[:lim]]
        if args.json:
            print(json.dumps({"数据时间": ts, "命中": n, "显示": len(rows),
                              "items": rows}, ensure_ascii=False, indent=2))
        else:
            print("命中 %d 条，显示 %d 条%s ｜ 数据时间 %s" %
                  (n, len(rows), ("（--all）" if args.all else ""), ts or "未知"))
            if rows:
                cols = list(rows[0].keys())
                if args.full:
                    # 完整字段不截断（尤其主图 URL），改为单条多行
                    for r in rows:
                        for c in cols:
                            print("%s: %s" % (c, r[c]))
                        print("---")
                else:
                    print(" ｜ ".join(cols))
                    for r in rows:
                        print(" ｜ ".join(str(r[c])[:70] for c in cols))
            print("提示：正文 --pno X --show intro ｜ 完整字段 --full ｜ 统计 --stats ｜ 机器读 --json")
        if args.all and n > 200:
            print("⚠️ 全量输出 %d 行（硬上限 2000），可能撑大上下文；建议 --limit 或加关键词收窄" % n)

    if args.time:
        print("耗时 %.1f ms" % ((time.perf_counter() - t0) * 1000))


if __name__ == "__main__":
    main()
