# -*- coding: utf-8 -*-
"""商战网络 (qqkami / ShangZhan) 货源适配器。

作用：把商战开放 API 的返回**归一化成志远 v3 的字段契约**，这样
`alds_dict.detail()/cost()/balance()` 与 `deploy.py` 无需改动即可使用商战货源。

字段契约（志远 v3 侧）：
    salesPrice     进价（做定价用；双价陷阱只认它）
    goodsType      3=直充 / 1=卡密
    rechargeTemplates  [{title,...}]  → 供 recharge_types_from_detail 推 ⑩ 类型
    minQuantity/maxQuantity  限购
    stockCount     库存

凭据位置：https://www.qqkami.com/userCenter/securitySettings → 「接口秘钥」弹窗
    customerid = 客户编号（1321023）
    sign       = 接口秘钥（进货接口访问密钥）

接口（均 POST 表单，返回 json；全局 code 1000=成功）：
    /api.php/Client/getCustomerInfo         商家信息（含余额）
    /api.php/Client/goodsInfo               单个商品详情（限 1 秒 1 次）
    /api.php/Client/designatedProductList   批量指定商品（限 3 秒 1 次，id 逗号分隔）
    /api.php/Client/goodsList               全量商品列表（限 **300 秒** 1 次；关键词搜索靠它：
                                             拉全量目录落本地缓存 → 按 name 本地过滤，见 catalog()/search_catalog()）
    /api.php/Client/createOrder             直充下单
    /api.php/Client/createCdKeyOrder        卡密下单
    /api.php/Client/orderDetail             订单详情（限 1 秒 1 次）
    /api.php/Client/getOrderList            订单列表
错误码：1001 参数不合法 / 1003 签名错误 / 1004 访问频繁 / 1006 客户编号不存在
        1008 未开通供货接口 / 1009 未开通进货接口 / 1010 无数据
"""
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

# 商战证书链在本机不可信（缺中间 CA）→ 走不再校验的 opener。
# 仅对本供货商接口使用，不影响其他请求。
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_CACHE = os.path.join(HERE, "_qqkami_catalog.json")   # 全量目录本地缓存
CATALOG_TTL = 330.0   # goodsList 限流 300s/次 → 缓存比限流多 30s 缓冲

HOST = "https://www.qqkami.com"
CID = "1321023"
SIGN = "2e9fd1dc44e5191f190fb108007840c0"   # 接口秘钥 = 文档里的 sign

# 商战 type(1卡密 2代充) → 志远 goodsType(1卡密 3直充)
_TYPE_MAP = {1: 1, 2: 3}

_last = [0.0]


def _throttle(gap=1.1):
    """默认按最严的 1 秒 1 次节流；goodsList 需 300 秒由调用方自行等待。"""
    d = time.time() - _last[0]
    if d < gap:
        time.sleep(gap - d)
    _last[0] = time.time()


def call(path, params=None, timeout=25, throttle=True):
    """POST 表单调用。自动补 customerid / sign。返回 dict（失败给 {'code':-1,...}）。"""
    if throttle:
        _throttle()
    payload = dict(params or {})
    payload.setdefault("customerid", CID)
    payload.setdefault("sign", SIGN)
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        HOST + path, data=data,
        headers={"content-type": "application/x-www-form-urlencoded",
                 "user-agent": "Mozilla/5.0"})
    try:
        raw = _OPENER.open(req, timeout=timeout).read().decode("utf-8", "ignore")
    except Exception as e:
        return {"code": -1, "info": "HTTP_ERR " + repr(e)[:160]}
    try:
        return json.loads(raw)
    except Exception:
        return {"code": -2, "info": "BAD_JSON", "raw": raw[:300]}


# ---------------- 原始接口 ----------------
def raw_goods_info(gid):
    """单个商品详情（限 1 秒 1 次）。"""
    return call("/api.php/Client/goodsInfo", {"id": gid})


