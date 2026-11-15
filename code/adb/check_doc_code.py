# -*- coding: utf-8 -*-
"""文档↔代码一致性检查（只读）

为什么有这道检查
----------------
`check_vault.py` 验的是**结构**（索引有没有挂、双链断没断、frontmatter 齐不齐），
它全绿**不代表**文档描述的行为和代码一致。2026-11-15 实测：

  · `项目-阿奇索模块化生产与契约回归.md` 的模块表把 `deploy.py`、`onepipe_guard.py`
    列在「alds_kit/ 按职责拆分」之下 —— 两者实际在 tools/ 根，且漏了整个 `alds_dict.py`；
  · 新增 CLI 参数 `--title-sku-mode` 只出现在经验页，**建品操作页查不到**。

这类漂移结构检查抓不到，只能靠比对「文档里写的函数/参数」与「代码里真实存在的」。
本脚本就干这件事，纯只读、不改任何文件。

检查项
------
1. 函数签名：`操作-*.md` 里 `func(a, b, c)` 形式的签名 vs 代码实际 `inspect.signature`
2. CLI 参数：代码里 argparse 定义的 `--flag` 是否都至少在某篇笔记里出现过
3. 模块归属：`alds_kit/` 实际模块名 vs 模块化正文里声称的
4. 阶段清单：`deploy.phase_*` 实际集合 vs 文档提到的集合

用法
----
    python check_doc_code.py             # 全查，退出码 0=一致 / 1=有漂移 / 2=环境问题
    python check_doc_code.py --verbose   # 打印每一条通过项
"""
import argparse
import glob
import importlib
import inspect
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"
TOOLS = r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41\edge-bridge\tools"
BT = "\x60"

# 文档里可能出现、但属于「别的模块」的函数，签名不强制
KNOWN_OTHER = {"strip_template_images", "resolve_buyer_field", "mark_verified"}


def read(p):
    try:
        return io.open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def vault_notes():
    return sorted(glob.glob(os.path.join(VAULT, "*.md")) +
                  glob.glob(os.path.join(VAULT, "身份与记忆", "*.md")))


def load_mod(name):
    sys.path.insert(0, TOOLS)
    try:
        return importlib.import_module(name)
    except Exception as e:
        print(f"   ✗ 无法导入 {name}: {e}")
        return None


# ── 1. 函数签名 ───────────────────────────────────────────────
PARAM = re.compile(r"^[a-z_][a-z_0-9]*$")


def param_names(sig):
    """从 inspect.signature 字符串取参数名序列（丢默认值、丢注解）。"""
    inner = sig.strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    if not inner.strip():
        return []
    out = []
    depth = 0
    cur = ""
    for ch in inner:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    names = []
    for a in out:
        a = a.strip()
        if not a:
            continue
        if a in ("*", "/"):
            continue
        name = a.split("=")[0].split(":")[0].strip().lstrip("*")
        names.append(name)
    return names


def check_signatures(mods, verbose):
    print("\n【1】函数签名：文档写的 == 代码实际")
    real = {}
    for m in mods:
        for n, f in vars(m).items():
            if callable(f) and not n.startswith("__"):
                try:
                    real.setdefault(n, list(inspect.signature(f).parameters))
                except (ValueError, TypeError):
                    pass
    bad, seen, skipped = [], set(), 0
    pat = re.compile(r"(" + BT + r"?)([a-z_][a-z_0-9]{3,})\(" + r"([^)\n]{0,90})\)")
    for p in vault_notes():
        note = os.path.basename(p)
        for ln, line in enumerate(read(p).split("\n"), 1):
            for _bt, fn, argstr in pat.findall(line):
                if fn not in real or fn in seen:
                    continue
                parts = [a.strip() for a in argstr.split(",") if a.strip()]
                # 🔴 只比对「纯参数名」形式。带字面量/kwarg/取下标的是**调用示例**，
                #    不是签名声明（例：`phase_copy(spec['goods'], spec)`），不能当漂移。
                if not parts or not all(PARAM.match(a) for a in parts):
                    skipped += 1
                    continue
                seen.add(fn)
                # 允许「省略尾部可选参数」：文档写 (gid, spec, plan) 对
                # 代码 (gid, spec, plan, dry=False) 合法；但顺序/改名仍算漂移。
                if parts == real[fn][:len(parts)]:
                    continue
                if parts != real[fn]:
                    bad.append((note, ln, fn, parts, real[fn]))
    if bad:
        for note, ln, fn, d, r in bad:
            print(f"   ✗ {note}:{ln} {fn}  文档({', '.join(d)}) ≠ 代码({', '.join(r)})")
        return [f"函数签名漂移 {len(bad)} 处"]
    print(f"   ✓ 核对 {len(seen)} 个函数签名，全部一致"
          f"（另有 {skipped} 处是调用示例，不参与比对）")
    if verbose:
        for fn in sorted(seen):
            print(f"       {fn}({', '.join(real[fn])})")
    return []


