# -*- coding: utf-8 -*-
"""SKU 规格名「类型前缀」判定与生成（2026-11-15 用户定）。

用户原话：
  「sku要写清楚是什么类型，除了时长，会员类型货币类型等sku都要带上，让顾客一目了然」

背景（实测，2026-11-15）：
  全店 17 件商品是「单维 + 纯档位」命名，SKU 名只有 `7天` / `1个月` / `500积分`，
  买家只能看到时长或面额，**看不出是哪种会员、哪种货币**。
  同一店里还有两种形态：
    多维（如 UC网盘）：会员:超级 / 时长:1天   → 已写清，无需加前缀
    单维（如 b站大会员）：使用周期:7天          → 缺类型，需补前缀

核心判据（避免误伤多维商品，这是本模块最容易做错的地方）：
  · 多维（propertyList 长度 ≥ 2）：每个维度各自有值 = 已一目了然 → 合规
  · 单维：valueText 必须带**类型词**，不能只是裸档位
  · 面额型（`500积分`/`50元`）：货币单位本身就是类型的一部分 → 合规，
    但维度名必须写清是什么货币（`积分:500` / `面额:50元`），不能只有裸数字

🔴 为什么不许把多维强行合成一维字符串：
   多维是平台原生能力，买家按维度逐级选择；合成一维会丢掉筛选能力，
   且 `specName` 结构变化会触发 SKU ID 重排（见操作-从货源编号新建宝贝 L303）。
"""

import re

# 纯档位形态（无类型词）
NUM = r"[\d一二三四五六七八九十百千万.]+"
DUR = r"(?:天|日|周|个月|月|季|半年|年|小时|分钟|次|张|个)"
MONEY = r"(?:元|币|点|钻石|音符|积分|豆|券)"

RE_PURE_DUR = re.compile(r"^" + NUM + DUR + r"(?:" + NUM + DUR + r")*$")
RE_PURE_MONEY = re.compile(r"^" + NUM + MONEY + r"(?:$|[^\d])")
RE_LEAD_DUR = re.compile(r"^(" + NUM + DUR + r")")

# 归属/限定后缀：这些是**必要**信息，不算「类型前缀缺失」
QUALIFIER_HINTS = ("首单", "限购", "限一次", "新客", "体验", "特惠", "号", "每月")

# 类型词表：SKU 名里出现任一 = 已说明类型
TYPE_WORDS = (
    # 会员等级 / 身份
    "会员", "VIP", "SVIP", "超级", "至臻", "基础", "普通", "高级", "豪华", "尊贵",
    "钻石", "白金", "黄金", "白银", "青铜",
    "学生", "儿童", "成人", "长者", "青春", "校园",
    # 产品线 / 卡种
    "单车", "电单车", "助力车", "畅骑", "次卡", "时长卡", "储时卡", "周卡", "月卡",
    "季卡", "年卡", "单次", "月付", "网盘", "小说", "扫描", "设计", "AI",
    # 货币 / 面额单位（货币类型也算「类型」）
    "积分", "元", "币", "点", "钻石", "音符", "豆", "券", "面额", "余额",
    # 形态
    "直充", "卡密", "CDK", "兑换",
)


def strip_first(name):
    return name[2:] if str(name).startswith("首单") else str(name)


def has_type_word(name):
    """SKU 值是否已含类型词（会员类型 / 货币单位 / 产品线）。"""
    core = strip_first(name)
    low = core.lower()
    return any(w.lower() in low for w in TYPE_WORDS)


def is_bare_tier(name):
    """是否只是裸**时长**档位（`7天` / `1个月`）。

    🔴 面额型（`500积分` / `50元`）**不算裸档位** —— 货币单位本身就是类型信息，
       买家看到「500积分」知道是积分不是天数。这类由 judge_sku 单独判
       「维度名是否说清币种」，不能笼统归为「缺类型」。
    """
    core = strip_first(name).strip()
    if not core:
        return False
    if has_type_word(core):
        return False
    return bool(RE_PURE_DUR.match(core))


