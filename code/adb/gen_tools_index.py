# -*- coding: utf-8 -*-
"""生成《脚本索引》笔记 —— 按用途分类，标注失效与高频"""
import io
import os
import re
import json
import glob
import datetime

TOOLS = r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41"
# 🔴 2026-11-15：知识库自身的检查/生成器在 `.workbuddy/tools/adb`，原先不在扫描范围，
#    导致 `check_vault.py` / `check_doc_code.py` / 本脚本自己都查不到 —— 「索引里没有，
#    新对话就发现不了」，正是索引存在的意义。现在两个根都扫。
ROOTS = [TOOLS, r"C:\Users\Administrator\.workbuddy\tools\adb"]
# 🔴 2026-11-15：原 TOOLS 只指到 `edge-bridge`，但历史脚本有一批散在任务目录根
#    （如 `pipeline_rest_jiuxiu.py`、`dump_alds_raw.py`）和 `qcqcq/`、`sku/`、`cdp/`，
#    只扫 edge-bridge 会让这些真实存在的脚本在索引里查不到、看起来"失效"。
SKIP_DIR = re.compile(r"node_modules|__pycache__|[\\/]_bak[^\\/]*[\\/]|backups_over1000|[\\/]\.git[\\/]")
VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"
OUT = os.path.join(VAULT, "脚本索引.md")

# ── 分类规则：先看中文说明，再看文件名 ──
# (类别, 说明关键词正则, 文件名正则)
RULES = [
    ("🏃 主流程", r"一条龙|完整跑通|全流程|端到端", r"deploy|pipeline|finish_9|_pipeline_9"),
    ("🔍 探测/读取", r"探|读取|拉取|查看|列出|扫|看看|现状|检查是否|确认是否", r"^_?(probe|read|dump|peek|scan|list|cap|get|fetch|show|search|find|enum|mtop)|^_(dump|read|probe|peek|scan|list|cap)_"),
    ("✏️ 配置/写入", r"配|设置|建|加|改|写|注入|上传|替换|追加|重建|保存|同步", r"^_?(set|add|build|config|update|upd|insert|create|write|save|fill|copy|rebuild|reprice|hy_|kb_|spec_)"),
    ("✅ 校验/核对", r"校验|核对|比对|对照|审计|验证|检查|一致|漂移|异常", r"^_?(verify|check|audit|compare|cmp|diff|tt_|_check_|_verify_|_audit_|_cmp_|_diff_)"),
    ("↩️ 回滚/清理", r"回滚|撤销|删除|清理|恢复|下架|还原", r"^_?(restore|revert|del|delete|clean)|_del_|_restore_|delisted"),
    ("🔐 登录/认证", r"登录|认证|授权|二维码|token|cookie|会话", r"login|auth|qr|_ssyq_capture|token"),
    ("🌐 抓外部站", r"抓取|爬|解析|签名|余额|货源|思券|逗点|点卡", r"qcqcq|sqqy88|siquan|_91kami|qqkami|sup12|xmang|balance|mtop|mt_|_zy_"),
    ("🩺 调试诊断", r"调试|排查|诊断|试|对比一下|探查|探索", r"^_?(dbg|diag|explore|research|test_)"),
]

# 高频脚本（正文明确提到的 = 重要）
KEY = {
    "deploy.py": "一条龙唯一入口（14 环节，含主图）",
    "restore_from_snapshot.py": "回滚",
    "_set_first_stock.py": "首单库存批量改",
    "_add_first_sku.py": "追加首单引流档",
    "_add_first_sku_direct.py": "追加首单（直连版）",
    "fix_platform_price_type.py": "修平台价格类型",
    "read_goofish_item.py": "读源商品 SKU",
    "probe_target.py": "读目标现状 + 自动备份",
    "check_min_quantity.py": "起充量巡检",
    "list_goods.py": "拉商品列表",
    "bridge.py": "桥接客户端基类",
    "balance_query.py": "省省/星芒余额",
    "sup12_client.py": "追梦客户端（SHA1）",
    "xianyu_sku_lib.py": "SKU 公共库",
}


def classify(name, doc):
    d = doc or ""
    for cat, dpat, npat in RULES:
        if re.search(dpat, d) or re.search(npat, name.lower()):
            return cat
    return "📦 其它"


