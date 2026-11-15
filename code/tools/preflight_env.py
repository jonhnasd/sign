#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读环境自检：判断「本机一条龙运行时」是否就绪，供外部 harness 调用。

设计约束（给迁移用）：
- 不写任何业务数据、不调任何写接口、不建草稿、不发布、不生图。
- 输出 JSON（ensure_ascii=False），退出码 0 = 无致命项，1 = 有致命项。
- 绝不打印凭据明文：sops 解密结果只返回 bool。

用法：
  python preflight_env.py                # 全量自检
  python preflight_env.py --no-token     # 跳过 agiso token 现取
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 🔴 2026-11-15：路径全部走 paths.py，不再写死 `C:\Users\Administrator\...`。
#    换机器只需设环境变量或让自动探测生效，见 paths.py 顶部说明。
try:
    from paths import CFG
except Exception:                      # 极端情况下（paths.py 缺失）退回本机默认
    CFG = None

BRIDGE_HEALTH = CFG.bridge_health if CFG else "http://127.0.0.1:8787/health"
SOPS_BIN = (CFG.sops_bin if CFG else None) or Path(r"C:\Users\Administrator\.workbuddy\tools\crypto\sops.exe")
AGE_KEY = (CFG.age_key if CFG else None) or Path(r"C:\Users\Administrator\.workbuddy\tools\crypto\age\keys.txt")
CRED_YAML = (CFG.credentials if CFG else None) or Path(r"C:\Users\Administrator\Desktop\obisidian\obisidian\secrets\credentials.sops.yaml")
ASSETS_DIR = (CFG.assets_dir if CFG else None) or Path(r"C:\Users\Administrator\Desktop\obisidian\obisidian\货源素材")
KUAIPAO_GEN = (CFG.kuaipao_gen if CFG else None) or Path(r"C:\Users\Administrator\Desktop\workbuddy\文档提取\_yq_poster\kuaipao_gen.py")

REQUIRED_SCRIPTS = (
    "create_from_pno.py",
    "deploy.py",
    "onepipe_guard.py",
    "replica_main_image.py",
    "agiso_direct.py",
    "alds_kit/__init__.py",
    "alds_kit/main_image.py",
    "alds_kit/media.py",
    "alds_kit/item.py",
    "alds_kit/supplier.py",
)
OPTIONAL_ASSETS = (
    ASSETS_DIR / "货源商品清单.json",
    ASSETS_DIR / "货源素材_详情.json",
)


def _http_json(url: str, timeout: float = 3.0):
    """强制不走系统代理，避免 127.0.0.1 被代理劫持。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _bridge():
    try:
        d = _http_json(BRIDGE_HEALTH)
        return {
            "reachable": True,
            "ok": bool(d.get("ok")),
            "extConnected": bool(d.get("extConnected")),
            "wsConnected": bool(d.get("wsConnected")),
            "swAlive": bool(d.get("swAlive")),
            "note": d.get("note", ""),
        }
    except Exception as exc:
        return {"reachable": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def _token():
    """只返回 bool，绝不回传 token 值。open_if_missing=False 不主动新开标签。"""
    try:
        sys.path.insert(0, str(HERE))
        import agiso_direct as A
        A.TOKEN = A.token_from_browser(open_if_missing=False)
        return {"obtained": bool(A.TOKEN)}
    except Exception as exc:
        return {"obtained": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def _kuaipao_key():
    """复用生产链路的解密函数，只回报 True/False，不落盘、不打印明文。"""
    try:
        os.environ.setdefault("SOPS_AGE_KEY_FILE", str(AGE_KEY))
        sys.path.insert(0, str(HERE))
        from alds_kit.main_image import get_kuaipao_key
        return {"decryptable": bool(get_kuaipao_key())}
    except Exception as exc:
        return {"decryptable": False, "error": "%s: %s" % (type(exc).__name__, exc)}


def _scripts():
    return {name: (HERE / name).is_file() for name in REQUIRED_SCRIPTS}


def run(with_token: bool = True) -> dict:
    fatal, warnings = [], []

    bridge = _bridge()
    if not (bridge.get("reachable") and bridge.get("extConnected") and bridge.get("wsConnected")):
        fatal.append("edge-bridge 未就绪：需要 127.0.0.1:8787 extConnected=true 且已登录 aldsidle.agiso.com")

    scripts = _scripts()
    missing = [k for k, v in scripts.items() if not v]
    if missing:
        fatal.append("缺少业务脚本: " + ", ".join(missing))

    writable = os.access(str(HERE), os.W_OK)
    if not writable:
        fatal.append("tools 目录不可写：snapshots / spec / manifest 无法落盘")

    crypto = {
        "sops_bin": SOPS_BIN.is_file(),
        "age_key": AGE_KEY.is_file(),
        "credentials_yaml": CRED_YAML.is_file(),
    }
    for k, v in crypto.items():
        if not v:
            fatal.append("凭据链缺失: " + k)

    token = _token() if with_token else {"obtained": None, "skipped": True}
    if token.get("obtained") is False:
        warnings.append("agiso token 现取失败；生产链路仍可能靠 Edge leveldb 兜底，但不可靠")

    assets = {p.name: p.is_file() for p in OPTIONAL_ASSETS}
    for k, v in assets.items():
        if not v:
            warnings.append("固定素材库缺文件: %s（影响复刻参考图，可用 --ref 或 --noimg 绕开）" % k)
    if not KUAIPAO_GEN.is_file():
        warnings.append("缺 kuaipao_gen.py：--go 的复刻生图阶段会失败（dry 不受影响）")

    kuaipao = _kuaipao_key() if all(crypto.values()) else {"decryptable": False, "skipped": True}
    if kuaipao.get("decryptable") is False and not kuaipao.get("skipped"):
        warnings.append("快跑 key 解密失败：生图阶段会失败（dry 不受影响）")

    return {
        "ready": not fatal,
        "fatal": fatal,
        "warnings": warnings,
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "tools_dir": str(HERE),
        "bridge": bridge,
        "agiso_token": token,
        "scripts": scripts,
        "writable": writable,
        "crypto": crypto,
        "kuaipao_key": kuaipao,
        "assets": assets,
        "kuaipao_gen": KUAIPAO_GEN.is_file(),
        "boundaries": [
            "本自检只读；不建草稿、不发布、不生图、不改线上商品",
            "凭据明文不入库、不打印；sops 仅回报是否可解密",
            "主图逐字视觉核验仍需外部多模态/人工，不能用本自检代替",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="一条龙运行时只读自检")
    ap.add_argument("--no-token", action="store_true", help="跳过 agiso token 现取")
    args = ap.parse_args()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    result = run(with_token=not args.no_token)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
