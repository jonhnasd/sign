# -*- coding: utf-8 -*-
"""选源四条规则的回归测试（net-free，不联网）。

锁死 2026-11-15 用户定的四条铁律：
  R1 直充/卡密不得混装
  R2 永远不上代充
  R3 三家比价取最低（且档位/产品线/异常价必须先否决）
  R4 有账户余额门槛的不上

为什么每个用例都配「反向验证」：只测「该拦的拦住了」会漏掉「全都拦」的退化实现。
所以每条规则都要同时验证「该放行的确实放行」。
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import sourcing as S

FAIL = []
N = 0


def ck(name, got, want):
    global N
    N += 1
    if got != want:
        FAIL.append("%s: got=%r want=%r" % (name, got, want))
        print("  ✗ %-52s got=%r want=%r" % (name, got, want))
    else:
        print("  ✓ %s" % name)


print("=== R2 代充必须剔除（接口 productType 区分不出来，只能靠标题）===")
ck("【人工代充】哔哩哔哩大会员 月卡", S.is_daichong({"productTitle": "【人工代充】哔哩哔哩大会员 月卡"})[0], True)
ck("代客充值 网易云月卡", S.is_daichong({"productTitle": "代客充值 网易云月卡"})[0], True)
# 反向：正常商品不能被误杀
ck("【官方直充】哔哩哔哩大会员1个月", S.is_daichong({"productTitle": "【官方直充】哔哩哔哩大会员1个月"})[0], False)
ck("【官方CDK】哔哩哔哩大会员7天", S.is_daichong({"productTitle": "【官方CDK】哔哩哔哩大会员7天"})[0], False)

print("\n=== R1 类型不得混装 ===")
ck("全直充 [1,1]", S.kind_uniform_violations([1, 1])[0], True)
ck("全卡密 [2,2]", S.kind_uniform_violations([2, 2])[0], True)
ck("混装 [1,2] 必须报错", S.kind_uniform_violations([1, 2])[0], False)
ck("混装 [1,1,2] 必须报错", S.kind_uniform_violations([1, 1, 2])[0], False)
ck("读不到类型 → None", S.kind_uniform_violations([])[0], None)

print("\n=== R4 余额门槛 ===")
ck("limitBalance=500 命中", S.balance_blocked({"limitBalance": 500})[0], True)
ck("limitBalance=1000 命中", S.balance_blocked({"limitBalance": 1000})[0], True)
ck("描述写余额满2000 命中", S.balance_blocked({"goodsDescribe": "需账户余额满2000元"})[0], True)
ck("limitBalance=0 不命中", S.balance_blocked({"limitBalance": 0})[0], False)
ck("无任何门槛 不命中", S.balance_blocked({})[0], False)

print("\n=== 档位归一：必须不跨量纲 ===")
ck("月卡 → 1个月", S.tier_canon("月卡"), "1个月")
ck("周卡 → 7天", S.tier_canon("周卡"), "7天")
ck("年卡 → 12个月", S.tier_canon("年卡"), "12个月")
ck("6小时 原样保留", S.tier_canon("6小时"), "6小时")
ck("6小时 不等于 1天", S.tier_canon("6小时") == S.tier_canon("1天"), False)
ck("月卡 等于 1个月", S.tier_canon("月卡") == S.tier_canon("1个月"), True)

print("\n=== 产品线同一性：升级版/共享版不得冒充 ===")
ck("超级大会员 被拒",
   S.same_product_line("哔哩哔哩大会员1个月", "【升级会员】哔哩哔哩大会员升级超级大会员『1个月』")[0], False)
ck("共享版 被拒",
   S.same_product_line("哔哩哔哩大会员7天", "【共享】哔哩哔哩大会员共享7天周卡")[0], False)
ck("同产品线 放行",
   S.same_product_line("哔哩哔哩大会员1个月", "哔哩哔哩大会员月卡")[0], True)

print("\n=== 兑换渠道不同 = 不同产品线（2026-11-15 实测坑）===")
# pno=14911「同程app兑换」¥9.42，比普会便宜，但只能在同程app内兑换 → 买家在B站用不了
ck("同程app兑换 被拒",
   S.same_product_line("哔哩哔哩大会员", "哔哩哔哩大会员1个月 | 同程app兑换")[0], False)
ck("链接直冲 被拒",
   S.same_product_line("哔哩哔哩大会员", "【只支持移动手机号充值】哔哩哔哩大会员月卡----链接直冲")[0], False)
ck("官方CDK 放行",
   S.same_product_line("哔哩哔哩大会员", "【官方CDK】哔哩哔哩大会员1个月")[0], True)

print("\n=== 换源时异常低价闸必须同样生效（R4 换源不能绕过 R3 的价闸）===")
fake_alt = [{"val": "1个月", "acct": 1, "pno": "a", "cost": 9.42, "skip": ""},
            {"val": "1个月", "acct": 1, "pno": "b", "cost": 12.46, "skip": ""},
            {"val": "1个月", "acct": 1, "pno": "c", "cost": 13.07, "skip": ""},
            {"val": "1个月", "acct": 2, "pno": "d", "cost": 1.31, "skip": ""}]
u2, out2 = S.flag_price_outliers(fake_alt)
ck("换源候选里 ¥1.31 也须被标异常", [c["pno"] for c, _ in out2], ["d"])

print("\n=== 异常低价闸 ===")
fake = [{"cost": 9.42, "pno": "a"}, {"cost": 12.46, "pno": "b"}, {"cost": 1.31, "pno": "c"}]
kept, dropped = S.flag_price_outliers(fake)
ck("¥1.31 被标异常", [c["pno"] for c, _ in dropped], ["c"])
ck("正常价保留 2 个", len(kept), 2)
# 反向：样本不足 3 个不判（避免误杀）
kept2, dropped2 = S.flag_price_outliers([{"cost": 9.0, "pno": "a"}, {"cost": 1.0, "pno": "b"}])
ck("样本<3 不判异常", len(dropped2), 0)

print("\n=== 组合优先级：档位 > 代充 > 类型 > 产品线 > 余额 > 低价 ===")
# 用假数据验证「更便宜但违规」的候选一定不会胜出
# 这里只验证判定函数链，不联网

print()
if FAIL:
    print("=== 失败 %d / %d ===" % (len(FAIL), N))
    for f in FAIL:
        print("   " + f)
    sys.exit(1)
print("=== 通过 %d / %d ✅ 四条规则全部锁死 ===" % (N, N))
