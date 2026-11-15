# -*- coding: utf-8 -*-
"""选源引擎：四条硬规则的唯一实现（2026-11-15 用户定）。

用户原话：
  「直充必须和直充一起上，不能与卡密类的一起上，卡密类同理。永远不上代充。
    如果三个网站都有，需要比价，谁价格低，上谁的。有账户余额限制的也不上。」

🔴 为什么必须写成代码而不是只写进文档：
   这四条都是「错一个就发不出货 / 亏钱」的判据。靠 agent 每次读文档自行遵守，
   换机器、换 agent、上下文被压缩后就可能漏。写成函数就能被 deploy 和
   onepipe_guard 共同调用，且可被回归测试锁死。

四条规则的实现位置：
  R1 直充/卡密不得混装  → kind_uniform_violations() / verify_live()  ④+
  R2 永远不上代充        → is_daichong() / screen_products()
  R3 三家比价取最低      → compare_sources()
  R4 有余额门槛的不上    → balance_blocked()

⚠️ 已核实的接口事实（2026-11-15 实测）：
   「人工代充」与「官方直充」的 productType **完全相同**（都是 1），
   接口字段区分不出来，只能靠商品标题里的「代充」字样判定。
   所以 R2 是**标题关键词闸**，不是类型闸 —— 不能指望 productType。
"""

import re

import agiso_direct as A
import alds_dict as D

# ---------------------------------------------------------------- 常量

# R2：代充关键词。用户口径是「永远不上代充」，宁严勿宽。
# 「代充」单字就能覆盖「人工代充」「代客充值」「代充下单」等写法。
DAICHONG_WORDS = ("代充", "代下单", "代购", "人工充值", "代客充值")

# R4：货源要求「账户余额 ≥ 该值」时不上（沿用 2026-11-03 收紧后的 500）。
BALANCE_BLOCK = 500.0

# R3：默认比价的站点（阿奇索供货商账号 ID）。
# 志远 95425 / 商战 96810 / 思券 99569
DEFAULT_ACCTS = (95425, 96810, 99569)

ACCT_NAME = {95425: "志远", 96810: "商战", 99569: "思券",
             95105: "星芒", 95131: "省省", 95329: "追梦", 93310: "千城"}

# 类型枚举（与 onepipe_guard.preflight 同口径）
PT_RECHARGE = 1   # 官方直充
PT_KAOMI = 2      # 卡密


def acct_label(acct):
    return "%s(%s)" % (ACCT_NAME.get(int(acct), "?"), acct)


# ---------------------------------------------------------------- 档位归一

# 同一档位的别名 → 标准写法。**只做等价类映射，不做跨量纲换算**：
# 「月卡」≡「1个月」是同一档的两种说法；「6小时」与「1天」不是同一档，
# 绝不互换（2026-11-15 实测：6小时 ¥0.80 比 1个月 ¥12 便宜，若互换就是发错货）。
TIER_ALIAS = {
    "周卡": "7天", "周": "7天", "一周": "7天", "7日": "7天",
    "月卡": "1个月", "一个月": "1个月", "1月": "1个月", "30天": "1个月",
    "季卡": "3个月", "三个月": "3个月", "3月": "3个月", "90天": "3个月",
    "半年卡": "6个月", "六个月": "6个月",
    "年卡": "12个月", "一年": "12个月", "1年": "12个月", "365天": "12个月",
}


def tier_canon(val):
    """档位值归一：把「月卡/周卡/季卡/年卡」等统一成「N个月/N天」。

    抽不出标准值（如「6小时」「2月」）时原样返回，**不猜、不换算**。
    """
    s = str(val or "").strip()
    if not s:
        return s
    if s in TIER_ALIAS:
        return TIER_ALIAS[s]
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(小时|天|日|周|个月|月|年)$", s)
    if m:
        n, u = m.group(1), m.group(2)
        u = {"日": "天", "月": "个月"}.get(u, u)
        return n + u
    return s


# ---------------------------------------------------------------- 产品线同一性