def main():
    files = []
    skipped_bak = 0
    for _root in ROOTS:
        for ext in ("*.py", "*.mjs"):
            for p in glob.glob(os.path.join(_root, "**", ext), recursive=True):
                if SKIP_DIR.search(p):
                    if re.search(r"[\\/]_bak", p):
                        skipped_bak += 1
                    continue
                files.append(p)
    files = sorted(set(files))
    # 同名只留路径最短的那份（= 正式位置），并在下面报告被合并的份数
    by_name = {}
    for p in files:
        n = os.path.basename(p)
        if n not in by_name or len(p) < len(by_name[n]):
            by_name[n] = p
    merged = len(files) - len(by_name)
    files = sorted(by_name.values())
    items = []
    for p in files:
        name = os.path.basename(p)
        try:
            s = io.open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        # docstring 优先
        doc = ""
        m = re.search(r'"""(.*?)"""', s[:4000], re.S)
        if m:
            doc = " ".join(m.group(1).strip().split("\n"))
        if not doc:
            ls = []
            for ln in s.split("\n")[:40]:
                ln = ln.strip()
                if ln.startswith("#") and re.search(r'[\u4e00-\u9fff]', ln):
                    ls.append(ln.lstrip("# ").strip())
            doc = " ".join(ls[:2])
        # 截到第一个句号/换行
        doc = re.split(r'[。\n]|\s{2,}', doc.strip())[0].strip()
        args = re.findall(r'add_argument\(\s*["\']([^"\']+)["\']', s)
        # 复用性判定：文件名绑死具体商品ID/日期 = 一次性
        oneoff = bool(re.search(r"_[0-9]{10,}|_[0-9]{4}-[0-9]{2}-[0-9]{2}", name))
        items.append({
            "name": name,
            "cat": classify(name, doc),
            "doc": doc[:100],
            "args": args[:5],
            "oneoff": oneoff,
            "mtime": datetime.date.fromtimestamp(os.path.getmtime(p)).isoformat(),
        })

    # 🔴 2026-11-15：清理「原表有、磁盘已无」的失效条目，并显式报数量。
    #    生成器是整表重写，失效条目本来会被自然清掉，但**没人知道清了什么** ——
    #    实测原表有 95 条此类条目（13%），长期无人发现，因为检查器把自动生成文件豁免了。
    old_names = []
    if os.path.exists(OUT):
        old_names = re.findall(r"^\|\s*(?:🔴\s*)?`([^`]+)`\s*\|",
                               io.open(OUT, encoding="utf-8").read(), re.M)
    new_names = {i["name"] for i in items}
    removed = [n for n in dict.fromkeys(old_names) if n not in new_names]

    # 输出
    _today = datetime.date.today()
    L = []
    L.append("---")
    L.append("created: 2026-11-05")
    L.append("updated: " + _today.isoformat())
    L.append("tags: [脚本, 索引, 工具, edge-bridge]")
    L.append("type: 索引")
    L.append("status: active")
    L.append("execution: read_only")
    L.append("verified_at: " + _today.isoformat())
    L.append("review_by: " + (_today + datetime.timedelta(days=90)).isoformat())
    L.append("---")
    L.append("")
    L.append("# 📇 脚本索引")
    L.append("")
    L.append(f"> **自动生成，手改无效**（`tools/adb/gen_tools_index.py`），共 **{len(items)}** 个脚本。")
    L.append(f"> 目录：`{TOOLS}` + `C:/Users/Administrator/.workbuddy/tools/adb`（知识库检查器）")
    L.append("> 重新生成：`python C:/Users/Administrator/.workbuddy/tools/adb/gen_tools_index.py`")
    L.append(f"> **本次清理**：失效条目 {len(removed)} 个（原表有、磁盘已无）· "
             f"跳过 `_bak_*` 备份 {skipped_bak} 个 · 同名合并 {merged} 份")
    L.append("")
    L.append("> [!tip] 用法")
    L.append(f"> **先在这里找现成脚本，再自己写。** {len(items)} 个脚本里很多功能已经实现过，")
    L.append("> 分类 + 用途 + 参数都在下表 —— 不用读代码就知道哪个能干哪件事。")
    L.append("")
    oneoff_n = sum(1 for i in items if i["oneoff"])
    L.append(f"> **复用性**：🟢 **{len(items)-oneoff_n} 个通用脚本**（可直接复用）· "
             f"🔴 **{oneoff_n} 个一次性脚本**（文件名绑死商品ID/日期，只能参考写法）")
    L.append("> 表里标 🔴 的一次性脚本，**照它的写法写新的**，别直接改它 —— 改了会影响历史商品。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## ⭐ 主力脚本（先看这几个）")
    L.append("")
    L.append("| 脚本 | 用途 |")
    L.append("|---|---|")
    for k, v in KEY.items():
        if any(i["name"] == k for i in items):
            L.append(f"| `{k}` | {v} |")
    L.append("")
    L.append("---")
    L.append("")

    # 按分类输出
    cats = []
    for c, _, _ in RULES:
        cats.append(c)
    cats.append("📦 其它")

    for c in cats:
        sub = [i for i in items if i["cat"] == c]
        if not sub:
            continue
        L.append(f"## {c}（{len(sub)}）")
        L.append("")
        L.append("| 脚本 | 用途 | 参数 | 最后改 |")
        L.append("|---|---|---|---|")
        # 有 doc 的排前面
        sub.sort(key=lambda x: (not x["doc"], x["name"]))
        for i in sub:
            doc = i["doc"].replace("|", "/") if i["doc"] else "—"
            args = ", ".join(i["args"][:4]) if i["args"] else "—"
            mark = "🔴 " if i["oneoff"] else ""
            L.append(f"| {mark}`{i['name']}` | {doc} | `{args}` | {i['mtime']} |")
        L.append("")

    L.append("---")
    L.append("")
    L.append("## 🔗 相关")
    L.append("")
    L.append("- [[操作-阿奇索上品一条龙]] —— 主流程用法")
    L.append("- [[操作-阿奇索宝贝SKU设置]] —— 接口层配方")
    L.append("- [[项目-edge-bridge]] —— 脚本依赖的桥接通道")
    L.append("- [[操作层规范]] —— 写笔记必带「🚀 快速开始」")
    L.append("")

    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print(f"✓ 已生成 {OUT}")
    print(f"  {len(items)} 个脚本，{len(L)} 行")
    print(f"  跳过 _bak_* 备份 {skipped_bak} 个 | 同名合并 {merged} 份 | 清理失效 {len(removed)} 条")
    if removed:
        print("  已清理（原表有、磁盘已无）:")
        for n in removed[:20]:
            print("    -", n)
        if len(removed) > 20:
            print(f"    … 另 {len(removed)-20} 条")

    # 统计
    from collections import Counter
    for c, n in Counter(i["cat"] for i in items).most_common():
        print(f"  {c:<14} {n}")


if __name__ == "__main__":
    main()
