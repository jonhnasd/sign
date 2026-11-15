# -*- coding: utf-8 -*-
"""运行时路径与环境配置 —— 换机器的唯一改动点。

为什么有这个文件
----------------
2026-11-15 实测：核心链路（deploy/create_from_pno/alds_kit）本来零写死，
但 `preflight_env.py`、`main_image.py`、`fetch_supplier_assets.py`、
`replica_main_image.py` 一共写了 17 处 `C:\\Users\\Administrator\\...`。
换台机器、换个用户名、换个盘符，这 17 处全断，而且断法各不相同
（找不到 sops、找不到素材、找不到 key），每个都要单独排查一遍。

设计原则
--------
1. **环境变量优先**：`DSH_VAULT`、`DSH_SOPS_BIN` 等设了就按设的走。
2. **其次自动发现**：从本文件位置往上找库根/工具根，不猜用户名。
3. **最后才用默认值**：默认值只是「本机已知位置」，不是硬要求。
4. **缺失不抛异常**：返回 None 或 False，由调用方决定是致命还是警告。
   —— 换机器时最怕的是 import 期就崩，那样连诊断都跑不了。

用法
----
    from paths import CFG
    CFG.vault_dir          # Obsidian 库根
    CFG.sops_bin           # sops 可执行
    CFG.assets_dir         # 货源素材目录
    CFG.describe()         # 打印解析结果与来源（doctor 用）
"""
from __future__ import annotations

import os
from pathlib import Path

# ── 环境变量名（统一 DSH_ 前缀，便于迁移时一次性覆盖）──────────
ENV_VAULT = "DSH_VAULT"
ENV_SOPS = "DSH_SOPS_BIN"
ENV_AGE_KEY = "DSH_AGE_KEY"
ENV_CRED = "DSH_CREDENTIALS"
ENV_WORKSPACE = "DSH_WORKSPACE"      # WorkBuddy 任务目录
ENV_KUAIPAO = "DSH_KUAIPAO_GEN"
ENV_BRIDGE = "DSH_BRIDGE_PORT"
ENV_PYTHON = "DSH_PYTHON"            # 指定解释器（换机器时最容易错的一项）

HERE = Path(__file__).resolve().parent          # .../edge-bridge/tools
EDGE_BRIDGE = HERE.parent                        # .../edge-bridge
WORKSPACE_DEFAULT = EDGE_BRIDGE.parent           # .../2026-09-22-11-37-41


def _first_dir(*cands):
    for c in cands:
        if c:
            p = Path(c)
            if p.is_dir():
                return p
    return None


def _first_file(*cands):
    for c in cands:
        if c:
            p = Path(c)
            if p.is_file():
                return p
    return None