def raw_multi(ids):
    """批量指定商品（限 3 秒 1 次）。ids 可为 list 或 '1,2,3'。"""
    if isinstance(ids, (list, tuple)):
        ids = ",".join(str(x) for x in ids)
    return call("/api.php/Client/designatedProductList", {"id": ids}, throttle=True)


def raw_goods_list(page=1):
    """全量商品列表（限 **300 秒** 1 次）。注意：不是关键词搜索。"""
    return call("/api.php/Client/goodsList", {"page": page}, throttle=False)


def raw_customer():
    """商家信息（客户编号 / 余额）。"""
    return call("/api.php/Client/getCustomerInfo", {})


# ---------------- 归一化 ----------------
def norm_goods(d):
    """商战 goodsInfo.data → 志远 detail 字段契约。"""
    if not isinstance(d, dict) or not d:
        return {}
    tpl = d.get("template") or {}
    tpls = []
    acct = str(tpl.get("account") or "").strip()
    if acct:
        tpls.append({"title": acct, "placeholder": acct, "key": "account", "lblName": "account"})
    content = tpl.get("content")
    if isinstance(content, list):
        for c in content:
            if not isinstance(c, dict):
                continue
            nm = str(c.get("name") or "").strip()
            if nm:
                tpls.append({"title": nm, "placeholder": str(c.get("value") or ""),
                             "key": str(c.get("index") or ""), "lblName": nm})
    try:
        gt = _TYPE_MAP.get(int(d.get("type") or 0))
    except Exception:
        gt = None
    return {
        "goodsId": d.get("id"),
        "name": d.get("name"),
        "salesPrice": d.get("price"),
        "faceValue": d.get("face_value"),
        "goodsType": gt,
        "stockCount": d.get("stock_num"),
        "minQuantity": 1,
        "maxQuantity": d.get("quantity"),
        "rechargeTemplates": tpls,
        "limitPrice": d.get("limit_price"),
        "supplyState": d.get("supply_state"),
        "stockState": d.get("stock_state"),
        "allowApiOrdering": d.get("allow_api_ordering"),
        "img": d.get("img"),
        "notice": d.get("notice"),
        "info": d.get("info"),
        "supplier": "qqkami",
    }


# ---------------- 全量目录缓存（goodsList，300 秒 1 次） ----------------
def _read_cache():
    """读本地目录缓存 → (ts, items) 或 None。"""
    try:
        with open(CATALOG_CACHE, "r", encoding="utf-8") as f:
            c = json.load(f)
        ts = float(c.get("ts") or 0)
        items = c.get("items") or []
        if ts and isinstance(items, list) and items:
            return (ts, items)
    except Exception:
        pass
    return None


def _write_cache(items):
    try:
        with open(CATALOG_CACHE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "items": items}, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def catalog(refresh=False):
    """取全量商品目录（优先本地缓存，过期/refresh 才调 goodsList）。

    返回 list[dict]；刷新失败（限流 1004 / 网络）时退回旧缓存兜底，全无则 None。
    注意：目录只用于**发现商品**（id+name），进价以 goodsInfo 详情实时为准。
    """
    cache = _read_cache()
    if cache and not refresh and (time.time() - cache[0]) < CATALOG_TTL:
        return cache[1]
    r = raw_goods_list(page=1)
    d = r.get("data")
    if r.get("code") == 1000 and isinstance(d, list) and d:
        _write_cache(d)
        return d
    # 刷新失败 → 旧缓存兜底（哪怕过期也胜过没有）
    return cache[1] if cache else None


def search_catalog(kw):
    """从全量目录里按关键词过滤（name 包含 kw，大小写不敏感）。
    返回 [{id, name, price, type, ...}]，按相关度（名称短者优先）排序。"""
    items = catalog()
    if not items:
        return []
    kws = [kw] if isinstance(kw, str) else list(kw or [])
    lows = [str(k).lower() for k in kws if k]
    hits = []
    for it in items:
        nm = str(it.get("name") or "")
        low = nm.lower()
        if any(k in low for k in lows):
            hits.append(it)
    hits.sort(key=lambda x: len(str(x.get("name") or "")))
    return hits


