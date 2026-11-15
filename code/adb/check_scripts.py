# -*- coding: utf-8 -*-
"""核对库内笔记提到的脚本是否仍存在于磁盘 → 列出失效清单"""
import io
import os
import re
import glob

VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"
SEARCH_DIRS = [
    r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41",   # 整个项目根（含 qcqcq/ cdp/ edge-bridge/ 等子目录）
    r"C:\Users\Administrator\Desktop\workbuddy",
    r"C:\Users\Administrator\.workbuddy\tools",
]

# 建索引：文件名 → 路径（递归扫全目录）
index = {}
for d in SEARCH_DIRS:
    if not os.path.isdir(d):
        continue
    for ext in ("*.py", "*.js", "*.sh", "*.cmd", "*.bat", "*.mjs"):
        for p in glob.glob(os.path.join(d, "**", ext), recursive=True):
            if "node_modules" in p or "__pycache__" in p:
                continue
            index.setdefault(os.path.basename(p), p)

print(f"磁盘上可查脚本: {len(index)} 个\n")

missing = {}
for md in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")):
    fn = os.path.basename(md)
    if fn in ("最近变更.md", "脚本索引.md"):
        continue
    s = io.open(md, encoding="utf-8", errors="ignore").read()
    # 抓 xxx.py / xxx.js / xxx.sh
    names = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_.\-]*\.(?:py|js|sh|cmd))\b', s))
    miss = sorted(n for n in names if n not in index)
    if miss:
        missing[fn] = miss

if not missing:
    print("✓ 所有笔记提到的脚本都还在磁盘上")
else:
    print("=== ⚠ 失效脚本（笔记提到但磁盘没有）===\n")
    total = 0
    for fn, miss in sorted(missing.items()):
        print(f"  {fn}:")
        for m in miss:
            print(f"      ✗ {m}")
            total += 1
        print()
    print(f"合计失效: {total} 个")
