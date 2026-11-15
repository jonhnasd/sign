#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一条龙完整性守卫（2026-11-12 建立）

背景：11-12 连踩三类坑，且每次 `--go` 自检都报「真问题=[] ✅」——
因为旧自检只查配置内部自洽，不知道 spec 的 kind、不查文案、不查主图：
  ① productType 判反（直充货源被配成卡密）→ 下单拿不到充值账号，发不出货
  ⑪ phase_copy 静默跳过（上游详情空 + spec 未写 title/desc）→ 描述留 17 字平台默认句
  ⑬/主图 从不替换主图，且没提醒 → 主图一直是同步原图、图上只印单档

本模块提供三道闸：
  A 前置硬闸 preflight()：kind vs 货源 productType 不一致 / 文案缺失 → --go 直接中止
  B 后置完成清单 postcheck()：逐项打勾，缺一项就是「一条龙没做完」，不再假绿
  C 独立巡检 CLI：python onepipe_guard.py --inspect  （对出售中全量只读体检）

2026-11-14 补第四类坑（⑨b）：旧 ⑨ 只判断 imgUrls[0] 是不是 -0-xy_item 同步原图，
只要换成任意自制 CDN 图就打绿 —— 于是「通用会员卡片 + 模型画文字」的纯文生图、
或手工随手传的图也能过。1425（1097971051544）15 项全绿而主图最不合规就是这么来的。
现改为读 `_main_image_manifest.json`（由 replica_main_image.py 写入）验收：
必须 mode=replica + 有参考图 pno/URL + 线上主图 URL 与记录一致 + 白名单已逐字核验。

判定口径（已用志远/思券样本交叉标定，见 agiso_direct.py 注释）：
  productType 1 = 官方直充 / 2 = 卡密（思券 goods_type 同义）

用法：
  python onepipe_guard.py --inspect                # 全店出售中只读巡检
  python onepipe_guard.py --inspect --gid <ID>    # 单个商品
  python onepipe_guard.py --self-test             # 不打网络，自检清单定义
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULT_SENTENCES = ("感兴趣的话点", "和我私聊吧")
BANNED_COPY = ("秒到账", "极速到账", "24小时自动发货", "自动发货", "快速到账", "立即到账")
SUPPLIER_LABEL_RE = re.compile(
    r"[（(\[【]?\s*(?:货源|供应商|上游)\s*(?:商品)?\s*(?:编号|ID|商品号)\s*[:：#]?\s*[A-Za-z0-9_-]+\s*[）)\]】]?",
    re.I,
)
URL_OR_DOMAIN_RE = re.compile(
    r"https?://\S+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}\S*|"
    r"\b[A-Za-z0-9.-]+\.(?:cn|com|net|top|cc|io)\b",
    re.I,
)
SUPPLIER_NAMES = ("志远", "商战", "思券", "星芒", "省省", "追梦", "千城",
                  "qqkami", "zy.kkam", "sqqy88", "xmang")


def buyer_copy_leaks(text):
    """Return matched internal-source markers in buyer-visible text only."""
    s = str(text or "")
    hits = []
    if SUPPLIER_LABEL_RE.search(s):
        hits.append("货源编号")
    if URL_OR_DOMAIN_RE.search(s):
        hits.append("网址/域名")
    for vendor in SUPPLIER_NAMES:
        if re.search(r"(?:货源|供应商|上游|网站|渠道)(?:名称)?\s*[:：是为来自于-]*\s*" +
                     re.escape(vendor) + r"|" + re.escape(vendor) +
                     r"\s*(?:货源|供应商|网站|渠道)", s, re.I):
            hits.append("供应商名称:%s" % vendor)
    return hits


def _A():
    import agiso_direct
    return agiso_direct


def item_of(gid, A=None):
    A = A or _A()
    r = A.get_item(str(gid))
    d = (r or {}).get("data") or {}
    return d.get("data") or d


def deep_cfg(r):
    """从多层返回里挖出含 supplierParamJson 的配置体。"""
    if not isinstance(r, dict):
        return {}
    for k in ("supplierParamJson", "itemSkuList", "sendTypeOption"):
        if k in r:
            return r
    for k in ("data", "result", "body"):
        if isinstance(r.get(k), dict):
            g = deep_cfg(r[k])
            if g:
                return g
    return {}