class Config:
    """解析一次，全流程复用。每个属性都保证不抛异常。"""

    def __init__(self):
        self.sources = {}       # 属性名 -> 解析来源（doctor 展示用）
        self.env_errors = []    # 环境变量设了但路径无效的记录（doctor 必须报）

        # ── 工作区（WorkBuddy 任务目录）──
        # 注意：默认值用「本文件上两级」，这样整个目录搬走也能自洽；
        # 若上层不是 WorkBuddy 任务目录（例如复制到别处做迁移测试），
        # 仍以本文件位置为准，绝不猜 C 盘旧路径。
        self.workspace = self._pick(
            "workspace", is_dir=True,
            cands=[os.environ.get(ENV_WORKSPACE), WORKSPACE_DEFAULT],
        )

        # ── Obsidian 库根：环境变量 → 常见位置 → 工作区兄弟 ──
        self.vault = self._pick(
            "vault", is_dir=True,
            cands=[
                os.environ.get(ENV_VAULT),
                Path.home() / "Desktop" / "obisidian" / "obisidian",
                Path.home() / "Documents" / "obisidian" / "obisidian",
                WORKSPACE_DEFAULT / "obisidian",
            ],
        )

        # ── 凭据与解密工具 ──
        crypto_dir = Path.home() / ".workbuddy" / "tools" / "crypto"
        self.sops_bin = self._pick(
            "sops_bin", is_dir=False,
            cands=[os.environ.get(ENV_SOPS),
                   crypto_dir / "sops.exe",
                   crypto_dir / "sops"],
        )
        self.age_key = self._pick(
            "age_key", is_dir=False,
            cands=[os.environ.get(ENV_AGE_KEY), crypto_dir / "age" / "keys.txt"],
        )
        self.credentials = self._pick(
            "credentials", is_dir=False,
            cands=[os.environ.get(ENV_CRED),
                   (self.vault / "secrets" / "credentials.sops.yaml") if self.vault else None],
        )

        # ── 货源素材（库内快照）──
        self.assets_dir = (self.vault / "货源素材") if self.vault else None
        if self.assets_dir and not self.assets_dir.is_dir():
            self.assets_dir = None

        # ── 快跑生图（可选，缺了只是少一种生图方式）──
        self.kuaipao_gen = self._pick(
            "kuaipao_gen", is_dir=False,
            cands=[os.environ.get(ENV_KUAIPAO),
                   Path.home() / "Desktop" / "workbuddy" / "文档提取" / "_yq_poster" / "kuaipao_gen.py"],
        )

        # ── 解释器（2026-11-15 新增）──
        # 为什么需要：doctor.py 原本只报 `sys.version_info`，即「你运行 doctor
        # 用的那个 python」。换机器时这恰好是最容易错的一环 —— 报告的是「当下
        # 碰巧是哪个」，不是「该用哪个」，所以它永远绿，问题留到真正跑批时才炸。
        # 这里显式解析一个**确定的**解释器路径，让 doctor 能对比「该用」与「在用」。
        self.python = self._pick(
            "python", is_dir=False,
            cands=[
                os.environ.get(ENV_PYTHON),
                # WorkBuddy 便携 python（本机既有安装）
                Path.home() / ".workbuddy" / "binaries" / "python" / "versions" / "3.13.12" / "python.exe",
                # DSH 自带运行时 python
                Path.home() / ".dsh" / "dsh-runtimes" / "dsh-primary-runtime"
                / "dependencies" / "python" / "python.exe",
            ],
        )

        # ── 桥接端口 ──
        try:
            self.bridge_port = int(os.environ.get(ENV_BRIDGE) or 8787)
            self.sources["bridge_port"] = "env" if os.environ.get(ENV_BRIDGE) else "default"
        except ValueError:
            self.bridge_port = 8787
            self.sources["bridge_port"] = "default(非法值回落)"

        self.bridge_health = f"http://127.0.0.1:{self.bridge_port}/health"

    # ── 内部：带来源记录的解析 ──
    def _pick(self, name, *, is_dir: bool, cands):
        """按优先级取第一个存在的路径，并记录来源。

        来源标记：
          env      环境变量给了且有效
          env_bad  环境变量给了但路径不存在（回落到后面的候选）—— 必须能被 doctor 看到，
                   否则换机器时「设了环境变量但设错」会被静默忽略，人以为配好了。
          probe    自动探测命中
          default  内置默认命中
          missing  全都没找到
        """
        env_name = self._env_of(name)
        env_val = os.environ.get(env_name) if env_name else None
        env_bad = bool(env_val) and not Path(env_val).exists()

        for i, c in enumerate(cands):
            if not c:
                continue
            p = Path(c)
            if (p.is_dir() if is_dir else p.is_file()):
                if i == 0 and env_val and Path(env_val) == p:
                    src = "env"
                elif env_bad and i > 0:
                    src = "env_bad"
                elif i == len(cands) - 1:
                    src = "default"
                else:
                    src = "probe"
                self.sources[name] = src
                if src == "env_bad":
                    self.env_errors.append(
                        {"name": name, "env": env_name,
                         "value": env_val, "used": str(p)})
                return p
        self.sources[name] = "env_bad_missing" if env_bad else "missing"
        if env_bad:
            self.env_errors.append(
                {"name": name, "env": env_name, "value": env_val, "used": None})
        return None

    @staticmethod
    def _env_of(name):
        return {"vault": ENV_VAULT, "sops_bin": ENV_SOPS, "age_key": ENV_AGE_KEY,
                "credentials": ENV_CRED, "workspace": ENV_WORKSPACE,
                "kuaipao_gen": ENV_KUAIPAO, "python": ENV_PYTHON}.get(name, "")

    # ── 便捷判断 ──
    @property
    def has_credentials(self):
        return bool(self.sops_bin and self.age_key and self.credentials)

    @property
    def env_ok(self):
        """环境变量是否全部有效（doctor 的致命项之一）。"""
        return not self.env_errors

    def describe(self):
        rows = [
            ("workspace", self.workspace, "WorkBuddy 任务目录"),
            ("vault", self.vault, "Obsidian 库根"),
            ("sops_bin", self.sops_bin, "sops 可执行"),
            ("age_key", self.age_key, "age 私钥"),
            ("credentials", self.credentials, "加密凭据文件"),
            ("assets_dir", self.assets_dir, "货源素材目录"),
            ("kuaipao_gen", self.kuaipao_gen, "快跑生图脚本（可选）"),
            ("python", self.python, "指定解释器（换机器关键项）"),
        ]
        out = []
        for name, val, desc in rows:
            out.append({
                "name": name,
                "desc": desc,
                "path": str(val) if val else None,
                "source": self.sources.get(name, "?"),
                "ok": bool(val),
            })
        out.append({
            "name": "bridge_port", "desc": "桥接端口",
            "path": self.bridge_health,
            "source": self.sources.get("bridge_port", "?"),
            "ok": True,
        })
        return out


CFG = Config()

if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(CFG.describe(), ensure_ascii=False, indent=2))
