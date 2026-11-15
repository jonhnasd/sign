# -*- coding: utf-8 -*-
"""推送前凭据扫描（通用版）：对任意仓库的暂存区做明文密钥检测。

与 adb/pre_push_secret_scan.py 的区别：那个写死 vault 路径，这个接受 --repo 参数，
供 edge-bridge 等多个仓库复用。
"""
import argparse
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

GIT = r"C:\Users\Administrator\.workbuddy\vendor\PortableGit\cmd\git.exe"

PATTERNS = [
    ("JWT", re.compile(r"eyJ0eXAiOiJKV1Qi[A-Za-z0-9_\-\.]{10,}")),
    ("age 私钥", re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]{20,}")),
    ("OpenAI 风格 key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("会话 Cookie", re.compile(r"KSSID=[A-Za-z0-9%]{10,}")),
    ("access_token 赋值", re.compile(r"access_token\s*[=:]\s*[\"']?[A-Za-z0-9_\-\.]{20,}")),
    ("私钥块", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("阿里云 AK", re.compile(r"\bLTAI[A-Za-z0-9]{12,}")),
    ("硬编码密码", re.compile(r"(?i)\b(password|passwd|pwd)\s*[=:]\s*[\"'][^\"'\s]{8,}[\"']")),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{25,}")),
]

BENIGN = [
    "AGE-SECRET-KEY-1...", "sk-xxxx", "eyJ0eXAiOiJKV1Qi...",
    "http_proxy 127.0.0.1:8080", "127.0.0.1:52510",
]


def main():
    ap = argparse.ArgumentParser(description="推送前凭据扫描")
    ap.add_argument("--repo", required=True, help="仓库根目录")
    ap.add_argument("--all", action="store_true",
                    help="扫描工作区全部文件而非仅暂存区")
    args = ap.parse_args()

    cmd = [GIT, "-C", args.repo, "ls-files" if args.all else "diff", "--cached"]
    if not args.all:
        cmd.append("--name-only")
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    files = [f for f in out.stdout.split("\n") if f.strip()]

    if not files:
        print("✓ 无待扫描文件")
        return 0

    print(f"扫描 {len(files)} 个文件…")
    hits = []
    for rel in files:
        p = f"{args.repo}\\{rel.replace('/', chr(92))}"
        try:
            text = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for lineno, line in enumerate(text.split("\n"), 1):
            if any(b in line for b in BENIGN):
                continue
            for name, pat in PATTERNS:
                if pat.search(line):
                    hits.append((rel, lineno, name, line.strip()[:66]))

    if hits:
        print("\n✗ 发现疑似明文凭据，拒绝推送：")
        for rel, ln, name, txt in hits[:30]:
            print(f"   {rel}:{ln}  [{name}]  {txt}")
        if len(hits) > 30:
            print(f"   … 另 {len(hits)-30} 处")
        return 1

    print("✓ 未发现明文凭据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