_supplier_cache = {}


def supplier_type(acct, pno):
    """按 pno 单点查货源真实 productType；查不到返回 None（调用方按『无法核实』处理）。"""
    key = (str(acct), str(pno))
    if key in _supplier_cache:
        return _supplier_cache[key]
    try:
        rows = _A().get_supplier_products(int(acct), str(pno)) or []
        hit = next((x for x in rows if str(x.get("productNo")) == str(pno)), None)
        val = hit.get("productType") if hit else None
    except Exception:
        val = None
    _supplier_cache[key] = val
    return val


def spec_pnos(spec):
    """兼容三类 spec：多档 skus[] / 单品 pno / 双维度 skus[]。"""
    out = []
    for s in (spec.get("skus") or []):
        p = s.get("pno")
        if p and str(p) not in out:
            out.append(str(p))
    if spec.get("pno") and str(spec["pno"]) not in out:
        out.append(str(spec["pno"]))
    return out[:6]


def is_raw_main_image(url):
    """闲鱼同步原图（未经快跑重制）——以 -0-xy_item 为判据。"""
    u = str(url or "")
    return bool(u) and ("-0-xy_item" in u or (u and "fleamarket" not in u and "-2-" not in u
                                              and "alicdn" in u))


def _R():
    """惰性 import 复刻式模块（读生成记录用），失败不致命。"""
    try:
        import replica_main_image as R
        return R
    except Exception:
        return None


def _buyer_field_mismatch(gid, spec, R):
    """图上印的填写项 vs 货源要求：只有「都是具体标识且互不包含」才判红。

    2026-11-14 加。旧 ⑨b 只验「留证齐全 + 无四类禁词」，但禁词表查的是「违不违规」，
    查不出「对不对」—— 图上写「填写手机号」而货源要「华为账号」，一个禁词都不命中，
    照样判绿。ID 链路（按阿奇索 ID 上 SKU）主图是自备的，更容易错，这条让它必红。
    """
    try:
        rec = R.read_manifest(gid) or {}
    except Exception:
        return ""
    have = str(rec.get("account_label") or "").strip()
    want = str((spec or {}).get("buyer_field") or "").strip()
    if not want and spec and spec.get("pno"):
        try:
            from alds_kit.supplier import buyer_field_of
            want = str(buyer_field_of(spec["pno"], spec.get("acct") or 0).get("field") or "").strip()
        except Exception:
            want = ""
    if have and not want and spec is not None:
        return "图上印了「%s」，但货源原文解析不出该填写项（疑似自拟，需核对或改图）" % have
    if have and want and have not in want and want not in have:
        return ("图上填写项与货源要求不一致：图=「%s」/ 应=「%s」"
                "（改 spec.buyer_field，或 main_image=replica 重做）" % (have, want))
    return ""


def main_image_plan(gid, main_url, spec=None):
    """⑨b：主图是否走过复刻式且已逐字核验。返回 (ok, note)，ok 可为 None（历史豁免）。"""
    R = _R()
    if R is None:
        return False, "读不到 replica_main_image 模块，无法校验主图方案"
    ok, note = R.main_image_problem(gid, main_url)
    if ok is None:
        if str(gid) in MAIN_IMAGE_LEGACY:
            return None, "历史商品，无复刻记录（待补证，不计缺）"
        return False, "无主图生成记录，无法证明走过复刻式（疑似通用模板/手工上传）"
    if ok:
        bad = _buyer_field_mismatch(gid, spec, R)
        if bad:
            return False, bad
    return ok, note



def desc_price_mismatches(desc, skus):
    """档位对照里的价格必须与线上 SKU 价逐档一致。

    2026-11-12 实坑：deploy --go 的 ⑫ 自动改价会把现价调成目标价，
    而 spec 手写的「档位对照」仍是改价前的数字 → 图文价格不符、旧自检照样报绿。
    返回 (mismatches, applicable)：描述里没有「档位 —— N 元」行时 applicable=False（不判定）。
    """
    live = {}
    for s in skus:
        vals = [str(p.get("valueText") or "") for p in (s.get("propertyList") or [])]
        key = "|".join(v for v in vals if v)
        if not key:
            continue
        try:
            live[key] = float(s.get("price") or 0)
        except (TypeError, ValueError):
            pass
        for v in vals:
            if v:
                live.setdefault(v, live.get(key, 0))
    pat = re.compile(r"^\s*(.+?)\s*[—–－-]{1,2}\s*([0-9]+(?:\.[0-9]+)?)\s*元\s*$", re.M)
    rows = pat.findall(desc or "")
    if not rows:
        return [], False
    bad, hit = [], 0
    for name, price in rows:
        name = name.strip()
        if name not in live:
            continue
        hit += 1
        try:
            p = float(price)
        except ValueError:
            continue
        if abs(p - live[name]) > 0.011:
            bad.append((name, p, live[name]))
    return bad, hit > 0