# 产品线判定里**不能跨**的修饰词。命中即视为不同商品，即使档位值相同也不许互换。
# 🔴 2026-11-15 实测教训：搜「哔哩哔哩大会员 1个月」时思券 pno=937
#    「【升级会员】哔哩哔哩大会员升级超级大会员『1个月』」成本 ¥10.05，
#    比普会 ¥13.14 便宜 3 元。按纯比价会选中它 —— 但「超级大会员」是另一档
#    会员等级，普通用户买到超级大会员属于**货不对板**，比贵 3 元严重得多。
HARD_VARIANTS = (
    "超级", "升级", "白金", "钻石", "至尊", "高级", "豪华",
    "儿童", "学生", "长者", "青春",
    "共享", "合租", "拼车", "家庭", "企业",
    "体验", "试用", "首月", "新用户",
    # 🔴 兑换渠道 / 领取方式不同 = 不同产品线（2026-11-15 加）
    #    实测 pno=14911「哔哩哔哩大会员1个月 | 同程app兑换」成本 ¥9.42，
    #    比普会便宜，但它只能在「同程 app」内兑换 —— 买家在 B 站里用不了，
    #    属货不对板。换源时若放行会直接发错货。
    "同程", "携程", "美团", "京东", "淘宝", "支付宝", "云端", "端内", "指定app",
    "链接直冲", "链接充值", "只支持", "仅支持", "限定",
    "接码", "验证码", "需接码",
    "共享号", "体验号", "租用", "出租",
)


def variant_words(text):
    """抽出标题里的产品线修饰词（用于同一性比对）。"""
    t = str(text or "")
    return {w for w in HARD_VARIANTS if w in t}


def same_product_line(ref_title, title):
    """判断两个标题是否同一产品线。

    判据：档位值与数字以外的核心词一致，且**修饰词集合相同**。
    ref 没有的修饰词、cand 出现了 → 不同产品线（cand 是升级版/共享版等）。
    """
    ref_v, can_v = variant_words(ref_title), variant_words(title)
    if can_v - ref_v:
        return False, "多出修饰词：%s" % "、".join(sorted(can_v - ref_v))
    return True, ""


# ---------------------------------------------------------------- 价格合理性闸

# 同一档位内，某候选价比该档中位数低到这个比例以下 → 视为异常低价，不上。
# 🔴 2026-11-15 实测教训：搜卡密「哔哩哔哩大会员1个月」时 pno=8276
#    「只支持移动手机号充值----链接直冲」成本 ¥1.31，而同档其他货源 ¥9.42~12.46。
#    详情写「复制发货链接到浏览器打开，输入手机号领取会员」—— 是限时活动/试用
#    性质的链接，不是稳定月卡。若只看最低价就选它，会大量发货失败或成本倒挂。
#    正常的货源价差通常在 20% 内，低于中位数 60% 必有原因，必须人工确认。
PRICE_OUTLIER_RATIO = 0.40