# ── 2. CLI 参数覆盖 ──────────────────────────────────────────
def check_cli(verbose):
    print("\n【2】CLI 参数：代码定义的 --flag 是否进了库")
    src = read(os.path.join(TOOLS, "create_from_pno.py"))
    if not src:
        print("   ⚠ 读不到 create_from_pno.py")
        return ["create_from_pno.py 缺失"]
    flags = sorted(set(re.findall(r"""add_argument\(\s*['"](--[a-z0-9-]+)['"]""", src)))
    # 隐藏/内部参数不算
    SKIP = {"--help"}
    flags = [f for f in flags if f not in SKIP]
    blob = "\n".join(read(p) for p in vault_notes())
    missing = [f for f in flags if f not in blob]
    if missing:
        for f in missing:
            print(f"   ✗ {f} 在库里零提及（读者无法发现）")
        return [f"CLI 参数未入文档 {len(missing)} 个: {', '.join(missing)}"]
    print(f"   ✓ {len(flags)} 个参数全部在库中出现")
    if verbose:
        print("       " + " ".join(flags))
    return []


# ── 3. 模块归属 ──────────────────────────────────────────────
def check_modules(verbose):
    print("\n【3】模块归属：alds_kit 实际模块 vs 文档声称")
    kit_dir = os.path.join(TOOLS, "alds_kit")
    actual = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(kit_dir, "*.py"))}
    actual.discard("__init__")
    doc = read(os.path.join(VAULT, "项目-阿奇索模块化生产与契约回归.md"))
    if not doc:
        print("   ⚠ 找不到模块化正文")
        return ["模块化正文缺失"]
    probs = []
    # 只取「alds_kit 是能力层」那一节，工具根那张表本来就不该算 alds_kit
    m = re.search(r"`alds_kit/`\s*是能力层.*?(?=\n工具根目录|\n##|\Z)", doc, re.S)
    kit_section = m.group(0) if m else ""
    claimed = set(re.findall(r"\|\s*`([a-z_0-9]+\.py)`\s*\|", kit_section))
    if not kit_section:
        print("   ⚠ 模块化正文里找不到「alds_kit/ 是能力层」小节")
    root_mods = {"deploy.py", "create_from_pno.py", "onepipe_guard.py",
                 "onepipe_service.py", "alds_dict.py"}
    bad_claim = [c for c in claimed if c in root_mods]
    if bad_claim:
        probs.append(f"文档把 {', '.join(bad_claim)} 列在 alds_kit 下，实际在 tools/ 根")
        for c in bad_claim:
            print(f"   ✗ {c} 被列在 alds_kit 表里，实际在 tools/ 根")
    for mm in sorted(actual):
        if f"{mm}.py" not in kit_section:
            probs.append(f"alds_kit/{mm}.py 未在 alds_kit 表出现")
            print(f"   ✗ alds_kit/{mm}.py 未进 alds_kit 表")
    if not probs and kit_section:
        print(f"   ✓ alds_kit {len(actual)} 个模块与文档一致（工具根 5 个编排器单列）")
        if verbose:
            print("       " + " ".join(sorted(actual)))
    return probs


# ── 4. 阶段清单 ──────────────────────────────────────────────
def check_phases(mods, verbose):
    print("\n【4】阶段清单：deploy.phase_* 是否都有操作文档")
    dp = next((m for m in mods if m.__name__ == "deploy"), None)
    if dp is None:
        return ["deploy 未加载"]
    phases = sorted(n for n in vars(dp) if n.startswith("phase_"))
    doc = read(os.path.join(VAULT, "操作-阿奇索单阶段重入调用.md"))
    if not doc:
        print("   ⚠ 找不到单阶段操作页")
        return ["单阶段操作页缺失"]
    missing = [p for p in phases if p not in doc]
    if missing:
        for p in missing:
            print(f"   ✗ {p} 未进单阶段操作页")
        return [f"阶段未入文档 {len(missing)} 个"]
    print(f"   ✓ {len(phases)} 个 phase_* 全部有文档")
    if verbose:
        print("       " + " ".join(phases))
    return []


def main():
    ap = argparse.ArgumentParser(description="文档↔代码一致性检查（只读）")
    ap.add_argument("--verbose", action="store_true", help="打印通过的明细")
    args = ap.parse_args()

    if not os.path.isdir(TOOLS):
        print(f"✗ tools 目录不存在: {TOOLS}")
        return 2

    print("=" * 62)
    print(" 文档↔代码一致性检查（结构检查抓不到的那一半）")
    print("=" * 62)

    mods = [m for m in (load_mod("deploy"), load_mod("create_from_pno"),
                        load_mod("alds_dict")) if m]

    problems = []
    problems += check_signatures(mods, args.verbose)
    problems += check_cli(args.verbose)
    problems += check_modules(args.verbose)
    problems += check_phases(mods, args.verbose)

    print("\n" + "=" * 62)
    if problems:
        print(" 发现漂移：")
        for p in problems:
            print(f"   · {p}")
        print("=" * 62)
        return 1
    print(" 文档与代码一致 ✓")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
