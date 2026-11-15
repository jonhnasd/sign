# -*- coding: utf-8 -*-
"""分析 edge-bridge/tools 下所有脚本的真实用途（读内容，不靠文件名猜）"""
import io
import os
import re
import json
import glob

TOOLS = r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41\edge-bridge\tools"

RULES = [
    # (类别, 关键词正则, 说明)
    ("主流程/执行",   r"deploy|一条龙|full_pipeline|_pipeline|pipeline_9|finish_9|do_all", "完整跑通某个流程"),
    ("探测/读取",     r"^_?(probe|read|dump|peek|scan|get|fetch|list|show|search|find|cap|list_)|_probe|_read|_dump|_peek|_scan|_list_", "只读不改，探现状"),
    ("配置/写入",     r"^_?(set|add|build|config|update|upd|insert|create|write|save|fill|copy|rebuild|reprice|rebuild|fix_|_set_|_add_|_build_|_config_|_update_|_upd_|_fill_|_spec_|_hy_|_kb_)", "会改动数据"),
    ("校验/核对",     r"^_?(verify|check|audit|compare|cmp|diff|v3_compare|tt_compare|_check_|_verify_|_audit_|_cmp_|_diff_)", "验证结果对不对"),
    ("回滚/清理",     r"^_?(restore|revert|del|delete|clean|_del_|_restore_)|delisted|_del_|_clean", "撤销或删除"),
    ("登录/认证",     r"login|auth|qr|_agiso_login|token|_ssyq_capture", "处理登录态"),
    ("数据抓取",      r"qcqcq|sqqy88|siquan|_91kami|qqkami|sup12|xmang|balance|mtop|mt_|_mt_|_zy_|_doubi|_douyin", "抓外部站点数据"),
    ("调试诊断",      r"^_?(dbg|diag|explore|research|research2|_dbg|_diag|test_|_probe_)", "排查问题用"),
    ("品类专用",      r"bixin|changpei|meituan|huafei|shoudan|doubi|douyu|liuying|qiancheng|shengsheng|xingmang|kge|_hy_|_tp_|_jd_|_bixin|_mt_|_zy_", "特定商品品类专用"),
]

CAT_ORDER = ["主流程/执行", "探测/读取", "配置/写入", "校验/核对", "回滚/清理",
             "登录/认证", "数据抓取", "调试诊断", "品类专用"]


def classify(name):
    low = name.lower()
    for cat, pat, _ in RULES:
        if re.search(pat, low):
            return cat
    return "其它"


def extract_doc(path):
    """取文件前 60 行里的中文说明 / docstring / argparse"""
    try:
        s = io.open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return "", []
    # docstring
    doc = ""
    m = re.search(r'"""(.*?)"""', s[:4000], re.S)
    if m:
        doc = m.group(1).strip()
    if not doc:
        # 注释里的中文行
        lines = []
        for ln in s.split("\n")[:40]:
            ln = ln.strip()
            if ln.startswith("#") and re.search(r'[\u4e00-\u9fff]', ln):
                lines.append(ln.lstrip("# ").strip())
        doc = " / ".join(lines[:2])
    args = re.findall(r'add_argument\(\s*["\']([^"\']+)["\']', s)
    return doc, args


def main():
    files = sorted(glob.glob(os.path.join(TOOLS, "*.py")))
    items = []
    for p in files:
        name = os.path.basename(p)
        doc, args = extract_doc(p)
        items.append({
            "name": name,
            "size": os.path.getsize(p),
            "mtime": time_fmt(os.path.getmtime(p)),
            "cat": classify(name),
            "doc": doc[:110],
            "args": args[:6],
        })

    print(f"总脚本数: {len(items)}\n")
    print("=== 分类分布 ===")
    for c in CAT_ORDER:
        n = sum(1 for i in items if i["cat"] == c)
        if n:
            print(f"  {c:<12} {n:>4}")
    others = sum(1 for i in items if i["cat"] == "其它")
    if others:
        print(f"  {'其它':<12} {others:>4}")

    print("\n=== 有中文说明的（可作索引标题）===")
    withdoc = [i for i in items if i["doc"] and re.search(r'[\u4e00-\u9fff]', i["doc"])]
    print(f"  {len(withdoc)} / {len(items)} 有中文 doc/注释")

    io.open(os.path.join(os.path.dirname(TOOLS), "tools", "_index_raw.json"),
            "w", encoding="utf-8").write(json.dumps(items, ensure_ascii=False, indent=1))
    print(f"\n原始数据已存 _index_raw.json")

    # 抽样展示
    print("\n=== 抽样（前 20 个有中文说明的）===")
    for i in withdoc[:20]:
        print(f"  [{i['cat']:<8}] {i['name'][:38]:<40} {i['doc'][:46]}")


def time_fmt(ts):
    import datetime
    return datetime.date.fromtimestamp(ts).isoformat()


if __name__ == "__main__":
    main()