def sku_dims(sku):
    """取 SKU 的维度列表 [(维度名, 值)]。"""
    out = []
    for p in (sku.get("propertyList") or []):
        out.append((str(p.get("propertyText") or ""), str(p.get("valueText") or "")))
    return out


def judge_sku(sku):
    """判定单个 SKU 规格名是否「一目了然」。返回 (ok, 说明)。

    ok=True  /  ok=False（需补类型）  /  ok=None（形态未识别，人工确认）
    """
    dims = sku_dims(sku)
    if not dims:
        return None, "无 propertyList，读不到规格名"

    # 多维：每个维度都有非空值 → 买家逐级可选，已一目了然
    if len(dims) >= 2:
        empty = [d for d, v in dims if not v.strip()]
        if empty:
            return False, "多维但有维度值为空：%s" % "、".join(empty)
        return True, "多维规格（%s）" % " / ".join("%s:%s" % (d, v) for d, v in dims)

    dim, val = dims[0]
    if not val.strip():
        return False, "规格值为空"

    core = strip_first(val).strip()
    money_words = ("积分", "元", "币", "点", "钻石", "音符", "豆", "券", "面额", "金额")
    dim_says_money = any(w in dim for w in money_words)

    # ① 维度名已说明币种（`积分:500` / `面额:50元`）→ 类型信息齐备，放行
    if dim_says_money:
        return True, "维度名已说明币种（%s:%s）" % (dim, val)

    # ② 值里自带货币单位（`500积分` / `50元`）：单位即类型 → 放行
    if RE_PURE_MONEY.match(core):
        return True, "面额型自带币种（%s:%s）" % (dim, val)

    # ③ 裸时长档位 → 必须补类型
    if is_bare_tier(core):
        return False, "单维裸档位「%s」：只有档位，没有会员类型/货币单位" % val

    # ④ 纯数字且维度名也没说币种 → 看不出来是什么
    if re.fullmatch(NUM, core) and dim in ("规格", "选项", ""):
        return False, "「%s」是纯数字，维度名也未说明币种/类型" % val

    if has_type_word(core):
        return True, "已含类型词：%s" % val

    return None, "形态未识别「%s」，请人工确认是否够清楚" % val


def audit_item(item):
    """巡检一件商品的全部 SKU。返回 (bad_list, ok_count, unknown_list)。"""
    bad, unknown, ok = [], [], 0
    for s in (item.get("itemSkuList") or []):
        st, why = judge_sku(s)
        if st is False:
            bad.append((s.get("skuId"), s.get("price"), why))
        elif st is None:
            unknown.append((s.get("skuId"), s.get("price"), why))
        else:
            ok += 1
    return bad, ok, unknown


# ---------------------------------------------------------------- 生成前缀

# 从商品标题抽「类型前缀」的候选：优先书名号/方括号里的，其次第一个档位数字之前的部分
_NOISE = ("【自动充值】", "【官方直充】", "【官方CDK】", "【官方】", "【卡密】",
          "【只支持移动手机号充值】", "官方直充", "自动充值", "官方CDK", "直充自己账号",
          "下单填写", "手机号", "填手机号", "官方卡密", "多档时长")


def type_prefix(title, product_name=""):
    """从标题/商品名推导 SKU 类型前缀，如「哔哩哔哩大会员」→「大会员」。

    返回 (prefix, 依据)。推不出时返回 ("", 原因) —— 不猜。
    """
    src = str(product_name or title or "").strip()
    for n in _NOISE:
        src = src.replace(n, " ")
    # 在第一个档位数字处截断
    m = re.search(NUM, src)
    if m and m.start() > 0:
        src = src[:m.start()]
    # 去掉常见尾缀
    for tail in ("会员", "VIP"):
        pass
    src = re.sub(r"[\s/、,，|]+", " ", src).strip()
    if not src:
        return "", "标题里没有可用于类型前缀的产品名词"
    return src, "取自标题首个档位之前的产品名"