# ---------------------------------------------------------------- A 前置硬闸
def preflight(spec, item, acct, kind, mode="--dry"):
    """返回 (fatal, warn)。fatal 非空时 --go 必须中止。

    只依赖 spec + 已读到的 item，不改动任何数据。
    """
    fatal, warn = [], []
    go = (mode == "--go")

    # ① 类型闸：kind 必须与货源真实 productType 一致（唯一可信来源是接口，不是标题/口述）
    want = {"recharge": 1, "kaomi": 2}.get(kind)
    if want is not None:
        checked = 0
        for pno in spec_pnos(spec):
            pt = supplier_type(acct, pno)
            if pt is None:
                continue
            checked += 1
            if int(pt) != want:
                fatal.append(
                    "类型错配：spec kind=%s 要求 productType=%s，但货源 acct=%s pno=%s 实际 productType=%s"
                    "（1=官方直充 / 2=卡密）。按此配置下单会发不出货。" % (kind, want, acct, pno, pt))
                break
        if checked == 0:
            warn.append("类型闸：未能从货源接口核实 productType（网络或目录问题），本次跳过交叉校验，请人工确认 kind")

    # ①b 永远不上代充（2026-11-15 用户定）—— 接口 productType 区分不出来，只能靠标题。
    #     代充也是 productType=1，若只看类型闸会放行；必须在写入前独立拦一道。
    #     🔴 这里用「显式重试 + 失败即 fatal」，不用 try/except 静默跳过：
    #        2026-11-15 首版写成 except → warn，而 warn 在 --go 下不打印，
    #        结果代充 pno=15301 漏过闸且毫无提示。安全闸绝不允许静默失效。
    try:
        import sourcing as _SRC
    except Exception as _e:
        _SRC = None
        fatal.append("代充闸不可用（无法导入 sourcing：%s）—— 安全闸失效时禁止上架，请修好再跑。" % str(_e)[:80])
    if _SRC is not None:
        _dc = []
        for pno in spec_pnos(spec):
            a = acct
            for _s in (spec.get("skus") or []):
                if str(_s.get("pno")) == str(pno) and _s.get("acct"):
                    a = _s.get("acct")
            _t = ""
            try:
                import alds_dict as _D
                _t = (_D.detail(pno, a) or {}).get("name") or ""
            except Exception:
                _t = ""
            bad, word = _SRC.is_daichong({"productTitle": _t})
            if bad:
                _dc.append("pno=%s「%s」含「%s」" % (pno, str(_t)[:28], word))
            elif not _t:
                # 拿不到标题就无法证明不是代充 → 不放行（安全闸默认拒绝）
                fatal.append("代充闸：pno=%s（acct=%s）取不到货源标题，无法证明非代充 → 拒绝上架。"
                             "请检查货源目录后重跑。" % (pno, a))
        if _dc:
            fatal.append("代充货源禁止上架（2026-11-15 用户定「永远不上代充」）："
                         + "；".join(_dc) + "。请换官方直充或卡密货源。")

    # ①c 直充/卡密不得混装（2026-11-15 用户定）
    try:
        import sourcing as _SRC2
        _pts = []
        for pno in spec_pnos(spec):
            pt = supplier_type(acct, pno)
            if pt is not None:
                _pts.append(int(pt))
        _ok, _why = _SRC2.kind_uniform_violations(_pts)
        if _ok is False:
            fatal.append("类型混装禁止（2026-11-15 用户定「直充必须和直充一起上，"
                         "不能与卡密类的一起上」）：%s。请把 SKU 拆成纯直充或纯卡密两件商品。" % _why)
    except Exception as _e:
        fatal.append("混装闸不可用（%s）—— 安全闸失效时禁止上架。" % str(_e)[:80])

    # ② 文案闸：spec 没给 title/desc 且线上描述是默认句/过短 → ⑪ 会静默跳过
    desc = str(item.get("desc") or item.get("description") or "")
    has_spec_copy = bool(spec.get("title") or spec.get("desc"))
    bad_desc = (not desc) or any(x in desc for x in DEFAULT_SENTENCES) or len(desc) < 60
    if bad_desc and not has_spec_copy and spec.get("detail_text") is not False:
        fatal.append(
            "文案缺失：线上描述仅 %d 字%s，且 spec 未写 title/desc —— ⑪ phase_copy 会静默跳过，"
            "跑完仍是平台默认句。请先用模板补齐 title/desc（文案缺失不要求用户提供）。"
            % (len(desc), "（平台默认句）" if any(x in desc for x in DEFAULT_SENTENCES) else ""))

    title = str(item.get("title") or "")
    for w in BANNED_COPY:
        if w in title:
            warn.append("标题含到账时效词「%s」，可能触发闲鱼风控" % w)

    # ③ 主图闸：同步原图不中止（主图是独立链路、需先确认文案再生图），但必须显式提醒
    imgs = item.get("imgUrls") or []
    if imgs and is_raw_main_image(imgs[0]):
        warn.append(
            "主图仍是闲鱼同步原图（未重制），图上通常只印上游单档、与自身多档 SKU 不符。"
            "重制走复刻式：python replica_main_image.py --self-test --pno <pno> "
            "→ 或直接 python create_from_pno.py ... --go（内嵌复刻式生图 + 生成记录）")

    if go and fatal:
        for f in fatal:
            print("  ❌ [前置硬闸] " + f)
        print("  ❌ --go 已中止，未做任何改动。修正 spec 后重跑；确需豁免可加 spec.allow_guard_bypass=true")
    else:
        for f in fatal:
            print("  ⚠️ [前置硬闸][dry 预演] " + f)
    for w in warn:
        print("  ⚠️ [前置提醒] " + w)
    if not fatal and not warn:
        print("  ✅ [前置硬闸] 类型/文案/主图 三项均通过")
    return fatal, warn