# ---------------- 对 v3_huafei 的三个契约入口 ----------------
def detail(gid):
    """等价于 v3_huafei.detail(p, gid)：返回 {code, data:{归一化字段}}。"""
    r = raw_goods_info(gid)
    if r.get("code") != 1000:
        return {"code": r.get("code"), "info": r.get("info"), "data": None}
    return {"code": 1000, "info": r.get("info"), "data": norm_goods(r.get("data") or {})}


def balance():
    """等价于 v3_huafei.balance(p)：返回 {code, data:{balance:float}}。"""
    r = raw_customer()
    if r.get("code") != 1000:
        return {"code": r.get("code"), "info": r.get("info"), "data": None}
    try:
        bal = float((r.get("data") or {}).get("user_balance") or 0)
    except Exception:
        bal = None
    return {"code": 1000, "info": r.get("info"), "data": {"balance": bal}}


def search(kw):
    """关键词搜索（**纯 API 密钥，无浏览器依赖**，2026-10-15 改）。

    商战没有关键词搜索接口，但 goodsList 可一把拉全量目录（含 id/name/price，
    限流 300 秒 1 次）→ 本地缓存 + 关键词过滤即可完成搜索。
    **目录一旦可用（含旧缓存兜底）就只走 API 过滤**，零命中也直接返回空，
    不再退回前台；仅当目录完全不可用（从未预热且刷新被限流）才走前台页面
    搜索（需 edge-bridge）。
    返回 {code:1000, data:{items:[{goodsId,name,salesPrice,goodsType}]}}，与 v3 同形。
    """
    items = catalog()
    if items is not None:
        kws = [kw] if isinstance(kw, str) else list(kw or [])
        lows = [str(k).lower() for k in kws if k]
        hits = [it for it in items
                if any(k in str(it.get("name") or "").lower() for k in lows)]
        hits.sort(key=lambda x: len(str(x.get("name") or "")))
        return {"code": 1000, "info": "目录过滤命中 %d" % len(hits),
                "data": {"items": [{"goodsId": it.get("id"),
                                    "name": it.get("name") or "",
                                    "salesPrice": it.get("price"),
                                    "goodsType": _TYPE_MAP.get(int(it.get("type") or 0))}
                                   for it in hits]}}
    # 目录完全不可用 → 退回前台页面搜索
    try:
        import qqkami_search as _s
        rows = _s.search_front(kw)
        return {"code": 1000, "info": "查询成功",
                "data": {"items": [{"goodsId": r["id"], "name": r.get("name") or ""} for r in rows]}}
    except Exception as e:
        return {"code": -1, "info": "目录未预热且前台搜索需要 edge-bridge：%s" % repr(e)[:120],
                "data": {"items": []}}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "multi":
        print(json.dumps(raw_multi(sys.argv[2]), ensure_ascii=False)[:1200])
    elif len(sys.argv) > 2 and sys.argv[1] == "search":
        r = search(sys.argv[2])
        items = (r.get("data") or {}).get("items") or []
        print("code=%s info=%s 命中=%d" % (r.get("code"), r.get("info"), len(items)))
        for it in items[:30]:
            print("  %-8s %-10s %s" % (it.get("goodsId"), it.get("salesPrice"),
                                       str(it.get("name"))[:50]))
    elif len(sys.argv) > 1 and sys.argv[1] == "catalog":
        items = catalog()
        print("catalog items =", len(items or []))
    elif len(sys.argv) > 1:
        print(json.dumps(detail(sys.argv[1]), ensure_ascii=False, indent=1)[:1500])
    else:
        print(json.dumps(balance(), ensure_ascii=False))