def flag_price_outliers(usable, ratio=None):
    """在「同档可用候选」里标出异常低价。返回 (保留, 剔除明细)。

    样本少于 3 个时不判定（中位数不可靠），避免误杀。
    """
    rr = PRICE_OUTLIER_RATIO if ratio is None else float(ratio)
    vals = sorted(float(c["cost"]) for c in usable if c.get("cost") is not None)
    if len(vals) < 3:
        return usable, []
    mid = vals[len(vals) // 2]
    floor = mid * rr
    kept, dropped = [], []
    for c in usable:
        if c.get("cost") is not None and float(c["cost"]) < floor:
            dropped.append((c, "异常低价 %.2f < 中位数%.2f×%.0f%%=%.2f"
                            % (float(c["cost"]), mid, rr * 100, floor)))
        else:
            kept.append(c)
    return kept, dropped


# ---------------------------------------------------------------- R2 代充

def is_daichong(prod):
    """R2：是不是代充商品。返回 (bool, 命中词)。

    依据只有标题 —— productType 区分不出来（人工代充也是 1）。
    """
    title = str((prod or {}).get("productTitle") or (prod or {}).get("name") or "")
    for w in DAICHONG_WORDS:
        if w in title:
            return True, w
    return False, ""


def screen_products(prods, allow_daichong=False):
    """R2：批量剔除代充商品。返回 (保留, 剔除明细)。"""
    kept, dropped = [], []
    for p in prods or []:
        bad, word = is_daichong(p)
        if bad and not allow_daichong:
            dropped.append((p.get("productNo"), p.get("productTitle"), "含「%s」" % word))
        else:
            kept.append(p)
    return kept, dropped


# ---------------------------------------------------------------- R4 余额

def balance_blocked(detail, threshold=None):
    """R4：货源是否要求账户余额门槛。返回 (bool, 门槛值)。

    取 limitBalance 与描述文字中的较大值（与 deploy.limit_balance_of 同算法，
    这里独立实现是为了让本模块可单独被 onepipe_guard 调用而不引入循环依赖）。
    """
    th = BALANCE_BLOCK if threshold is None else float(threshold)
    lb = 0.0
    try:
        lb = float((detail or {}).get("limitBalance") or 0)
    except Exception:
        lb = 0.0
    txt = " ".join(str((detail or {}).get(k) or "")
                   for k in ("goodsDescribe", "notice", "info", "name"))
    for m in re.finditer(r"余额[^\d]{0,8}(\d+(?:\.\d+)?)", txt):
        try:
            lb = max(lb, float(m.group(1)))
        except Exception:
            pass
    return (lb >= th, lb)


# ---------------------------------------------------------------- R1 类型

def product_type_of(prod):
    """货源真实类型：1=官方直充 / 2=卡密 / None=读不到。"""
    v = (prod or {}).get("productType")
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def kind_uniform_violations(types):
    """R1：一组 SKU 的 productType 是否纯净（不得混装直充与卡密）。

    返回 (ok, 明细)。ok=False 表示同时出现 1 和 2 —— 用户明令禁止。
    """
    ts = {int(t) for t in (types or []) if t is not None}
    if not ts:
        return None, "读不到 productType"
    if len(ts) > 1:
        names = {1: "直充", 2: "卡密"}
        return False, "混装：同时出现 %s" % "、".join(
            sorted(names.get(t, str(t)) for t in ts))
    return True, "纯净：%s" % {1: "直充", 2: "卡密"}.get(list(ts)[0], str(list(ts)[0]))


# ---------------------------------------------------------------- R3 比价

def compare_sources(tiers, accts=None, allow_daichong=False, balance_threshold=None,
                    strict_tier=True, ref_title=""):
    """R3+R2+R4：多站点逐档比价，取最低价。

    tiers: [(档位值, 关键词)] 或 [(档位值, 关键词, 类型)]
           档位值经 tier_canon 归一后与货源 tier_val 比较
    accts: 要比价的站点，默认 DEFAULT_ACCTS
    strict_tier: True 时只接受档位匹配的商品（默认，防选错档）
    ref_title: 产品线参考标题（如「【官方直充】哔哩哔哩大会员1个月」）。
               给了就只接受同产品线的候选，**防止用「超级大会员」冒充「大会员」**。

    规则叠加顺序（重要，每一步都能独立否决更便宜的候选）：
      ① 档位不符 → 不计入（防错档：6小时不能当1个月）
      ② 代充 → 剔除（R2，即使更便宜也不用）
      ③ 类型不同装 → 剔除（R1，直充找直充、卡密找卡密）
      ④ 产品线不同 → 剔除（超级/升级/共享/儿童等修饰词不同）
      ⑤ 余额门槛 → 剔除（R4）
      ⑥ 剩下里取 cost 最低（R3）

    返回每档的 (档位, 选中记录 | None, 全部候选明细)
    """
    from alds_kit import supplier as _SP

    accts = list(accts or DEFAULT_ACCTS)
    out = []
    for t in tiers:
        val, kw = t[0], t[1]
        want_kind = t[2] if len(t) > 2 else None
        cands = []
        for acct in accts:
            try:
                prods = A.get_supplier_products(acct, kw) or []
            except Exception as e:
                cands.append({"val": val, "acct": acct, "pno": None,
                              "title": "", "cost": None,
                              "blocked": "目录读取失败:%s" % str(e)[:40]})
                continue
            for p in prods:
                pno = str(p.get("productNo"))
                title = str(p.get("productTitle") or "")

                # ① 档位匹配（防错档）
                tv = _SP.tier_val(title)
                if strict_tier and tier_canon(tv) != tier_canon(val):
                    continue

                # ② 代充（R2）
                bad, word = is_daichong(p)
                if bad and not allow_daichong:
                    cands.append({"val": val, "acct": acct, "pno": pno,
                                  "title": title, "cost": None,
                                  "blocked": "代充:含「%s」" % word})
                    continue

                # ③ 类型必须同装（R1）
                pt = product_type_of(p)
                if want_kind is not None and pt is not None and pt != want_kind:
                    continue

                # ④ 产品线同一性（防升级版/共享版冒充）
                if ref_title:
                    same, why = same_product_line(ref_title, title)
                    if not same:
                        cands.append({"val": val, "acct": acct, "pno": pno,
                                      "title": title, "cost": None,
                                      "blocked": "产品线不同:" + why})
                        continue

                try:
                    d = D.detail(pno, acct) or {}
                except Exception:
                    d = {}
                # ⑤ 余额门槛（R4）
                blk, lb = balance_blocked(d, balance_threshold)
                cost = None
                try:
                    cost = D.cost(pno, acct)
                except Exception:
                    cost = None
                cands.append({"val": val, "acct": acct, "pno": pno,
                              "title": title, "cost": cost,
                              "blocked": ("余额门槛≥%.0f" % lb) if blk else ""})
        usable = [c for c in cands if not c["blocked"] and c["cost"] is not None]
        # ⑥ 异常低价闸：偏离同档中位数过多的，先剔再比
        usable, outliers = flag_price_outliers(usable)
        for c, why in outliers:
            c["blocked"] = why
        best = min(usable, key=lambda c: float(c["cost"])) if usable else None
        out.append((val, best, cands))
    return out


def find_alternate_source(tier_val, kw, bad_acct, ref_title="", want_kind=None,
                          accts=None, cost_max=None, balance_threshold=None):
    """R4 换源：某货源有余额门槛时，去**其他站点**找同档同产品线的替代。

    2026-11-15 用户定：「货源网站有余额限制换货源，没有就不上的不上」
      → 命中余额门槛**不是直接剔除**，而是先换源；换不到才不上。

    返回 (best | None, 明细列表)。best = {val, acct, pno, title, cost}
    只换源、不改档位/产品线/类型 —— 那三条仍由各自的闸把关。
    """
    from alds_kit import supplier as _SP

    accts = [a for a in (accts or DEFAULT_ACCTS) if int(a) != int(bad_acct)]
    cands = []
    for acct in accts:
        try:
            prods = A.get_supplier_products(acct, kw) or []
        except Exception:
            continue
        for p in prods:
            pno = str(p.get("productNo"))
            title = str(p.get("productTitle") or "")
            # 档位必须完全一致（防错档）
            if tier_canon(_SP.tier_val(title)) != tier_canon(tier_val):
                continue
            # 代充不换（R2）
            if is_daichong(p)[0]:
                continue
            # 类型必须同装（R1）
            pt = product_type_of(p)
            if want_kind is not None and pt is not None and pt != want_kind:
                continue
            # 产品线必须同一（防升级版/共享版）
            if ref_title and not same_product_line(ref_title, title)[0]:
                continue
            try:
                d = D.detail(pno, acct) or {}
            except Exception:
                continue
            # 新货源自己也不能有余额门槛
            blk, lb = balance_blocked(d, balance_threshold)
            if blk:
                cands.append({"val": tier_val, "acct": acct, "pno": pno,
                              "title": title, "cost": None,
                              "skip": "该源也有门槛≥%.0f" % lb})
                continue
            try:
                cost = D.cost(pno, acct)
            except Exception:
                cost = None
            if cost is None:
                continue
            if cost_max is not None and float(cost) > float(cost_max):
                cands.append({"val": tier_val, "acct": acct, "pno": pno,
                              "title": title, "cost": cost,
                              "skip": "成本%.2f>%g" % (float(cost), float(cost_max))})
                continue
            cands.append({"val": tier_val, "acct": acct, "pno": pno,
                          "title": title, "cost": cost, "skip": ""})

    usable = [c for c in cands if not c["skip"]]
    # 🔴 异常低价闸必须在这里也过一次。
    #    2026-11-15 实测：漏掉这步时换源选中了 pno=8276（¥1.31 的「链接直冲」），
    #    正是 compare_sources 里被价格合理性闸拦掉的那个坑。
    #    换源和比价必须用同一套判据，否则换个入口就能绕过去。
    usable, outliers = flag_price_outliers(usable)
    for c, why in outliers:
        c["skip"] = why
    best = min(usable, key=lambda c: float(c["cost"])) if usable else None
    return best, cands


def format_compare(report):
    """把 compare_sources 的结果打成可读表格。"""
    lines = []
    for val, best, cands in report:
        lines.append("【%s】" % val)
        ok = [c for c in cands if not c["blocked"] and c["cost"] is not None]
        ok.sort(key=lambda c: float(c["cost"]))
        for c in ok:
            mark = "✅ 选中" if best and c is best else "   "
            lines.append("  %s %-10s pno=%-7s ¥%-8.2f %s"
                         % (mark, acct_label(c["acct"]), c["pno"], float(c["cost"]),
                            str(c["title"] or "")[:26]))
        for c in cands:
            if c["blocked"]:
                lines.append("  ❌ %-10s pno=%-7s %s  %s"
                             % (acct_label(c["acct"]), c["pno"] or "-",
                                c["blocked"], str(c["title"] or "")[:24]))
        if not best:
            lines.append("  ⚠️ 无可用货源（全部被代充/余额/缺价排除）")
    return "\n".join(lines)


# ---------------------------------------------------------------- 线上复核

def verify_live(gid, balance_threshold=None, allow_daichong=False):
    """对**已上架商品**复核四条规则。返回 (ok, rows)。

    与 deploy 无关，直接读线上 → 即使有人绕过 deploy 手工配置也能抓出来。
    这正是「规则写进代码」的价值：验收不依赖执行路径。
    """
    rows = []
    it = (A.get_item(gid) or {}).get("data", {}).get("data") or {}
    skus = it.get("itemSkuList") or []
    if not skus:
        return False, [("R1 类型纯净", None, "无 SKU")]

    types, cfgs = [], []
    for s in skus:
        try:
            c = (A.get_sku_alds(gid, s.get("skuId")) or {}).get("data", {}).get("data") or {}
        except Exception:
            c = {}
        cfgs.append((s, c))
        pno = c.get("supplierProductNo")
        ptype = c.get("productType")
        if ptype is None and pno:
            try:
                ptype = D.supplier_type(c.get("supplierAccountId"), pno)
            except Exception:
                ptype = None
        if ptype is not None:
            types.append(ptype)

        # R2 逐档：代充
        bad, word = (False, "")
        if pno:
            try:
                title = D.detail(pno, c.get("supplierAccountId") or D.DEFAULT_ACCT).get("name") or ""
            except Exception:
                title = ""
            bad, word = is_daichong({"productTitle": title})
        rows.append(("R2 非代充", not bad,
                     "sku=%s %s" % (s.get("skuId"), ("含「%s」" % word) if bad else "OK")))

        # R4 逐档：余额门槛
        blk, lb = balance_blocked({"limitBalance": c.get("limitBalance")}, balance_threshold)
        rows.append(("R4 无余额门槛", not blk,
                     "sku=%s 门槛=%s" % (s.get("skuId"), ("≥%.0f" % lb) if blk else "无")))

    ok1, detail1 = kind_uniform_violations(types)
    rows.insert(0, ("R1 类型纯净", ok1, detail1))

    ok = all(r[1] is not False for r in rows)
    return ok, rows


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    gid = sys.argv[1] if len(sys.argv) > 1 else ""
    if gid:
        ok, rows = verify_live(gid)
        print("=== 四条规则复核 %s ===" % gid)
        for name, st, det in rows:
            print("  %s %-14s %s" % ({True: "✅", False: "❌", None: "－"}.get(st, "?"), name, det))
        print("结论：", "全部通过 ✓" if ok else "有问题 ❌")
        sys.exit(0 if ok else 1)
    print("用法: python sourcing.py <gid>   # 复核已上架商品的四条规则")
