#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""换机器体检：一条命令告诉你「能不能跑、缺什么、怎么补」。

和 `preflight_env.py` 的分工
---------------------------
- `preflight_env.py`：**给 harness 调用的**机器可读自检（JSON，ready/fatal）。
- `doctor.py`：**给人/给 agent 看的**迁移体检。除了调用 preflight，还会：
  ① 逐项打印「期望 / 实际 / 来源 / 怎么修」；
  ② 检查知识库两道检查器在不在；
  ③ 给出**可直接复制的修复命令**（环境变量写法）；
  ④ 支持 `--fix-env` 打印一段可粘贴的环境变量设置。

设计约束
--------
只读。不建草稿、不发布、不生图、不改线上商品、不写任何文件。
退出码：0 = 可以跑一条龙；1 = 有致命项；2 = doctor 自身无法运行。

用法
----
    python doctor.py                # 完整体检
    python doctor.py --json         # 机器可读
    python doctor.py --fix-env      # 只打印环境变量修复片段
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ENV_HINTS = {
    "workspace": "DSH_WORKSPACE",
    "vault": "DSH_VAULT",
    "sops_bin": "DSH_SOPS_BIN",
    "age_key": "DSH_AGE_KEY",
    "credentials": "DSH_CREDENTIALS",
    "assets_dir": "DSH_VAULT",        # 由 vault 推导
    "kuaipao_gen": "DSH_KUAIPAO",
    "bridge_port": "DSH_BRIDGE_PORT",
}

REQUIRED_SCRIPTS = (
    "create_from_pno.py", "deploy.py", "onepipe_guard.py",
    "replica_main_image.py", "agiso_direct.py", "paths.py",
    "alds_kit/__init__.py", "alds_kit/main_image.py", "alds_kit/media.py",
    "alds_kit/item.py", "alds_kit/supplier.py", "alds_kit/copy.py",
    "alds_kit/contract.py", "alds_kit/supplier.py",
)

VAULT_CHECKERS = (
    r"C:\Users\Administrator\.workbuddy\tools\adb\check_vault.py",
    r"C:\Users\Administrator\.workbuddy\tools\adb\check_doc_code.py",
)


def _http_json(url, timeout=3.0):
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


class Row:
    __slots__ = ("name", "desc", "ok", "detail", "fix", "fatal")

    def __init__(self, name, desc, ok, detail="", fix="", fatal=True):
        self.name, self.desc, self.ok = name, desc, ok
        self.detail, self.fix, self.fatal = detail, fix, fatal

    def as_dict(self):
        return {"name": self.name, "desc": self.desc, "ok": self.ok,
                "detail": self.detail, "fix": self.fix, "fatal": self.fatal}


def check_paths():
    rows = []
    try:
        from paths import CFG
    except Exception as e:
        return [Row("paths.py", "配置解析模块", False,
                    f"导入失败: {e}", "确认 paths.py 与 doctor.py 同目录", True)]

    for item in CFG.describe():
        name, path, ok, src = item["name"], item["path"], item["ok"], item["source"]
        env = ENV_HINTS.get(name, "—")
        if item["name"] == "bridge_port":
            rows.append(Row(name, item["desc"], True, path, "", False))
            continue
        # 可选项目不致命
        fatal = name not in ("kuaipao_gen",)
        if src in ("env_bad", "env_bad_missing"):
            # 🔴 环境变量设了但无效 —— 这条必须报错，否则「设错」会被静默忽略
            rows.append(Row(name, item["desc"], False,
                            f"环境变量 {env} 指向不存在的路径，已回落",
                            f'改对或删掉 {env}（当前值无效）', True))
            continue
        if ok:
            rows.append(Row(name, item["desc"], True,
                            f"{path}  [来源:{src}]", "", fatal))
        else:
            fix = (f'set {env}=<正确路径>' if env != "—" else "见 paths.py 顶部说明")
            rows.append(Row(name, item["desc"], False,
                            f"未找到（来源:{src}）", fix, fatal))
    return rows


