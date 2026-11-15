# -*- coding: utf-8 -*-
"""onepipe_guard 命令行参数解析回归（net-free）。

锁死 2026-11-15 修的缺陷：
  `python onepipe_guard.py --inspect <gid>` 的位置参数被**静默丢弃** ——
  只要 args 里没有 `--gid` 就走 inspect_all()，去读 _live_gids_fresh.json
  里硬编码的旧 9 个商品。

后果很恶劣：查 A 商品拿到 B 商品的报告，且无任何提示。
巡检工具谎报比没有工具更危险 —— 本文件就是防它复发。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import onepipe_guard as G

FAIL = []
N = 0


def ck(name, got, want):
    global N
    N += 1
    if got != want:
        FAIL.append("%s: got=%r want=%r" % (name, got, want))
        print("  ✗ %-46s got=%r want=%r" % (name, got, want))
    else:
        print("  ✓ %s" % name)


GID = "1098282127320"
GID2 = "1098282127321"

print("=== 核心修复：位置参数必须被识别（原先被丢弃）===")
ck("--inspect <gid>", G.parse_targets(["--inspect", GID])[0], [GID])
ck("bare <gid>", G.parse_targets([GID])[0], [GID])

print("\n=== 其他等价写法 ===")
ck("--inspect --gid <gid>", G.parse_targets(["--inspect", "--gid", GID])[0], [GID])
ck("--gid=<gid>", G.parse_targets(["--inspect", "--gid=" + GID])[0], [GID])
ck("多个 --gid", G.parse_targets(["--gid", GID, "--gid", GID2])[0], [GID, GID2])
ck("多个位置参数", G.parse_targets(["--inspect", GID, GID2])[0], [GID, GID2])
ck("gid 去重", G.parse_targets(["--inspect", GID, GID, "--gid", GID])[0], [GID])

print("\n=== 不带 ID → 空列表（调用方回落到全量清单）===")
ck("--inspect", G.parse_targets(["--inspect"])[0], [])
ck("--self-test", G.parse_targets(["--self-test"])[0], [])

print("\n=== 非法输入必须**报错**，绝不静默忽略 ===")
g, p = G.parse_targets(["--inspect", "abc"])
ck("非数字被拒", g, [])
ck("非数字有提示", len(p), 1)
g, p = G.parse_targets(["--inspect", "--gid"])
ck("--gid 缺值 → 无目标", g, [])
ck("--gid 缺值 → 有提示", len(p), 1)
g, p = G.parse_targets(["--inspect", "123"])
ck("位数过短(3位)被拒", g, [])
g, p = G.parse_targets(["--inspect", "1098282127320extra"])
ck("含字母被拒", g, [])

print("\n=== _looks_like_gid 边界 ===")
ck("8 位（下界）", G._looks_like_gid("12345678"), True)
ck("7 位（过短）", G._looks_like_gid("1234567"), False)
ck("20 位（上界）", G._looks_like_gid("1" * 20), True)
ck("21 位（过长）", G._looks_like_gid("1" * 21), False)
ck("空串", G._looks_like_gid(""), False)
ck("前后空格", G._looks_like_gid("  " + GID + "  "), True)

print()
if FAIL:
    print("=== 失败 %d / %d ===" % (len(FAIL), N))
    for f in FAIL:
        print("   " + f)
    sys.exit(1)
print("=== 通过 %d / %d ✅ --inspect <gid> 不再被丢弃 ===" % (N, N))