# ---------------------------------------------------------------- B 后置完成清单
CHECKS = [
    "① 商品在线", "② SKU 已建", "③ 每档绑货源", "④ 类型与货源一致",
    "⑤ 直充参数齐全", "⑥ 卡密参数为空", "⑦ 描述完善", "⑧ 标题合规",
    "⑨ 主图已重制", "⑨b 主图方案合规", "⑩ 价格库存正常", "⑪ 发货/改价配置",
    "⑫ 货源可售", "⑬ 无模板残留", "⑭ 限价不泄漏", "⑮ 买家文案无内部信息",
    "⑯ 无代充货源", "⑰ 类型不混装", "⑱ 无余额门槛",
]

# ⑨b 历史豁免（2026-11-14 建）：这些商品在「复刻式 + 生成记录」机制之前上架，
# 主图是当时手工分层合成/复刻做的，没有 manifest。判 None（－，不算缺），
# 但巡检会明确标注「待补记录」。新商品不要往这里加 ——
# 新增商品无记录必须红，这是本闸存在的意义。
MAIN_IMAGE_LEGACY = {
    "1100446952795", "1097000155425", "1100124692806", "1096735887393",
    "1096737823598", "1097674798748", "1099659265490", "1100813876979",
    "1100879952009", "1098716682922", "1100910304959",
}

# ⑬ 模板残留判定素材（2026-11-13 加）：additional 异商品词 + 已知模板图 URL 片段。
# 词只在「出现于 additional 且不出现在标题/描述」时报红 → 本身就是该品牌的商品不误报。
FOREIGN_HINTS = ("美团外卖", "知乎盐选", "剪映", "哈啰", "喜马拉雅", "爱奇艺",
                 "夸克", "UC网盘", "饿了么", "瑞幸", "古茗", "海底捞")
RESIDUE_IMG_HINTS = ("O1CN01qp2bsQuflMG",)   # 已知模板残留图（知乎盐选模板 1100813876979）


