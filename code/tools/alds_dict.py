# -*- coding: utf-8 -*-
"""阿奇索(alds) 枚举字典 + golden 默认值 + 货源映射（单一权威来源）。
所有脚本一律 import 本模块，禁止再硬编码 / 逆向前端 JS 猜枚举。

枚举来源：2026-10-09 抓 agiso 前端 chunk 实锤 + 全店健康商品 golden 比对。
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))

# ============ 枚举 ============
# 内容方式 spType
SP_TYPE = {1: "单卡种", 2: "发卡方案", 3: "无卡", 4: "接口", 5: "接口方案", 6: "自有货源"}
SOURCE_SP_TYPE = 6   # 凡货源自 agiso 供货商账号(志远/星芒/省省/追梦)，不论直充 or 卡密，一律 = 6

# 发货方法 sendTypeOption
SEND_TYPE = {24: "无卡密(闲鱼消息·无提取)", 28: "提取/自动发货"}
GOOD_SEND_TYPE = 28

# 直充账号类型 rechargeAccountTypes（可组合，如 [8,16,4]）
# 🔴 128=剪映号（前端 Tl.JianYing=128，2026-11-15 按知识库 上品规则 §81 / 一条龙 §172 补录）
RECHARGE_TYPE = {1: "手机号", 2: "固话", 4: "平台账号", 8: "QQ号", 16: "微信号", 32: "邮箱",
                 128: "剪映号", 256: "ID类(抖音号/快手ID)"}
PLATFORM_ACCOUNT = [4]

# ============ 货源映射 ============
ACCT_PLATFORM = {95425: "卡密 zy.kkam", 95105: "星芒 xmang", 95131: "省省 ssyq", 95329: "追梦 sup12",
                 96810: "商战 qqkami",
                 93310: "千城 (无v3接口·不可自动校验)",
                 # 思券（2026-11-09 用户实证：账号可用，页面发货设置里能选到、能绑关联商品）
                 99569: "思券 siquan"}
# 有 v3 接口、可自动校验「起购区间 min/max」的货源。
# 注意：余额校验不看这个集合 —— 思券 99569 的余额已能走手机通道直读（2026-11-12）。
VERIFIABLE_ACCTS = {95425, 95105, 95131, 95329, 96810}
DEFAULT_ACCT = 95425          # 志远（用户定：默认首选，最便宜）

# 🔴 2026-11-09：思券走**阿奇索货源接口**取价，不用它自己的 v3 站点。
#    背景：思券站 88.sqqy88.cn 自 2026-11-03 起返回 200 空正文（PHP 静默 exit），
#    v3 通道全线不通；但阿奇索侧的 /api/AcprSerivces/GetSupplierProductList 正常，
#    且其 productCost 与思券 goods_price **实测分毫不差**（2026-11-09 九档逐一核对）。
#    该接口真实参数名是 `idNo`（供货商账号 ID），不是 supplierAccountId。
ALDS_SIDED_ACCTS = {99569}     # 走阿奇索侧取价的账号


# ============ 阿奇索侧货源查询（思券等 v3 不通的货源）============
_ALDS_SIDED_CACHE = {}


def alds_sided_products(acct):
    """拉某账号下的货源商品列表（带缓存，同一次 deploy 内不重复请求）。"""
    a = int(acct)
    if a in _ALDS_SIDED_CACHE:
        return _ALDS_SIDED_CACHE[a]
    try:
        import agiso_direct as A
        items = A.get_supplier_products(a) or []
    except Exception:
        items = []
    _ALDS_SIDED_CACHE[a] = items
    return items


def alds_sided_product(acct, pno):
    """按商品编号在阿奇索货源列表里定位一条（pno 可能是 int 或 str）。"""
    key = str(pno)
    for it in alds_sided_products(acct):
        if str(it.get("productNo")) == key:
            return it
    return None


def alds_sided_cost(acct, pno):
    """阿奇索侧货源供货价（productCost）。取不到返回 None。"""
    it = alds_sided_product(acct, pno)
    if not it:
        return None
    try:
        return float(it.get("productCost"))
    except Exception:
        return None


def alds_sided_name(acct, pno):
    it = alds_sided_product(acct, pno)
    return (it or {}).get("productTitle") or ""


def alds_sided_purchasable(acct, pno):
    """阿奇索侧货源商品是否可购（isAllowPurchase）。取不到返回 None（未知）。"""
    it = alds_sided_product(acct, pno)
    if not it:
        return None
    v = it.get("isAllowPurchase")
    return None if v is None else bool(v)


# ============ 全店基准 ============
DEFAULT_PROFIT = 0.066        # 售价 = 进价 / (1-0.066)  —— 2026-11-09 用户定 6.6%
DEFAULT_STOCK = 9999
FIRST_ORDER_MIN_PRICE = 5.0   # 引流款参考下限（**非硬规则**：实测 Q币4.81/快手4.58 等低于5元属正常，仅提示）

# ============ 关键不变量（偏离即视为故障）============
INVARIANT_GOODS = {"spType": 6, "sendTypeOption": 28, "autoSend": True, "apiType": 2,
                   "contentTplId": -1, "enableSendByTiqu": True,
                   "disableSendSalePriceToSupplier": False}
INVARIANT_SKU = {"spType": 6, "sendTypeOption": 28, "autoSend": True, "apiType": 2,
                 "contentTplId": -1, "enableSendByTiqu": True}

# ============ golden 模板 ============
_KIND_ALIAS = {"recharge": "recharge_multi", "kaomi": "kaomi_multi",
               "single": "single_recharge",
               "recharge_multi": "recharge_multi", "kaomi_multi": "kaomi_multi",
               "single_recharge": "single_recharge"}


def golden(kind):
    """返回该类的 golden 字段集 {ref_goods, goods_level, sku_level, sku_count}。"""
    k = _KIND_ALIAS.get(kind, kind)
    with open(os.path.join(HERE, "golden_templates.json"), encoding="utf-8") as f:
        t = json.load(f)
    g = t["kinds"].get(k)
    if not g:
        raise KeyError("未知 kind=%s（可选 recharge/kaomi/single）" % kind)
    return g


# ============ 货源侧查询（v3）============
def _platform(acct):
    from v3_huafei import PLATFORMS
    name = ACCT_PLATFORM.get(int(acct))
    if not name or name not in PLATFORMS:
        return None
    return PLATFORMS[name]


def detail_raw(pno, acct=DEFAULT_ACCT):
    """货源详情原始返回 {code,msg,data}（用于区分『pno不存在』与『接口异常』）。"""
    from v3_huafei import detail as _d
    p = _platform(acct)
    if not p:
        return None
    return _d(p, str(pno))


def detail(pno, acct=DEFAULT_ACCT):
    """查货源详情（进价 salesPrice / 限购 min~maxQuantity / 参数 rechargeTemplates / goodsType）。"""
    # 🔴 2026-11-09：v3 不通的账号（思券）改走阿奇索货源接口。
    #    阿奇索侧没有 min/max 起充与 goodsDetail → 只给能确证的字段，
    #    缺失字段留空（下游按「取不到」处理，不臆造）。
    if int(acct) in ALDS_SIDED_ACCTS:
        it = alds_sided_product(acct, pno)
        if not it:
            return {}
        try:
            cost = float(it.get("productCost"))
        except Exception:
            cost = None
        ptype = int(it.get("productType") or 0)
        return {"name": it.get("productTitle") or "",
                "salesPrice": cost,
                "goodsType": ptype,
                # 🔴 productType: 1=官方直充 / 2=卡密（2026-11-12 用志远直充样板+
                #    思券 pno241【官方直充】/pno19【官方卡密】交叉标定；旧映射写反过）
                "goodsTypeName": {1: "官方直充", 2: "卡密"}.get(ptype, ""),
                "minQuantity": None, "maxQuantity": None,
                "limitBalance": None, "rechargeTemplates": [], "goodsDetail": ""}
    r = detail_raw(pno, acct)
    return (r or {}).get("data")


def cost(pno, acct=DEFAULT_ACCT):
    """货源真实进价 salesPrice（双价陷阱：只认它）。"""
    d = detail(pno, acct)
    try:
        return float(d.get("salesPrice"))
    except Exception:
        return None


def balance(acct=DEFAULT_ACCT):
    # 🔴 2026-11-12：思券没有 v3 通道（/api/v3/* 全线 Route Not Found），
    #    改走手机通道 POST /front/diy/user/info 直读 data.userinfo.balance。
    #    手机未连接/接口异常时退回 None（与旧版「读不到」行为一致，check_balance 会提示人工确认）。
    if int(acct) in ALDS_SIDED_ACCTS:
        try:
            import importlib.util
            import os
            p = os.path.join(os.path.expanduser("~"), "Desktop", "workbuddy",
                             "文档提取", "siquan_phone.py")
            sp = importlib.util.spec_from_file_location("_siquan_phone_balance", p)
            m = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(m)
            return float(m.user_balance()["balance"])
        except Exception:
            return None
    from v3_huafei import balance as _b
    p = _platform(acct)
    if not p:
        return None
    try:
        return float(((_b(p) or {}).get("data") or {}).get("balance"))
    except Exception:
        return None


# 类型码 → 买家填写项文案（主图印字 / 描述【填写内容】用）
BUYER_LABEL = {1: "手机号", 2: "固话", 4: "平台账号", 8: "QQ号", 16: "微信号",
               32: "邮箱", 128: "剪映号", 256: "账号ID"}


def buyer_label_for(types):
    """把 rechargeAccountTypes 转成印在主图/描述里的买家填写项文案。"""
    if not types:
        return ""
    code = int(types[0])
    return BUYER_LABEL.get(code) or RECHARGE_TYPE.get(code, "")


# 表单字段名（真实字段名，可直接命中）。🔴 通用「充值账号」不在表内 —— 它同时可能是
# 手机号或平台账号，必须靠主图/介绍的填写语义区分，不许无脑当 [4]。
_NAME_RULE = [("剪映", [128]), ("抖音", [256]), ("快手", [256]),
              ("qq", [8]), ("微信", [16]), ("邮箱", [32]), ("固话", [2]),
              ("手机号", [1]), ("手机", [1]), ("电话", [1]),
              ("平台账号", [4]), ("平台id", [4]), ("平台 id", [4]),
              ("会员账号", [4]), ("账号id", [4]), ("账号 id", [4]),
              ("游戏账号", [4]), ("游戏id", [4]),
              ("uid", [4]), ("用户名", [4]), ("userid", [4])]

# 🔴 自由文字（介绍/OCR/须知）必须带「填写语义」才算证据。
#    2026-11-15 实测教训：26652 详情图写「适用范围：支持手机、电脑、平板使用」，
#    裸关键词「手机」会被误判成「买家要填手机号」→ ⑩ 勾错类型。设备支持 ≠ 填写项。
_FILL_VERB = r'(填写|填入|输入|提交|提供|填好|请填|需填|要填|备注|留言)'
# 顺序 = 优先级：具体平台 ID 先于泛称，手机先于「账号」，避免「填写手机号」被「账号」抢先。
_CTX_RULE = [
    (r'剪映(号|id|账号)?', [128]),
    (r'抖音(号|id|账号)?', [256]),
    (r'快手(号|id|账号)?', [256]),
    (r'(qq|QQ)(号|账号)?', [8]),
    (r'微信(号|账号)', [16]),
    (r'邮箱(地址|号)?', [32]),
    (r'固话|座机', [2]),
    (r'手机(号|号码|号吗)?', [1]),
    # 平台账号族：买家要填的是对方平台的账号/ID，不是手机号
    (r'(平台|会员|游戏|充值)(账号|帐号|号|id|ID)', [4]),
    (r'(账号|帐号|id|ID|uid|UID)', [4]),
]


def _signals_of(d):
    """收集可判定「买家要填什么」的全部文字证据。"""
    parts = []
    for t in (d or {}).get("rechargeTemplates") or []:
        if isinstance(t, dict):
            parts.append(str(t.get("title") or t.get("placeholder") or t.get("name") or ""))
        else:
            parts.append(str(t))
    for k in ("goodsDescribe", "text", "notice", "goodsDetailText", "_ocr"):
        v = (d or {}).get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    return parts


def recharge_types_from_detail(d):
    """推断**明确要求**的 rechargeAccountTypes。返回 (types:list|None, note:str)。

    三级判定（从严到宽）：
      ① 货源 rechargeTemplates 的 title/placeholder —— 这是真实表单字段名，直接命中即可；
      ② 自由文字里带填写语义（填写/输入/提交…）的目标项 —— 允许「下单请填写手机号」；
      ③ 都没有 → 返回 None，由调用方要求显式指定。**禁止默认猜 [4]。**

    🔴 「支持手机、电脑、平板使用」这类**设备支持**描述不算填写证据（2026-11-15 实测误判）。
    """
    # ① 表单字段名
    titles = []
    for t in (d or {}).get("rechargeTemplates") or []:
        if isinstance(t, dict):
            titles.append(str(t.get("title") or t.get("placeholder") or t.get("name") or ""))
        else:
            titles.append(str(t))
    tpl_blob = " ".join(titles).lower()
    for kw, types in _NAME_RULE:
        if kw in tpl_blob:
            return types, "表单字段命中『%s』→ %s" % (kw, RECHARGE_TYPE.get(types[0]))

    # ② 自由文字 + 填写语义
    free = []
    for k in ("goodsDescribe", "text", "notice", "goodsDetailText", "_ocr"):
        v = (d or {}).get(k)
        if isinstance(v, str) and v.strip():
            free.append(v)
    blob = " ".join(free)
    if blob.strip():
        for pat, types in _CTX_RULE:
            m = re.search(_FILL_VERB + r'[^。；;\n]{0,8}?' + pat, blob)
            if m:
                return types, "介绍/图片含填写语义『%s』→ %s" % (m.group(0)[:24], RECHARGE_TYPE.get(types[0]))

    # ③ 判定不出
    seen = " ".join(titles) if titles else "（无参数模板）"
    return None, "仅通用名「%s」，介绍/图片也没有带填写语义的目标项" % seen[:60]


def param_from_detail(d):
    """从货源 rechargeTemplates 推 (var_key, var_name, var_desc)。"""
    for t in (d or {}).get("rechargeTemplates") or []:
        if not isinstance(t, dict):
            continue
        title = t.get("title") or t.get("placeholder") or "充值账号"
        return (t.get("lblName") or t.get("key") or "account", title,
                t.get("placeholder") or ("请输入" + str(title)))
    return ("account", "充值账号", "请输入充值账号")


# ============ SKU 级 alds 配置构造 ============
def build_sku_cfg(kind, tpl_sku, acct, sku_id=None, spec_name=None,
                  pno=None, multiple=1, platform_price_type=2,
                  var_key=None, var_value=None, var_name=None, var_desc=None,
                  additional=None, goods_id=None):
    """由 golden 的 SKU 级模板 + 覆盖字段，生成 SaveSkuAldsInfo 的 payload。
    强制写入不变量（spType/sendTypeOption/tiqu/autoSend/apiType/contentTplId）。

    🔴 `goods_id` 必须传！后端靠 goodsId 定位商品，缺了会报
       「获取商品信息出错，查询失败，请重试。15，Remote service error」（2026-10-10 实锤）。
    """
    c = dict(tpl_sku or {})
    c.pop("createTime", None); c.pop("modifyTime", None)
    if goods_id is not None:
        c["goodsId"] = str(goods_id)
    else:
        c.pop("goodsId", None)
    c["idNo"] = 0
    if sku_id is not None:
        c["skuId"] = str(sku_id)
    if spec_name is not None:
        c["specName"] = spec_name
    c["supplierAccountId"] = int(acct)
    if pno is not None:
        c["supplierProductNo"] = str(pno)
    c["multiple"] = multiple
    c["platformPriceType"] = platform_price_type
    # 强制不变量
    c.update(INVARIANT_SKU)
    c["productType"] = 2 if kind in ("kaomi", "kaomi_multi") else 1
    if kind in ("kaomi", "kaomi_multi"):
        c["supplierParamJson"] = ""
        c["attach"] = []
        c["multiple"] = 1
        if additional is not None:
            c["additional"] = additional
    else:
        vk = var_key or "account"
        vv = var_value or "{$充值账号}"
        c["supplierParamJson"] = json.dumps({vk: vv}, ensure_ascii=False)
        c["attach"] = [{"name": vk, "key": vk, "type": "text",
                        "title": var_name or "充值账号",
                        "desc": var_desc or ("请输入" + (var_name or "充值账号")),
                        "vali": "all", "tip": "", "value": vv, "required": True}]
    return c


def build_goods_cfg(kind, tpl_goods, gid, id_no, sp_type=None):
    """由 golden 的商品级模板生成 SaveGoodsAldsInfo 的 payload（用于 ⑨ 登记）。"""
    p = dict(tpl_goods or {})
    p.pop("createTime", None); p.pop("modifyTime", None)
    p["goodsId"] = str(gid)
    p["idNo"] = id_no if id_no is not None else p.get("idNo")
    p["defineSku"] = kind not in ("single", "single_recharge")
    p.update(INVARIANT_GOODS)
    p["spType"] = sp_type or SOURCE_SP_TYPE
    return p


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("SP_TYPE:", SP_TYPE)
    print("SEND_TYPE:", SEND_TYPE)
    print("RECHARGE_TYPE:", RECHARGE_TYPE)
    print("DEFAULT_ACCT =", DEFAULT_ACCT, ACCT_PLATFORM.get(DEFAULT_ACCT))
    for k in ("recharge", "kaomi", "single"):
        g = golden(k)
        print("golden %-8s ref=%s SKU=%s" % (k, g["ref_goods"], g["sku_count"]))
    print("志远余额 =", balance())
