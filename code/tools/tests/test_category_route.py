# -*- coding: utf-8 -*-
"""类目线路判定回归（category_route.py）。

背景：2026-11-15 实测事故 —— 拿 b 站商品（categoryId=50023914 剪映线）当模板
建抖音短剧，发布报 `Remote service error，类目检查限制,请联系闲鱼运营`。
换 50025461 后一次成功。

锁死：
  ① 通用线路原样保留
  ② 受限线路 + 非专属品类 → 必须纠偏回通用线路
  ③ 受限线路 + 专属品类 → 保留（不能误伤剪映自己的商品）
  ④ 未知类目 → 回退通用线路（保守）
  ⑤ 返回结构完整
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import category_route as C

ok_n = 0
bad = []


def ck(name, got, want):
    global ok_n
    if got == want:
        ok_n += 1
        print("  ✓ %s" % name)
    else:
        bad.append("%s: got=%r want=%r" % (name, got, want))
        print("  ✗ %s   got=%r want=%r" % (name, got, want))


GEN_ID = 50025461
GEN_CH = "35d467e7358057b0a7f7e02f36b0b49a"
JY_ID = 50023914
JY_CH = "4687e5abc9d918d7a7f7e02f36b0b49a"

print("=== ① 通用线路原样保留 ===")
r = C.resolve(GEN_ID, GEN_CH, "抖音短剧会员14天", verbose=False)
ck("categoryId 不变", r["categoryId"], GEN_ID)
ck("未发生纠偏", r["switched_from"], None)

print("\n=== ② 受限线路 + 非专属品类 → 纠偏（这是本次事故场景）===")
r = C.resolve(JY_ID, JY_CH, "抖音短剧会员14天", verbose=False)
ck("纠偏到通用线路", r["categoryId"], GEN_ID)
ck("channelCatId 跟着换", r["channelCatId"], GEN_CH)
ck("记录来源", r["switched_from"], JY_ID)
ck("带 spBizType=25", r["spBizType"], "25")

print("\n=== ③ 受限线路 + 专属品类 → 保留（不许误伤剪映）===")
for t in ("剪映SVIP会员1个月", "必剪会员月卡", "快影VIP 30天", "醒图会员"):
    r = C.resolve(JY_ID, JY_CH, t, verbose=False)
    ck("「%s」保留剪映线路" % t, r["categoryId"], JY_ID)

print("\n=== ④ 未知类目 → 回退通用线路 ===")
r = C.resolve(99999999, "whatever", "某商品", verbose=False)
ck("未知类目回退通用", r["categoryId"], GEN_ID)
ck("记录来源", r["switched_from"], 99999999)

print("\n=== ⑤ 返回结构完整 ===")
r = C.resolve(GEN_ID, GEN_CH, "x", verbose=False)
for k in ("categoryId", "channelCatId", "spBizType", "name", "reason"):
    ck("含字段 %s" % k, k in r and r[k] not in (None, ""), True)

print("\n=== ⑥ 通用线路常量自洽 ===")
ck("GENERAL.categoryId", C.GENERAL["categoryId"], 50025461)
ck("GENERAL.spBizType", C.GENERAL["spBizType"], "25")
ck("受限线路含剪映线", JY_ID in C.RESTRICTED, True)

print()
if bad:
    print("=== 失败 %d / %d ===" % (len(bad), ok_n + len(bad)))
    for b in bad:
        print("   ", b)
    sys.exit(1)
print("=== 通过 %d / %d ✅ 类目线路判定已锁死 ===" % (ok_n, ok_n))