def check_scripts():
    missing = [s for s in REQUIRED_SCRIPTS if not (HERE / s).exists()]
    if missing:
        return Row("scripts", "核心脚本", False,
                   "缺: " + ", ".join(sorted(set(missing))),
                   "从原机器完整拷贝 edge-bridge/tools/ 目录", True)
    return Row("scripts", "核心脚本", True, f"{len(set(REQUIRED_SCRIPTS))} 个齐全")


def check_bridge():
    try:
        from paths import CFG
        url = CFG.bridge_health
    except Exception:
        url = "http://127.0.0.1:8787/health"
    try:
        d = _http_json(url)
    except Exception as e:
        return Row("bridge", "桥接服务 8787", False,
                   f"连不上: {type(e).__name__}",
                   "① 双击 edge-bridge 启动脚本 ② 打开 Edge ③ 确认扩展已启用 "
                   "④ curl 必须加 --noproxy '*'", True)
    ok = bool(d.get("extConnected"))
    if ok:
        return Row("bridge", "桥接服务 8787", True, "extConnected=true")
    return Row("bridge", "桥接服务 8787", False,
               f"服务在跑但 extConnected={d.get('extConnected')}",
               "打开 Edge 并登录 agiso；edge://extensions 里启用 Edge Bridge", True)


def check_sops():
    try:
        from paths import CFG
    except Exception:
        return Row("sops", "凭据解密", False, "paths 不可用", "", True)
    if not CFG.has_credentials:
        return Row("sops", "凭据解密", False,
                   "sops/age/凭据文件 三者不全",
                   "拷 .workbuddy/tools/crypto/ 整个目录 + secrets/credentials.sops.yaml，"
                   "或设 DSH_SOPS_BIN / DSH_AGE_KEY / DSH_CREDENTIALS", True)
    try:
        out = subprocess.run(
            [str(CFG.sops_bin), "--decrypt", "--extract", '["kuaipao"]',
             str(CFG.credentials)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "SOPS_AGE_KEY_FILE": str(CFG.age_key)}, timeout=25)
        if out.returncode == 0:
            return Row("sops", "凭据解密", True, "可解密（明文不打印）")
        return Row("sops", "凭据解密", False,
                   f"解密失败 rc={out.returncode}",
                   "确认 age 私钥与加密文件配对（换机器最容易错的一项）", True)
    except Exception as e:
        return Row("sops", "凭据解密", False, f"{type(e).__name__}: {e}",
                   "检查 sops 可执行权限", True)


def check_checkers():
    found = [p for p in VAULT_CHECKERS if Path(p).exists()]
    if len(found) == len(VAULT_CHECKERS):
        return Row("checkers", "知识库检查器", True, "2 个都在")
    return Row("checkers", "知识库检查器", False,
               f"缺 {len(VAULT_CHECKERS)-len(found)} 个",
               "拷 .workbuddy/tools/adb/ 整个目录（check_vault/check_doc_code）", False)


def check_vault():
    try:
        from paths import CFG
    except Exception:
        return Row("vault", "Obsidian 库", False, "paths 不可用", "", True)
    if not CFG.vault:
        return Row("vault", "Obsidian 库", False, "未找到库根",
                   "设 DSH_VAULT=<库根>", True)
    key_notes = ["长期记忆.md", "经验-踩坑手册.md", "操作-阿奇索单阶段重入调用.md"]
    miss = [n for n in key_notes if not (CFG.vault / n).exists()]
    if miss:
        return Row("vault", "Obsidian 库", False,
                   f"{CFG.vault} 缺关键笔记: {', '.join(miss)}",
                   "确认拷的是完整库，不是部分导出", True)
    return Row("vault", "Obsidian 库", True, f"{CFG.vault} 关键笔记齐全")


def check_python():
    v = sys.version_info
    ok = v >= (3, 10)
    return Row("python", "Python 版本", ok, f"{v.major}.{v.minor}.{v.micro}",
               "需 >= 3.10（用到 3.10+ 语法）", True)