def postcheck(gid, spec=None, kind=None, verbose=True):
    """回读线上逐项打勾。返回 (rows, missing)。不写任何数据。"""
    A = _A()
    it = item_of(gid, A)
    skus = it.get("itemSkuList") or []
    desc = str(it.get("desc") or "")
    title = str(it.get("title") or "")
    imgs = it.get("imgUrls") or []
    rows = []

    # ① 在线：页面「出售中」tab 实测 status=0（存量）与 99（当天新上架）都算在线
    sr = []
    try:
        sr = (((A.search_goods(str(gid), 1, 5) or {}).get("data") or {}).get("data") or {}).get("items") or []
        online = bool(sr) and str(sr[0].get("status")) in ("0", "1", "99")
        recharge_flag = bool((sr[0] if sr else {}).get("apiRechargeOnOff"))
    except Exception:
        online, recharge_flag = None, None
    rows.append(("① 商品在线", True if online else (None if online is None else False),
                 "status=%s" % (sr[0].get("status") if sr else "?")))

    # ② SKU
    rows.append(("② SKU 已建", len(skus) > 0, "%d 档" % len(skus)))

    # ③⑤⑥ 逐档配置（最多查 8 档，避免 14 档商品过慢）
    cfgs = []
    for s in skus[:8]:
        c = deep_cfg(A.get_sku_alds(str(gid), str(s.get("skuId")))) or {}
        cfgs.append(c)
    bound = [c for c in cfgs if c.get("supplierProductNo")]
    rows.append(("③ 每档绑货源", len(bound) == len(cfgs) and bool(cfgs),
                 "%d/%d 档有 pno" % (len(bound), len(cfgs))))

    # ④ 类型一致（与 spec.kind 比对，这是旧自检缺失的一环）
    # 独立巡检没传 kind 时，按线上 productType 反推，保证 ⑤⑥ 也能判
    pts = {int(c.get("productType")) for c in cfgs if c.get("productType") is not None}
    kind_src = "spec"
    if kind is None and pts:
        kind = "recharge" if pts == {1} else ("kaomi" if pts == {2} else None)
        kind_src = "按线上推断"
    want = {"recharge": 1, "kaomi": 2}.get(kind)
    if want is None:
        rows.append(("④ 类型与货源一致", None, "kind 无法确定，跳过"))
    elif not pts:
        rows.append(("④ 类型与货源一致", None, "读不到 productType"))
    else:
        rows.append(("④ 类型与货源一致", pts == {want},
                     "线上=%s / kind=%s(%s) 期望=%s" % (sorted(pts), kind, kind_src, want)))

    # ⑤ 直充参数 / ⑥ 卡密参数（按 kind 只判相关那条，另一条标 N/A）
    if kind == "recharge":
        good = all("{$充值账号}" in str(c.get("supplierParamJson") or "") and
                   any(str(a.get("value") or "") for a in (c.get("attach") or []))
                   for c in cfgs)
        rows.append(("⑤ 直充参数齐全", bool(good and recharge_flag),
                     "参数/占位符%s，apiRechargeOnOff=%s" % ("OK" if good else "缺失", recharge_flag)))
        rows.append(("⑥ 卡密参数为空", None, "N/A（直充商品）"))
    elif kind == "kaomi":
        good = all(not c.get("supplierParamJson") and not (c.get("attach") or []) for c in cfgs)
        rows.append(("⑤ 直充参数齐全", None, "N/A（卡密商品）"))
        rows.append(("⑥ 卡密参数为空", bool(good and not recharge_flag),
                     "参数为空=%s，apiRechargeOnOff=%s" % (good, recharge_flag)))
    else:
        rows.append(("⑤ 直充参数齐全", None, "未提供 kind"))
        rows.append(("⑥ 卡密参数为空", None, "未提供 kind"))

    # ⑦ 描述：档位段落允许带后缀（老商品写「【档位对照 · 先选会员再选时长】」），
    # 也接受把档位写在正文里的写法（剪映「支持5天、7天…五档时长」）。
    tier_vals = set()
    for s in skus:
        for p in (s.get("propertyList") or []):
            v = str(p.get("valueText") or "")
            if v:
                tier_vals.add(v)
    has_tier_block = any(m in desc for m in ("【档位对照", "【档位说明", "【规格", "【可选档位"))
    tier_hits = sum(1 for v in tier_vals if v in desc)
    tier_ok = has_tier_block or tier_hits >= 2
    mism, applicable = desc_price_mismatches(desc, skus)
    price_ok = not (applicable and mism)
    d_ok = (len(desc) >= 100 and not any(x in desc for x in DEFAULT_SENTENCES)
            and tier_ok and price_ok)
    rows.append(("⑦ 描述完善", d_ok, "%d 字 / 档位信息=%s(段落=%s,正文命中%d档) / 默认句=%s / 对照价=%s"
                 % (len(desc), tier_ok, has_tier_block, tier_hits,
                    any(x in desc for x in DEFAULT_SENTENCES),
                    "一致" if applicable and not mism else
                    ("不符%s" % mism[:3] if mism else "无价格行(不判定)"))))

    # ⑧ 标题 + 买家可见文案内部信息
    t_bad = [w for w in BANNED_COPY if w in title]
    t_bytes = sum(3.0 if ord(ch) > 127 else 1.5 for ch in title)
    title_leaks = buyer_copy_leaks(title)
    desc_leaks = buyer_copy_leaks(desc)
    sku_copy_leaks = []
    for c in cfgs:
        for field in ("additional",):
            leaks = buyer_copy_leaks(c.get(field))
            if leaks:
                sku_copy_leaks.append("%s(sku%s):%s" % (field, c.get("skuId"), "/".join(leaks)))
    copy_leaks = title_leaks + desc_leaks + sku_copy_leaks
    rows.append(("⑧ 标题合规", bool(title) and not t_bad and t_bytes <= 90 and not title_leaks,
                 "%.1f/90 字节 / 违规词=%s / 内部信息=%s" %
                 (t_bytes, t_bad or "无", title_leaks or "无")))
    rows.append(("⑮ 买家文案无内部信息", not copy_leaks,
                 "泄漏=" + "、".join(copy_leaks[:8]) if copy_leaks else "干净"))

    # ⑨ 主图（本轮新增的关键项）
    raw = bool(imgs) and is_raw_main_image(imgs[0])
    rows.append(("⑨ 主图已重制", bool(imgs) and not raw,
                 "%s" % ("同步原图（未重制）" if raw else
                         ("自制CDN图" if imgs else "无主图"))))

    # ⑨b 主图方案合规（2026-11-14 加）：有张自制图不算过，必须可追溯到复刻式 + 参考图 + 逐字核验
    #    + 图上填写项与货源要求一致（spec 传入，ID 链路自备主图也受这条约束）
    plan_ok, plan_note = main_image_plan(gid, imgs[0] if imgs else "", spec)
    rows.append(("⑨b 主图方案合规", plan_ok, plan_note))


    # ⑩ 价格库存
    p_ok = all(float(s.get("price") or 0) > 0 for s in skus) and bool(skus)
    rows.append(("⑩ 价格库存正常", p_ok,
                 "%d 档，最低 ¥%s" % (len(skus), min([float(s.get("price") or 0) for s in skus] or [0]))))

    # ⑪ 发货/改价
    try:
        g = deep_cfg(A.get_goods_alds(str(gid))) or {}
        ship = bool(g.get("autoSend"))
        rows.append(("⑪ 发货/改价配置", ship, "autoSend=%s spType=%s" % (ship, g.get("spType"))))
    except Exception as e:
        rows.append(("⑪ 发货/改价配置", None, "读取失败 %s" % str(e)[:40]))

    # ⑫ 货源可售（2026-11-13 加）：每档 isAllowPurchase；停售=红（对应库存须置 0）。
    #    取不到状态=未知 → ⚠️ 不判红（保守不阻断，与 supplier_allowed 口径一致）。
    flags = []
    for c in cfgs:
        pno = c.get("supplierProductNo")
        if not pno:
            continue
        try:
            flags.append((pno, A.supplier_allowed(int(c.get("supplierAccountId") or 0), pno)))
        except Exception:
            flags.append((pno, None))
    bad = [p for p, v in flags if v is False]
    unknown = [p for p, v in flags if v is None]
    rows.append(("⑫ 货源可售",
                 False if bad else (None if (unknown or not flags) else True),
                 "停售=%s 未知=%s" % (bad or "无", unknown or "无")))

    # ⑬ 无模板残留（2026-11-13 加）：additional 异商品词 + 已知模板残留图。
    residue = []
    for c in cfgs:
        addl = str(c.get("additional") or "")
        for w in FOREIGN_HINTS:
            if w in addl and w not in title and w not in desc:
                residue.append("additional←%s(sku%s)" % (w, c.get("skuId")))
    for u in imgs:
        for h in RESIDUE_IMG_HINTS:
            if h in str(u):
                residue.append("图片←模板残留(%s…)" % h[:14])
    rows.append(("⑬ 无模板残留", not residue, "；".join(residue[:4]) or "干净"))

    # ⑭ 限价不泄漏（2026-11-13 用户定：SKU 名/描述/发货说明三不写）。
    leak = []
    if "限价" in title:
        leak.append("标题")
    if "限价" in desc:
        leak.append("描述")
    for c in cfgs:
        for field in ("additional", "specName"):
            if "限价" in str(c.get(field) or ""):
                leak.append("%s(sku%s)" % (field, c.get("skuId")))
        for a_ in (c.get("attach") or []):
            if "限价" in str(a_.get("desc") or "") + str(a_.get("title") or ""):
                leak.append("attach(sku%s)" % c.get("skuId"))
    rows.append(("⑭ 限价不泄漏", not leak, "泄漏=" + "、".join(leak) if leak else "干净"))

    # ⑯/⑰/⑱ 选源四条规则复核（2026-11-15 用户定）
    # 这三项独立于执行路径：即使有人手工在网页上配了违规货源，巡检也能抓出来。
    try:
        import sourcing as _SR
        # ⑯ 代充（永远不上）
        _dcs = []
        for c in cfgs:
            _pno = c.get("supplierProductNo")
            if not _pno:
                continue
            _nm = ""
            try:
                _nm = (D.detail(_pno, c.get("supplierAccountId") or acct) or {}).get("name") or ""
            except Exception:
                _nm = ""
            bad, word = _SR.is_daichong({"productTitle": _nm})
            if bad:
                _dcs.append("sku%s←pno=%s 含「%s」" % (c.get("skuId"), _pno, word))
        rows.append(("⑯ 无代充货源", not _dcs,
                     "；".join(_dcs[:3]) if _dcs else "干净（2026-11-15 铁律：永远不上代充）"))

        # ⑰ 类型不混装
        _tps = []
        for c in cfgs:
            _p = c.get("supplierProductNo")
            if not _p:
                continue
            _t = c.get("productType")
            if _t is None:
                try:
                    _t = D.supplier_type(c.get("supplierAccountId") or acct, _p)
                except Exception:
                    _t = None
            if _t is not None:
                _tps.append(int(_t))
        _uok, _uwhy = _SR.kind_uniform_violations(_tps)
        rows.append(("⑰ 类型不混装", _uok, _uwhy))

        # ⑱ 无余额门槛
        _lbs = []
        for c in cfgs:
            _p = c.get("supplierProductNo")
            if not _p:
                continue
            _d = {}
            try:
                _d = D.detail(_p, c.get("supplierAccountId") or acct) or {}
            except Exception:
                _d = {}
            blk, lb = _SR.balance_blocked(_d)
            if blk:
                _lbs.append("sku%s←pno=%s 门槛≥%.0f" % (c.get("skuId"), _p, lb))
        rows.append(("⑱ 无余额门槛", not _lbs,
                     "；".join(_lbs[:3]) if _lbs else "干净"))
    except Exception as _e:
        for _n in ("⑯ 无代充货源", "⑰ 类型不混装", "⑱ 无余额门槛"):
            rows.append((_n, None, "判定不可用：%s" % str(_e)[:60]))


    missing = [n for n, ok_, _ in rows if ok_ is False]
    if verbose:
        print("\n  ── 一条龙完成清单（%s）──" % gid)
        for n, ok_, note in rows:
            mark = "✅" if ok_ is True else ("⚠️" if ok_ is False else "－")
            print("   %s %-18s %s" % (mark, n, note))
        if missing:
            print("   ❌ 未完成 %d 项：%s —— 一条龙没做完，不能报绿" % (len(missing), "、".join(missing)))
        else:
            print("   ✅ %d 项全部完成" % len(CHECKS))
    return rows, missing


