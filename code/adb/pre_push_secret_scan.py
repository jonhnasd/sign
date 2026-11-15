# -*- coding: utf-8 -*-
"""推送前凭据扫描：任何待提交内容里出现明文密钥就拦下。

为什么单独写：`.gitignore` 只能挡「已知路径」，挡不住「把密钥粘进笔记正文」。
2026-11-15 实测库里就有 sops 密文，一旦有人把解密结果贴进 md 再 commit，
git 历史里就永久留痕，删文件也没用。
"""
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

GIT = r"C:\Users\Administrator\.workbuddy\vendor\PortableGit\cmd\git.exe"
VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"

# 高危模式：命中即拒绝推送
PATTERNS = [
    ("JWT", re.compile(r"eyJ0eXAiOiJKV1Qi[A-Za-z0-9_\-\.]{10,}")),
    ("age 私钥", re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]{20,}")),
    ("sops 明文段", re.compile(r"^\s{2,}key:\s*[\"']?[A-Za-z0-9_\-]{16,}", re.M)),
    ("OpenAI 风格 key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("会话 Cookie", re.compile(r"KSSID=[A-Za-z0-9%]{10,}")),
    ("access_token 赋值", re.compile(r"access_token\s*[=:]\s*[\"']?[A-Za-z0-9_\-\.]{20,}")),
    ("私钥块", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

# 白名单：这些是说明性文字，不是真凭据
BENIGN = [
    "AGE-SECRET-KEY-1...",
    "sk-xxxx",
    "eyJ0eXAiOiJKV1Qi...",
    "http_proxy 127.0.0.1:8080",
]


def staged_files():
    out = subprocess.run([GIT, "-C", VAULT, "diff", "--cached", "--name-only"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    return [f for f in out.stdout.split("\n") if f.strip()]


def main():
    files = staged_files()
    if not files:
        print("✓ 暂存区为空，无需扫描")
        return 0

    print(f"扫描 {len(files)} 个暂存文件…")
    hits = []
    for rel in files:
        p = f"{VAULT}\\{rel}"
        try:
            text = open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for lineno, line in enumerate(text.split("\n"), 1):
            if any(b in line for b in BENIGN):
                continue
            for name, pat in PATTERNS:
                if pat.search(line):
                    hits.append((rel, lineno, name, line.strip()[:70]))

    if hits:
        print("\n✗ 发现疑似明文凭据，拒绝推送：")
        for rel, ln, name, txt in hits:
            print(f"   {rel}:{ln}  [{name}]  {txt}")
        print("\n处理：从文件中移除后重新 add；若已 commit，需改写历史（git filter-repo）")
        return 1

    print("✓ 未发现明文凭据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