def check_location():
    """本目录是否就是「真正在用的」那份 tools。

    🔴 为什么要有这条：复制一份 tools 到别处（迁移演练、临时备份）也能全绿，
       但改了那份的代码不会影响实际在跑的那份 —— 最容易白干一下午。
    """
    canon = Path(r"C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41\edge-bridge\tools")
    here = HERE
    try:
        same = here.resolve() == canon.resolve()
    except Exception:
        same = False
    if same:
        return Row("location", "工作目录", True, str(here), "", False)
    if canon.is_dir():
        return Row("location", "工作目录", False,
                   f"当前在副本里跑：{here}（正式位置是 {canon}）",
                   "确认你要改的是哪一份；改副本不会影响线上",
                   False)
    return Row("location", "工作目录", True,
               f"{here}（正式位置不存在，按新机器处理）", "", False)


def main():
    ap = argparse.ArgumentParser(description="换机器体检（只读）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fix-env", action="store_true",
                    help="只打印环境变量修复片段")
    args = ap.parse_args()

    rows = [check_python(), check_location()]
    rows += check_paths()
    rows += [check_scripts(), check_bridge(), check_sops(),
             check_vault(), check_checkers()]

    fatal_bad = [r for r in rows if not r.ok and r.fatal]
    warn_bad = [r for r in rows if not r.ok and not r.fatal]

    if args.fix_env:
        print("# 换机器：把下面几行设成新机器上的真实路径，再跑 python doctor.py")
        print("# PowerShell 用 $env:NAME='值'；bash 用 export NAME='值'\n")
        cur = {}
        try:
            from paths import CFG
            cur = {r["name"]: r for r in CFG.describe()}
            for e in CFG.env_errors:
                print(f"# ✗ {e['env']} 当前值无效: {e['value']}")
        except Exception:
            pass
        printed = 0
        for name, env in ENV_HINTS.items():
            if env == "—" or name in ("assets_dir", "kuaipao_gen", "bridge_port"):
                continue
            info = cur.get(name) or {}
            good = info.get("path")
            src = info.get("source")
            if good and src in ("env", "probe", "default"):
                # 已解析到可用路径 → 换机器时这行是「新机器上要改成什么」，不是照抄旧值
                print(f"# ✓ {info.get('desc', name)} 已就绪（本机: {good}）")
                print(f"#    换机器时改成新机器上的对应路径：$env:{env} = '<新路径>'")
                continue
            print(f"# ✗ {info.get('desc', name)} 未就绪（当前: {good or '未找到'}）")
            print(f"$env:{env} = '<新机器上的路径>'")
            printed += 1
        if not printed:
            print("\n# 本机全部就绪。换机器时只需按上面每行的提示改路径。")
        print("\n# 想让设置长期生效：setx NAME \"<路径>\"（Windows）或写进 ~/.bashrc（bash）")
        return 0

    if args.json:
        print(json.dumps({
            "ok": not fatal_bad,
            "fatal": [r.as_dict() for r in fatal_bad],
            "warnings": [r.as_dict() for r in warn_bad],
            "all": [r.as_dict() for r in rows],
        }, ensure_ascii=False, indent=2))
        return 0 if not fatal_bad else 1

    print("=" * 68)
    print(" 换机器体检 · 一条龙运行时")
    print("=" * 68)
    for r in rows:
        mark = "✓" if r.ok else ("✗" if r.fatal else "⚠")
        print(f" {mark} {r.name:<12} {r.desc:<18} {r.detail}")
        if not r.ok and r.fix:
            print(f"     └─ 怎么修: {r.fix}")
    print("=" * 68)
    if fatal_bad:
        print(f" 结论：还不能跑一条龙（{len(fatal_bad)} 项致命）")
        print(" 下一步：python doctor.py --fix-env    # 打印要设的环境变量")
        print("=" * 68)
        return 1
    print(f" 结论：可以跑一条龙 ✓"
          + (f"（{len(warn_bad)} 项非致命警告）" if warn_bad else ""))
    print(" 下一步：python preflight_env.py  →  ready 必须为 true")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
