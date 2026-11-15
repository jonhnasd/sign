# -*- coding: utf-8 -*-
"""SKU 规格名「类型前缀」判定回归（net-free）。

锁死 2026-11-15 用户要求：
  「sku要写清楚是什么类型，除了时长，会员类型货币类型等sku都要带上，让顾客一目了然」

最容易做错的两件事，本文件重点防：
  ① 误伤多维商品 —— 多维（会员:超级 / 时长:1天）本身已一目了然，不该硬加前缀
  ② 漏判裸档位 —— 单维 `7天` / `1个月` / `500积分` 必须判不合格
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import sku_naming as S

FAIL = []
N = 0


def ck(name, got, want):
    global N
    N += 1
    if got != want:
        FAIL.append("%s: got=%r want=%r" % (name, got, want))
        print("  ✗ %-50s got=%r want=%r" % (name, got, want))
    else:
        print("  ✓ %s" % name)


def mk(dims):
    """dims: [(维度名, 值)] → 伪 SKU"""
    return {"skuId": "1", "price": "1", "propertyList":
            [{"propertyText": d, "valueText": v} for d, v in dims]}


print("=== 裸档位必须判不合格（单维，只有时长）===")
for v in ("7天", "1个月", "12个月", "3个月", "1天", "5天", "14天", "24个月"):
    ck("裸档位 %s" % v, S.judge_sku(mk([("使用周期", v)]))[0], False)

print("\n=== 面额型：值里自带币种 or 维度名说明币种 → 都算清楚 ===")
ck("规格:500积分 → 值自带币种，合格",
   S.judge_sku(mk([("规格", "500积分")]))[0], True)
ck("规格:50元 → 值自带币种，合格", S.judge_sku(mk([("规格", "50元")]))[0], True)
ck("积分:500 → 维度名说清币种，合格",
   S.judge_sku(mk([("积分", "500")]))[0], True)
ck("面额:50元 → 合格", S.judge_sku(mk([("面额", "50元")]))[0], True)
ck("500积分 带币种写法 → 合格", S.judge_sku(mk([("积分", "500积分")]))[0], True)
ck("规格:500 纯数字+维度名没说币种 → 不合格",
   S.judge_sku(mk([("规格", "500")]))[0], False)

print("\n=== 带类型词的必须放行（不能误伤）===")
for v in ("大会员7天", "超级会员1个月", "SVIP7天", "单车7天4次",
          "5元500晋江币", "10000积分", "50元", "设计室会员1个月"):
    ck("带类型 %s" % v, S.judge_sku(mk([("规格", v)]))[0], True)

print("\n=== 多维商品必须放行（这是最容易误伤的地方）===")
ck("会员:超级 / 时长:1天",
   S.judge_sku(mk([("会员", "超级"), ("时长", "1天")]))[0], True)
ck("会员:至臻 / 时长:12个月",
   S.judge_sku(mk([("会员", "至臻"), ("时长", "12个月")]))[0], True)
ck("车型:单车 / 时长:7天 / 次数:4次",
   S.judge_sku(mk([("车型", "单车"), ("时长", "7天"), ("次数", "4次")]))[0], True)

print("\n=== 多维但有维度值为空 → 不合格 ===")
ck("会员:超级 / 时长:(空)",
   S.judge_sku(mk([("会员", "超级"), ("时长", "")]))[0], False)

print("\n=== 首单档：剥掉「首单」后按裸档位判 ===")
ck("首单7天（裸）", S.judge_sku(mk([("时长", "首单7天")]))[0], False)
ck("首单单车7天4次（带类型）", S.judge_sku(mk([("时长", "首单单车7天4次")]))[0], True)

print("\n=== 读不到规格名 → None（人工确认，不硬判）===")
ck("无 propertyList", S.judge_sku({"skuId": "1"})[0], None)
ck("空值", S.judge_sku(mk([("使用周期", "")]))[0], False)

print("\n=== is_bare_tier 直接判定（只管裸时长，不管面额）===")
ck("7天 是裸档位", S.is_bare_tier("7天"), True)
ck("1个月 是裸档位", S.is_bare_tier("1个月"), True)
# 面额型不算裸时长档位：货币单位就是类型信息，由维度名判定
ck("500积分 不算裸时长档位", S.is_bare_tier("500积分"), False)
ck("大会员7天 不是", S.is_bare_tier("大会员7天"), False)
ck("超级会员1个月 不是", S.is_bare_tier("超级会员1个月"), False)

print("\n=== 真实商品整件巡检 ===")
bili = {"itemSkuList": [mk([("使用周期", "7天")]), mk([("使用周期", "1个月")])]}
bad, ok, unk = S.audit_item(bili)
ck("b站商品：2 档全不合格", (len(bad), ok), (2, 0))

soda = {"itemSkuList": [mk([("会员", "VIP"), ("时长", "7天")]),
                        mk([("会员", "SVIP"), ("时长", "12个月")])]}
bad2, ok2, unk2 = S.audit_item(soda)
ck("汽水音乐：2 档全合格", (len(bad2), ok2), (0, 2))

print("\n=== type_prefix 推导 ===")
p, _ = S.type_prefix("【自动充值】哔哩哔哩大会员 7天/1个月 直充自己账号")
ck("从标题抽前缀", "大会员" in p or "哔哩哔哩大会员" in p, True)
p2, why = S.type_prefix("", "")
ck("空输入不猜", p2, "")

print()
if FAIL:
    print("=== 失败 %d / %d ===" % (len(FAIL), N))
    for f in FAIL:
        print("   " + f)
    sys.exit(1)
print("=== 通过 %d / %d ✅ SKU 类型前缀判定已锁死 ===" % (N, N))
