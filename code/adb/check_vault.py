#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
库完整性检查器 —— 防止「笔记写了但索引没挂，新对话发现不了」

检查项：
  1. Obsidian 库每篇笔记是否都挂进了 长期记忆.md 的索引表
  2. 是否都进了用户级 MEMORY.md 的速查表
  3. [[双链]] 是否有断链（指向不存在的文件）
  4. 是否含敏感凭据（token / JWT / 密码 / API key）
  5. 工作区 daily log 是否有超过 30 天未蒸馏的
  6-11. 见下方各检查段（legacy / frontmatter / 口径交叉 / 操作层 /
        脚本有效性 / 索引新鲜度 / 结构完整性）
  12. 元约束【M4】状态四维：8 个必填字段 + 受控词表 + review_by 过期
  13. 元约束【M1】规则单一正文：阈值副本检测（按 规则-知识库元约束.md 登记表）
  14. 元约束【M2】规则卡四要素：登记表每行的判据/验证/失效条件/指纹非空

用法：
  python check_vault.py            # 全查
  python check_vault.py --fix      # 自动把漏挂的补进索引（需人工确认表格描述）
"""
import io
import os
import re
import sys
import glob
import datetime

VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"
USER_MEM = r"C:\Users\Administrator\.workbuddy\user-6e1ce042-0701-4318-8682-d9adc18279df-personal\MEMORY.md"
WS_MEM = r"C:\Users\Administrator\Desktop\workbuddy\文档提取\.workbuddy\memory"

SKIP_INDEX = {"欢迎", "长期记忆", "记忆-回写规范", "最近变更"}  # 最近变更=自动生成
SENSITIVE = [
    ("eyJ0eXAiOiJKV1Qi", "JWT"),
    ("KSSID=", "会话Cookie"),
    ("api_key", "API key"),
    ("sk-", "OpenAI风格key"),
    ("access_token", "访问令牌"),
]
# 这些是「本地地址示例」不是凭据，白名单避免误报
BENIGN = [
    "http_proxy 127.0.0.1:8080",   # mitmproxy 本地代理示例
    "127.0.0.1:52510",
]


def read(p, default=""):
    try:
        return io.open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return default


# ── 元约束（规则-知识库元约束.md）──────────────────────────────
REG_DOC = "规则-知识库元约束.md"
REG_HEAD = "## 五、规则登记表"
AUTO_GEN = {"脚本索引.md", "上品资料索引.md", "最近变更.md"}
RULE_WORDS = ("必须", "禁止", "一律", "默认", "不得", "上限", "统一", "只准", "不准", "严禁")
POINTER_HINT = ("正文见", "详见", "见 [[", "[摘要]", "[引]")


def resolve_note(canon):
    """把登记表的「唯一正文」解析成绝对路径。
    🔴 2026-11-15 修：原实现只做 os.path.join(VAULT, canon)，正文放在
    `身份与记忆/` 子目录时存在性检查必然失败；而 M1 的跳过判断又用 basename
    比对，写成 `身份与记忆/X.md` 会让正文自己被当成副本、写成 `X.md` 又找不到文件。
    现在两个目录都找，跳过判断统一按 basename。"""
    for cand in (os.path.join(VAULT, canon),
                 os.path.join(VAULT, "身份与记忆", os.path.basename(canon))):
        if os.path.exists(cand):
            return cand
    return os.path.join(VAULT, canon)


def parse_registry():
    """解析 规则-知识库元约束.md §五 登记表。
    返回 (rows, err)；row = (规则, 唯一正文, 判据, 验证方式, 失效条件, 指纹)"""
    s = read(os.path.join(VAULT, REG_DOC))
    if not s:
        return None, f"元约束正文缺失（{REG_DOC}）"
    i = s.find(REG_HEAD)
    if i < 0:
        return None, f"未找到「{REG_HEAD}」"
    rows = []
    for ln in s[i:].split("\n")[1:]:
        t = ln.strip()
        if not t.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in t.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0] == "规则" or set(cells[0]) <= set("-: "):
            continue
        rows.append(tuple(cells[:6]))
    if not rows:
        return None, "登记表解析为空"
    return rows, None


def main():
    print("=" * 62)
    print(" Obsidian 库完整性检查")
    print("=" * 62)

    notes = [os.path.basename(p)[:-3] for p in glob.glob(os.path.join(VAULT, "*.md"))]
    idx = read(os.path.join(VAULT, "长期记忆.md"))
    um = read(USER_MEM)

    problems = []

    # ---- 1/2 索引覆盖 ----
    print("\n【1】索引覆盖")
    miss_i, miss_u = [], []
    for n in notes:
        if n in SKIP_INDEX:
            continue
        in_idx = n in idx
        in_um = n in um
        mark = "✓" if (in_idx and in_um) else ("✗索引" if not in_idx else "✗速查")
        print(f"   {mark:<6} {n}")
        if not in_idx:
            miss_i.append(n)
        if not in_um:
            miss_u.append(n)
    if miss_i:
        problems.append(f"未挂索引: {', '.join(miss_i)}")
    if miss_u:
        problems.append(f"未挂速查表: {', '.join(miss_u)}")

    # ---- 3 双链 ----
    print("\n【2】双链断链检查")
    broken = []
    # 笔记名集合：支持 子目录/笔记名 与 笔记名 两种写法（Obsidian 双链不带 .md 后缀）
    note_names = set()
    for p in glob.glob(os.path.join(VAULT, "*.md")):
        note_names.add(os.path.splitext(os.path.basename(p))[0])
    for p in glob.glob(os.path.join(VAULT, "*", "*.md")):
        rel = os.path.relpath(p, VAULT).replace("\\", "/")
        note_names.add(os.path.splitext(rel)[0])      # 身份与记忆/MEMORY
        note_names.add(os.path.splitext(os.path.basename(p))[0])  # MEMORY
    for p in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "*", "*.md")):
        s = read(p)
        base = os.path.basename(p)
        for m in re.findall(r"\[\[([^\]|]+)", s):
            t = m.strip()
            if not t or t.startswith("http") or t == "创建链接":
                continue
            # 去掉 .md 后缀再比对
            t2 = t[:-3] if t.endswith(".md") else t
            if t2 not in note_names and t not in note_names:
                broken.append(f"{base} -> [[{t}]]")
    if broken:
        for b in broken:
            print(f"   ✗ {b}")
        problems.append(f"断链 {len(broken)} 处")
    else:
        print("   ✓ 全部有效")

    # ---- 4 敏感信息 ----
    print("\n【3】敏感凭据扫描")
    hit = False
    for p in glob.glob(os.path.join(VAULT, "*.md")):
        s = read(p)
        for b in BENIGN:
            s = s.replace(b, "")
        for kw, label in SENSITIVE:
            if kw in s:
                print(f"   ✗ {os.path.basename(p)} 含 {label}")
                hit = True
    if not hit:
        print("   ✓ 未发现")

    # ---- 5 daily log 超期 ----
    print("\n【4】工作区 daily log 超 30 天未蒸馏")
    today = datetime.date.today()
    overdue = []
    for p in glob.glob(os.path.join(WS_MEM, "2026-*.md")):
        d = datetime.date.fromisoformat(os.path.basename(p)[:-3])
        age = (today - d).days
        if age > 30:
            overdue.append(f"{os.path.basename(p)} ({age}天)")
            print(f"   ⚠ {os.path.basename(p)}  {age} 天前")
    if not overdue:
        print("   ✓ 无超期")

    # ---- 6 legacy 笔记清单 ----
    print("\n【5】legacy 笔记（历史留档，别照做）")
    legacy = []
    for p in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")):
        s = read(p)
        m = re.search(r"^status:\s*(\S+)", s, re.M)
        if m and m.group(1) == "legacy":
            rel = os.path.relpath(p, VAULT).replace(os.sep, "/")
            legacy.append(rel)
            has_warn = "现行口径" in s or "别照着" in s or "已不在现行" in s
            print(f"   {'✓' if has_warn else '⚠'} {rel}  "
                  f"{'（已加口径提示）' if has_warn else '← 建议加现行口径提示'}")
            if not has_warn:
                problems.append(f"legacy 笔记缺口径提示: {rel}")
    if not legacy:
        print("   ✓ 无 legacy 笔记")

    # ---- 7 frontmatter 完整性 + 元约束 M4 状态四维 ----
    print("\n【6】frontmatter 完整性 + 状态四维（M4）")
    need = ["created", "updated", "tags", "type", "status",
            "execution", "verified_at", "review_by"]
    STATUS_OK = {"active", "legacy", "draft"}
    EXEC_OK = {"write_verified", "read_only", "blocked", "unspecified"}
    DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    fm_bad = 0
    for p in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")):
        if os.path.basename(p) == "最近变更.md":
            continue
        s = read(p)
        rel = os.path.relpath(p, VAULT).replace(os.sep, "/")
        if not s.startswith("---"):
            print(f"   ✗ {rel} 无 frontmatter")
            problems.append(f"缺 frontmatter: {rel}")
            fm_bad += 1
            continue
        miss = [k for k in need if not re.search(rf"^{k}:", s, re.M)]
        if miss:
            print(f"   ✗ {rel} 缺字段: {', '.join(miss)}")
            problems.append(f"frontmatter 缺字段 {rel}: {miss}")
            fm_bad += 1
            continue
        st = re.search(r"^status:\s*(\S+)", s, re.M).group(1)
        ex = re.search(r"^execution:\s*(\S+)", s, re.M).group(1)
        rb = re.search(r"^review_by:\s*(\S+)", s, re.M).group(1)
        va = re.search(r"^verified_at:\s*(\S+)", s, re.M).group(1)
        errs = []
        if st not in STATUS_OK:
            errs.append(f"status={st} 不在词表 {sorted(STATUS_OK)}")
        if ex not in EXEC_OK:
            errs.append(f"execution={ex} 不在词表 {sorted(EXEC_OK)}")
        if not DATE_RE.match(va):
            errs.append(f"verified_at={va} 非 YYYY-MM-DD")
        if not DATE_RE.match(rb):
            errs.append(f"review_by={rb} 非 YYYY-MM-DD")
        if errs:
            print(f"   ✗ {rel} {'; '.join(errs)}")
            problems.append(f"状态四维取值错 {rel}: {errs[0]}")
            fm_bad += 1
            continue
        if ex == "write_verified" and st == "legacy":
            print(f"   ⚠ {rel} legacy 却标 write_verified（历史流程不该再算已验证）")
        rb_d = datetime.date.fromisoformat(rb)
        if rb_d < today:
            print(f"   ⚠ {rel} review_by 已过期 {rb}（过期 {(today-rb_d).days} 天）→ 复核后更新")
            problems.append(f"review_by 过期 {rel}: {rb}")
            fm_bad += 1
        elif ex == "unspecified" and st == "active":
            print(f"   ·  {rel} active 且 execution=unspecified（待补声明执行等级）")
    if not fm_bad:
        print("   ✓ 8 字段齐全、词表与日期合法、无过期")

    # ---- 8 口径交叉引用 ----
    print("\n【7】口径交叉引用（库内自洽性）")
    mem = read(os.path.join(VAULT, "身份与记忆", "MEMORY.md"))
    has_rule = "货源只比" in mem or "现行" in mem
    print(f"   {'✓' if has_rule else '✗'} 库内含现行货源口径")
    if not has_rule:
        problems.append("库内 身份与记忆/MEMORY.md 缺现行货源口径")
    # 检查提到历史货源平台的笔记：若提到但**没有**任何口径标注 → 才是冲突
    for p in glob.glob(os.path.join(VAULT, "*.md")):
        s = read(p)
        rel = os.path.relpath(p, VAULT).replace(os.sep, "/")
        if rel in ("身份与记忆/MEMORY.md", "最近变更.md"):
            continue
        if not re.search(r"(省省|星芒|追梦)", s):
            continue
        # 已明确标注「弃用/不再使用/历史留档」或已指向 MEMORY → 合规
        marked = any(k in s for k in
                     ["已弃用", "不再使用", "不再考虑", "历史留档", "legacy",
                      "别照着", "已不在现行", "MEMORY"])
        if marked:
            print(f"   ✓ {rel}（已标注口径）")
        else:
            print(f"   ⚠ {rel} 提到历史货源平台但未标注口径")
            problems.append(f"口径可能冲突: {rel}")
    print("   ✓ 无冲突" if not any("口径可能冲突" in p for p in problems) else "")

    # ---- 9 操作层完整性 ----
    print("\n【8】操作层完整性（照《操作层规范》检查）")
    # 需要「快速开始」块的 type
    NEED_QS = {"操作", "项目", "项目笔记"}
    SKIP_TYPES = {"索引", "长期记忆", "身份文件", "规则", "模板", "环境档案"}
    qs_missing = []
    for p in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")):
        rel = os.path.relpath(p, VAULT).replace(os.sep, "/")
        if os.path.basename(p) == "最近变更.md":
            continue
        s = read(p)
        m = re.search(r"^type:\s*(.+)$", s, re.M)
        typ = m.group(1).strip() if m else ""
        if typ in SKIP_TYPES:
            continue
        if typ not in NEED_QS:
            continue
        if "## 🚀 快速开始" not in s:
            qs_missing.append(rel)
            print(f"   ✗ {rel}（type={typ}）缺「🚀 快速开始」块")
            continue
        # 四要素检查
        miss = []
        for label, pat in (("前置条件", r"###\s*前置条件"),
                           ("一键入口", r"###\s*一键入口"),
                           ("预期输出", r"###\s*预期输出")):
            if not re.search(pat, s):
                miss.append(label)
        if miss:
            qs_missing.append(rel)
            print(f"   ✗ {rel} 快速开始缺要素：{', '.join(miss)}")
        else:
            cmd_n = len(re.findall(r"```(?:bash|powershell|sh|cmd)\n", s))
            print(f"   ✓ {rel}（命令块 {cmd_n} 个）")
    if not qs_missing:
        print("   ✓ 全部具备")
    else:
        problems.append(f"缺操作层快速开始块 {len(qs_missing)} 篇: "
                        + ", ".join(os.path.basename(x) for x in qs_missing))

    # ---- 10 脚本有效性 ----
    print("\n【9】脚本有效性（笔记提到的脚本是否还在磁盘）")
    search_dirs = [
        r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41",
        r"C:\Users\Administrator\Desktop\workbuddy",
        r"C:\Users\Administrator\.workbuddy\tools",
        r"C:\Users\Administrator\.workbuddy\skills",
    ]
    sidx = {}
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for ext in ("*.py", "*.js", "*.sh", "*.cmd", "*.bat", "*.mjs"):
            for p in glob.glob(os.path.join(d, "**", ext), recursive=True):
                if "node_modules" in p or "__pycache__" in p:
                    continue
                sidx.setdefault(os.path.basename(p), p)
    dead_total = 0
    # 收集各笔记里「明确声明失效」的脚本名（出现在 已知失效/已失效/不存在 段落里的）
    noted_dead = {}
    for p in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")):
        rel = os.path.relpath(p, VAULT).replace(os.sep, "/")
        s = read(p)
        # 找「已知失效」「已失效」「不存在」这类标注附近的脚本名（前后各看一段）
        noted = set()
        for m in re.finditer(r'已知失效|已失效|已不存在|磁盘上已不存在|全盘搜索无果|旧名|手机侧路径|手机侧脚本', s):
            lo = max(0, m.start() - 200)
            seg = s[lo:m.start() + 600]
            noted.update(re.findall(r'\b([A-Za-z_][A-Za-z0-9_.\-]*\.(?:py|js|sh|cmd|mjs))\b', seg))
        if noted:
            noted_dead[rel] = noted
    for p in glob.glob(os.path.join(VAULT, "*.md")) + glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")):
        rel = os.path.relpath(p, VAULT).replace(os.sep, "/")
        if os.path.basename(p) in ("最近变更.md", "脚本索引.md"):
            continue
        s = read(p)
        names = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_.\-]*\.(?:py|js|sh|cmd|mjs))\b', s))
        dead = sorted(n for n in names if n not in sidx)
        # 排除明显是网页产物的
        dead = [d for d in dead if not re.match(r'^(app|index|chunk-vendors|.*\.[0-9a-f]{8}|kefu|pages-.*)\.js$', d)]
        # 排除示例占位符（规范文档里的 xxx.py 之类）
        dead = [d for d in dead if not re.match(r'^(xxx|yyy|zzz|your_|example|foo|bar)\.', d)]
        # 排除手机侧脚本（/data/local/tmp/... 下的在 PC 端不存在是正常的）
        phone_side = [d for d in dead if re.search(r'/data/local/tmp/[^\s`"]*' + re.escape(d), s)]
        dead = [d for d in dead if d not in phone_side]
        if dead:
            # 笔记里若已明确标注「失效/不存在/已弃用」→ 不算问题
            marked = any(k in s for k in
                         ["已知失效", "已失效", "不存在", "已弃用", "磁盘上已", "全盘搜索无果"])
            still = [d for d in dead if d not in noted_dead.get(rel, [])]
            if marked and not still:
                print(f"   ✓ {rel}（已标注失效：{len(dead)} 个）")
            else:
                if still:
                    dead_total += len(still)
                    print(f"   ⚠ {rel} 引用了不存在的脚本：{', '.join(still[:6])}")
                    problems.append(f"脚本失效 {rel}: {', '.join(still[:6])}")
                else:
                    print(f"   ✓ {rel}（已标注失效）")
    if not dead_total:
        print(f"   ✓ 全部有效（已索引 {len(sidx)} 个脚本文件）")

    # ---- 11 索引新鲜度 ----
    print("\n【10】自动生成索引的新鲜度")
    AUTO = ["脚本索引.md", "上品资料索引.md", "最近变更.md"]
    stale = []
    for name in AUTO:
        p = os.path.join(VAULT, name)
        if not os.path.exists(p):
            print(f"   ✗ {name} 不存在")
            problems.append(f"自动索引缺失: {name}")
            continue
        # 与源对比：脚本索引 ← 脚本数；上品资料索引 ← spec+结果数
        if name == "脚本索引.md":
            cur = len(glob.glob(os.path.join(
                r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41", "**", "*.py"), recursive=True))
            m = re.search(r"共\s*\*\*(\d+)\*\*\s*个脚本", read(p))
            idx = int(m.group(1)) if m else 0
            if cur and idx and abs(cur - idx) > 25:
                print(f"   ⚠ {name} 可能过期（磁盘 {cur} 个 vs 索引 {idx} 个）")
                stale.append(name)
            else:
                print(f"   ✓ {name}（{idx} 个脚本）")
        elif name == "上品资料索引.md":
            s = read(p)
            m1 = re.search(r"spec 模板（(\d+) 份）", s)
            m2 = re.search(r"上品结果记录（(\d+) 份）", s)
            idx = (int(m1.group(1)) if m1 else 0) + (int(m2.group(1)) if m2 else 0)
            proj = r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41"
            cur = len(glob.glob(os.path.join(proj, "spec_*.json"))) + \
                  len(glob.glob(os.path.join(proj, "上品结果-*.md")))
            if cur and idx and cur != idx:
                print(f"   ⚠ {name} 已过期（磁盘 {cur} 份 vs 索引 {idx} 份）→ 跑 refresh-indexes.sh")
                stale.append(name)
            else:
                print(f"   ✓ {name}（{idx} 份）")
        else:
            print(f"   ✓ {name}")

    # 【11】结构完整性 —— 补丁打多了的典型后遗症（见《操作层规范》第六节）
    print("\n【11】结构完整性（补丁后遗症 / 该重写了）")
    AUTO_FILES = {"脚本索引.md", "上品资料索引.md", "最近变更.md"}
    struct_bad = []
    checked = 0
    md_files = sorted(glob.glob(os.path.join(VAULT, "*.md")) +
                      glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")))
    for p in md_files:
        name = os.path.basename(p)
        if name in AUTO_FILES:
            continue   # 自动生成索引：重跑生成器，不手写
        checked += 1
        s = read(p)
        issues = []

        # A. 同一个 ## 章节内出现同名 ###/#### 标题（跨章节同名是正常的）
        for block in re.split(r"(?=^## )", s, flags=re.M):
            head = block.split("\n", 1)[0].strip()[:36]
            seen = {}
            for t in re.findall(r"^#{3,4}\s+(.+?)\s*$", block, re.M):
                key = re.sub(r"^[\d一二三四五六七八九十]+[.、\s]*", "", t).strip()
                if len(key) > 1:
                    seen[key] = seen.get(key, 0) + 1
            for k, n in seen.items():
                if n >= 2:
                    issues.append(f"章节「{head}」内标题重复 ×{n}: {k}")

        # B. 重复的连续 3 行块（排除代码块；表格/示例的重复是正常的）
        lines = [l.rstrip() for l in s.split("\n")]
        incode = False
        clean = []
        for l in lines:
            if l.strip().startswith("```"):
                incode = not incode
                clean.append("")
            else:
                clean.append("" if incode else l)
        seen_blocks = {}
        for i in range(len(clean) - 2):
            tri = tuple(clean[i:i + 3])
            if not all(x.strip() and len(x.strip()) > 10 for x in tri):
                continue
            seen_blocks.setdefault(tri, []).append(i + 1)
        for tri, locs in seen_blocks.items():
            if len(locs) >= 2:
                issues.append(f"重复段落（行 {locs[0]} / {locs[1]}）: 「{tri[0].strip()[:40]}」")
                break   # 每篇只报一处，避免刷屏

        if issues:
            struct_bad.append(name)
            print(f"   ⚠ {name}")
            for x in issues[:3]:
                print(f"      · {x}")
            problems.append(f"结构损坏（按《操作层规范》六重写） {name}: {issues[0]}")
    if not struct_bad:
        print(f"   ✓ 全部整洁（已查 {checked} 篇）")

    # ---- 12 元约束 M1：规则单一正文 ----
    print("\n【12】规则单一正文（M1 阈值副本检测）")
    rows, rerr = parse_registry()
    md_files = sorted(glob.glob(os.path.join(VAULT, "*.md")) +
                      glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")))
    if rerr:
        print(f"   ✗ {rerr}")
        problems.append(f"规则登记表不可用: {rerr}")
    else:
        dup = []
        for rule, canon, _c, _v, _e, fp in rows:
            toks = [x.strip().strip("`") for x in fp.split(",") if x.strip()]
            if not toks:
                continue
            for p in md_files:
                name = os.path.basename(p)
                if name == os.path.basename(canon) or name in AUTO_GEN or name == REG_DOC:
                    continue
                for no, line in enumerate(read(p).split("\n"), 1):
                    if not any(k in line for k in toks):
                        continue
                    if not any(w in line for w in RULE_WORDS):
                        continue
                    if any(k in line for k in POINTER_HINT):
                        continue
                    dup.append((name, no, rule, line.strip()[:56]))
        if dup:
            for name, no, rule, txt in dup:
                print(f"   ⚠ {name}:{no} 「{rule}」副本 → {txt}")
            problems.append(f"阈值副本 {len(dup)} 处：改为「正文见 [[X]]」或给该行加 [摘要]")
        else:
            print(f"   ✓ {len(rows)} 条规则正文唯一，无副本")

    # ---- 13 元约束 M2：规则卡四要素 ----
    print("\n【13】规则卡四要素（M2）")
    if rerr:
        print(f"   ✗ {rerr}")
    else:
        bad = []
        for rule, canon, jud, ver, exp, fp in rows:
            miss = [n for n, v in (("判据", jud), ("验证方式", ver),
                                   ("失效条件", exp), ("指纹", fp))
                    if not v or v in ("—", "-", "空")]
            if not os.path.exists(resolve_note(canon)):
                miss.append(f"唯一正文不存在({canon})")
            if miss:
                bad.append((rule, miss))
        if bad:
            for rule, miss in bad:
                print(f"   ✗ 「{rule}」缺 {', '.join(miss)}")
            problems.append(f"规则卡四要素不全 {len(bad)} 条")
        else:
            print(f"   ✓ {len(rows)} 条规则四要素齐全，唯一正文均存在")

    # ---- 14 自动生成索引一致性（原先把脚本索引整份豁免，腐烂无人知）----
    # 🔴 2026-11-15 加：`脚本索引.md` 在【9】里属于 AUTO_GEN 豁免，导致「索引里有、
    #    磁盘上已无」的条目不报错。这里单独给它一道校验：条目必须在生成器的扫描根下真实存在。
    print("\n【14】脚本索引一致性（自动生成文件不再豁免）")
    SCRIPTS_ROOTS = [r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41",
                     r"C:\Users\Administrator\.workbuddy\tools\adb"]
    SCRIPTS_SKIP = re.compile(r"node_modules|__pycache__|[\\/]_bak[^\\/]*[\\/]"
                              r"|backups_over1000|[\\/]\.git[\\/]")
    idx_path = os.path.join(VAULT, "脚本索引.md")
    if not os.path.exists(idx_path):
        print("   ⚠ 脚本索引.md 不存在，跳过")
    else:
        txt = read(idx_path)
        names = re.findall(r"^\|\s*(?:🔴\s*)?`([^`]+)`\s*\|", txt, re.M)
        disk = set()
        for _root in SCRIPTS_ROOTS:
            for r, _d, fs in os.walk(_root):
                if SCRIPTS_SKIP.search(r + "\\"):
                    continue
                disk.update(fs)
        dead = [n for n in dict.fromkeys(names) if n not in disk]
        uniq = len(dict.fromkeys(names))
        dup_by_design = len(names) - uniq
        if dead:
            for n in dead[:8]:
                print(f"   ✗ 索引有、磁盘无: {n}")
            print(f"   ✗ 共 {len(dead)} 条失效条目（重跑 gen_tools_index.py 清理）")
            problems.append(f"脚本索引失效条目 {len(dead)} 个")
        else:
            print(f"   ✓ {uniq} 个条目全部真实存在"
                  f"（另有 {dup_by_design} 行属主力表与分类表的有意重复）")

    print("\n" + "=" * 62)
    if problems:
        print(" 发现问题：")
        for p in problems:
            print(f"   · {p}")
        print("=" * 62)
        return 1
    print(" 全部通过 ✓")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