def _looks_like_gid(s):
    return bool(re.fullmatch(r"\d{8,20}", str(s or "").strip()))


def parse_targets(args):
    """从命令行解析目标 gid 列表。返回 (gids, problems)。

    支持三种等价写法：
      --inspect <gid>                     位置参数
      --inspect --gid <gid>               显式开关
      --inspect --gid <a> --gid <b>       多个
      也接受 bare `python onepipe_guard.py <gid>`

    🔴 2026-11-15 修：此前 `--inspect <gid>` 的位置参数被**静默丢弃** ——
       只要 args 里没有 `--gid` 就一直走 inspect_all()，去读
       _live_gids_fresh.json 里硬编码的旧 9 个商品。结果查 A 商品拿到 B 商品
       的报告，而且没有任何提示。巡检工具谎报比没有工具更危险，故显式解析、
       非法参数一律报错而不是忽略。
    """
    gids, problems = [], []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--gid":
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                problems.append("--gid 后面缺少商品 ID")
                i += 1
            else:
                gids.append(args[i + 1])
                i += 2
            continue
        if a.startswith("--gid="):
            gids.append(a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("-"):
            i += 1          # 其他开关（--inspect / --self-test …）不参与
            continue
        if _looks_like_gid(a):
            gids.append(a)
        else:
            problems.append("无法识别的参数 %r（商品 ID 应为 8~20 位数字）" % a)
        i += 1

    seen, out = set(), []
    for g in gids:
        g = str(g).strip()
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out, problems


def inspect_all(gid=None):
    """只读巡检。gid 可为 str / list / None(None=读全量清单)。

    返回进程退出码：0=全通过，1=有缺项或商品取不到，2=环境/清单问题。
    """
    A = _A()
    A.TOKEN = A.token_from_browser(open_if_missing=False)
    if isinstance(gid, (list, tuple)):
        ids = [str(x) for x in gid]
    elif gid:
        ids = [str(gid)]
    else:
        p = os.path.join(HERE, "_live_gids_fresh.json")
        if not os.path.exists(p):
            print("缺 _live_gids_fresh.json，请先跑 grab_live_gids.py；"
                  "或直接指定商品：python onepipe_guard.py --inspect <gid>")
            return 2
        ids = json.load(open(p, encoding="utf-8"))
        print("（未指定商品 → 读 _live_gids_fresh.json 的 %d 个在售商品）" % len(ids))

    print("只读巡检 %d 个商品（不修改任何线上数据）\n" % len(ids))
    total, bad_ids = {}, []
    for g in ids:
        # 🔴 先验 ID 真实存在：item_of 取不到会静默返回 {}，不校验就会
        #    跑出一堆红项却分不清是商品有问题还是 ID 写错了。
        it = {}
        try:
            it = item_of(g, A)
        except Exception as e:
            print("❌ 商品 %s 取不到：%s" % (g, str(e)[:80]))
            bad_ids.append(g)
            continue
        if not it or (not it.get("title") and not it.get("itemSkuList")):
            print("❌ 商品 %s 不存在或无权限（检查 ID 是否写错）" % g)
            bad_ids.append(g)
            continue
        rows, missing = postcheck(g, verbose=True)
        total[g] = missing

    print("\n=== 汇总 ===")
    for g, m in total.items():
        print("  %s  %s" % (g, "✅ 全通过" if not m else "❌ 缺 %d 项：%s" % (len(m), "、".join(m))))
    for g in bad_ids:
        print("  %s  ❌ 商品取不到（ID 错误或无权限）" % g)
    if len(total) + len(bad_ids) > 1:
        clean = sum(1 for m in total.values() if not m)
        print("\n  %d/%d 全通过%s"
              % (clean, len(total) + len(bad_ids),
                 "" if not bad_ids else "，%d 个 ID 无效" % len(bad_ids)))
    return 0 if (not bad_ids and all(not m for m in total.values())) else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--self-test" in args:
        print("清单一共 %d 项：" % len(CHECKS))
        for c in CHECKS:
            print("  -", c)
        print("\n示例：python onepipe_guard.py --inspect 1099583129794")
        print("      python onepipe_guard.py --inspect --gid <gid>")
        print("      python onepipe_guard.py --inspect            # 全店在售")
    else:
        gids, problems = parse_targets(args)
        for p in problems:
            print("⚠️ " + p)
        if problems and not gids:
            print("\n用法：python onepipe_guard.py --inspect [<gid> ...] [--gid <gid> ...]")
            sys.exit(2)
        if gids or "--inspect" in args:
            sys.exit(inspect_all(gids or None))
        print(__doc__)
