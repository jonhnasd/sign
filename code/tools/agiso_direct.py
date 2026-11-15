# -*- coding: utf-8 -*-
"""agiso 直连 HTTP 封装：绕过 edge-bridge 浏览器 fetch（桥接 fetch 卡死时可用）。
token 取自 agiso 页面 localStorage，本机 curl 直连可达 agiso。
"""
import json, time, os, re, shutil, tempfile, urllib.request, urllib.error

BASE = "https://aldsidle.agiso.com"
BRIDGE = "http://127.0.0.1:8787/rpc"

# token 不持久化：一律经桥接从已登录的 agiso 页面 localStorage 现取（agiso token 易挂，现取才拿得到新的）
TOKEN = ""


_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本机 127.0.0.1 一律直连，绕过 http_proxy


def _bridge(cmd, params, t=20):
    body = json.dumps({"cmd": cmd, "params": params, "timeout": t * 1000}).encode()
    req = urllib.request.Request(BRIDGE, data=body, headers={"content-type": "application/json"})
    with _NOPROXY.open(req, timeout=t + 5) as r:
        return json.loads(r.read().decode())


_AGISO_LIST_URL = "https://aldsidle.agiso.com/#/goodsManage/goodsList"
_last_tab_open = 0.0            # 新开 agiso 页的限频时间戳（避免 401 风暴时刷标签页）
_TAB_OPEN_COOLDOWN = 20         # 秒：两次自动开页之间的最小间隔


def _find_agiso_tab():
    tabs = (_bridge("tabs_list", {}) or {}).get("data") or []
    for tb in tabs:
        if "aldsidle.agiso.com" in str(tb.get("url", "")):
            return tb.get("id")
    return None


def _read_token_from_tab(tab_id):
    o = _bridge("eval", {"tabId": tab_id, "code": "localStorage.getItem('TOKEN')||''"})
    return ((o or {}).get("data") or {}).get("value")


def token_from_browser(open_if_missing=True, force_new=False, wait=16):
    """经桥接从 agiso 页面 localStorage 取最新 TOKEN。

    - 优先复用现有 agiso 标签页（同步 eval，无需页面 fetch，最稳）；
    - force_new=True 或没有 agiso 页 / 页内 token 为空时：新开一个 agiso 页，
      让 SPA 加载时把新 TOKEN 写回 localStorage，再轮询读取（限频 _TAB_OPEN_COOLDOWN）。
    """
    global _last_tab_open
    if not force_new:
        tid = _find_agiso_tab()
        if tid is not None:
            try:
                v = _read_token_from_tab(tid)
            except Exception:
                v = None
            if v:
                return v
    if not open_if_missing:
        return None
    if time.time() - _last_tab_open < _TAB_OPEN_COOLDOWN:
        return None
    _last_tab_open = time.time()
    try:
        o = _bridge("tab_new", {"url": _AGISO_LIST_URL}, 30)
    except Exception:
        return None
    if not (o or {}).get("ok"):
        return None          # 扩展/SW 不可用 → 直接失败，别空等轮询（上层会降级到 leveldb）
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(2)
        tid = _find_agiso_tab()
        if tid is not None:
            try:
                v = _read_token_from_tab(tid)
            except Exception:
                v = None
            if v:
                return v
    return None


# ---- 离线备用通道：扩展/SW 卡死时，直接读 Edge localStorage leveldb 找 token ----
_LEVELDB_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                            r"Microsoft\Edge\User Data\Default\Local Storage\leveldb")
_TOKEN_RE = re.compile(rb"[0-9A-Fa-f]{32}:[0-9A-Fa-f]{64}")


def token_candidates_from_leveldb():
    """按「leveldb 文件越新越可能是当前 token」顺序返回候选（只读复制，不动原文件）。"""
    try:
        files = [os.path.join(_LEVELDB_DIR, f) for f in os.listdir(_LEVELDB_DIR)]
    except Exception:
        return []
    files = [f for f in files if os.path.isfile(f) and not f.endswith("LOCK")]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    tmp = os.path.join(tempfile.gettempdir(), "edge_ls_tok")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        os.makedirs(tmp, exist_ok=True)
    except Exception:
        return []
    seen, out = set(), []
    for src in files:
        try:
            dst = os.path.join(tmp, os.path.basename(src))
            shutil.copy2(src, dst)
            data = open(dst, "rb").read()
        except Exception:
            continue
        if b"agiso" not in data.lower():
            continue
        for m in _TOKEN_RE.finditer(data):
            tok = m.group(0).decode("ascii")
            if tok not in seen:
                seen.add(tok)
                out.append(tok)
    return out


def token_from_leveldb(validate=True, timeout=15):
    """从浏览器本地存储库拿一个**当前可用**的 token（逐个试探，命中即返回）。"""
    for tok in token_candidates_from_leveldb():
        if not validate:
            return tok
        try:
            req = urllib.request.Request(
                BASE + "/api/GoodsManage/SearchGoodsList",
                data=json.dumps({"keyword": "", "page": 1, "pageSize": 1}).encode("utf-8"),
                headers={"Content-Type": "application/json", "x_front": "1",
                         "X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer " + tok},
                method="POST")
            with _NOPROXY.open(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "ignore").lower()
            if '"issuccess":true' in body or '"issuccess": true' in body:
                return tok
        except urllib.error.HTTPError as e:
            if e.code == 401:
                continue
        except Exception:
            continue
    return None


def _hdrs():
    return {
        "Content-Type": "application/json",
        "x_front": "1",
        "X-Requested-With": "XMLHttpRequest",
        "Authorization": "Bearer " + TOKEN,
    }


def _bridge_alive():
    """桥接 + 扩展 SW 是否真的能干活（探一下 ping，卡死时立刻失败，避免空等）。"""
    try:
        return bool(((_bridge("ping", {}, 8)) or {}).get("ok"))
    except Exception:
        return False


def _refresh_token():
    """token 失效时续期：①经桥接读现有 agiso 页；②新开一页续；
    ③桥接/扩展不可用（SW 卡死）时，降级读 Edge localStorage leveldb 现取。"""
    global TOKEN
    if _bridge_alive():
        for force in (False, True):
            try:
                v = token_from_browser(open_if_missing=True, force_new=force)
            except Exception:
                v = None
            if v and v != TOKEN:
                TOKEN = v
                return True
    try:
        v = token_from_leveldb()
    except Exception:
        v = None
    if v and v != TOKEN:
        TOKEN = v
        return True
    return False


def _ensure_token():
    """首用时若尚无 token，先经桥接取一次（避免拿空 token 白跑一个 401 请求）。"""
    if not TOKEN:
        _refresh_token()


def _post(path, payload, timeout=30, _retry=True):
    _ensure_token()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers=_hdrs(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry and _refresh_token():
            return _post(path, payload, timeout, _retry=False)
        return {"__http": e.code, "__body": e.read().decode("utf-8", "ignore")[:400]}
    except Exception as e:
        return {"__err": type(e).__name__ + ":" + str(e)[:200]}


def _get(path, timeout=30, _retry=True):
    _ensure_token()
    req = urllib.request.Request(BASE + path, headers=_hdrs(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry and _refresh_token():
            return _get(path, timeout, _retry=False)
        return {"__http": e.code, "__body": e.read().decode("utf-8", "ignore")[:400]}
    except Exception as e:
        return {"__err": type(e).__name__ + ":" + str(e)[:200]}


# ---------------- 接口 ----------------
def get_item(gid, draft=False, vg=False):
    return _post("/api/GoodsManage/GetItemInfo",
                 {"goodsId": str(gid), "draft": draft, "virtualGameGoods": vg})

def get_goods_alds(gid):
    return _get(f"/api/AldsInfo/GetGoodsAldsInfo/{gid}")

def get_sku_alds(gid, skid):
    return _get(f"/api/AldsInfo/GetSkuAldsInfo/{gid}/{skid}")


# ---------------- 货源（供货商账号）接口 ----------------
# 🔴 2026-11-09 用户实证：思券（99569）在阿奇索里是**可用**的供货商账号，
#    页面「发货设置 → 货源账号」下拉里能选到、能绑关联商品。
#    之前误判「思券断链」是因为把 GetSupplierProductList 的参数名猜成了
#    supplierAccountId/acprAccountId/... → 后端一律回「货源账号Id不能为空」。
#    **真实参数名是 `idNo`**（供货商账号 ID），keyword 可选过滤。
def get_supplier_accounts():
    """全部供货商账号 [{val: 账号ID, text: 名称}]（思券=99569）。"""
    j = _post("/api/AcprSerivces/GetSupplierAccounts", {})
    return ((j or {}).get("data") or {}).get("data") or []


def get_supplier_products(id_no, keyword="", page_index=1, page_size=100):
    """某供货商账号下的货源商品列表。

    返回 [{productNo, productTitle, productType, productCost, minSalePrice, isAllowPurchase}]。
    · productNo = 该货源平台内部的商品编号（配 SKU 时就是 supplierProductNo）
    · productCost = 供货价（= 思券 goods_price，已实测分毫不差）
    · productType：1=直充 / 2=卡密（与 alds_dict.build_sku_cfg 一致）
      实证 2026-11-12：思券 pno241【官方直充】=1、pno19【官方卡密】=2；
      志远 95425 已配好的官方直充样板商品（喜马拉雅/剪映/夸克等）SKU 配置
      productType 全部为 1、supplierParamJson={"account":"{$充值账号}"}。
      ⚠️ 旧注释写成「1=卡密 / 2=直充」是反的，曾导致 1099580109253
      百度搭子积分被误判为卡密、配成空参数发不出货，已修正。

    ⚠️ 2026-11-09：思券账号 99569 的货源总量大（>100），单页拉不全会漏掉
       中间编号的商品（实测 pno=1176 取不到、1177 能取到）。故默认自动翻页
       直到取空页为止，返回**全量**合并结果。
    """
    out = []
    idx = int(page_index or 1)
    while True:
        body = {"idNo": int(id_no), "pageIndex": idx, "pageSize": int(page_size or 100)}
        if keyword:
            body["keyword"] = keyword
        j = _post("/api/AcprSerivces/GetSupplierProductList", body)
        d = (j or {}).get("data") or {}
        items = ((d.get("data") or {}).get("items")) or []
        out.extend(items)
        # 🔴 2026-11-14 修：带关键词时也必须翻页到空页。
        #    服务端把 pageSize 压成固定 20 条，关键词命中可能跨页
        #    （实测「微博」共 35 条，pno=1425 落在第 2 页），只取第一页会漏商品。
        # 服务端会把 pageSize 压成固定值（实测恒 20），所以不能用 len(items) < pageSize 判断末页；
        # 只能用「本页为空」判断。
        if not items:
            break
        idx += 1
        if idx > 200:          # 兜底，防死循环
            break
    return out


# 🔴 2026-11-13 加：单品可售态缓存（停售前置闸用）。按 (账号, pno) 缓存。
_SUPPLIER_ALLOW_CACHE = {}

def supplier_allowed(id_no, product_no):
    """单品是否可售（isAllowPurchase）。

    用 get_supplier_products(id_no, keyword=product_no) 单页定位（与 find_product 同路，O(1) 网络，
    不翻全量列表以免卡死）。返回：
      · True  → 可售
      · False → 暂停销售（isAllowPurchase 明确为 false/0）
      · None  → 未知（取数失败或字段缺失），保守不阻断
    🔴 用于上架前置闸：避免把停售货源挂上闲鱼，导致买家付款后发不出货。
    """
    key = (int(id_no), str(product_no))
    if key in _SUPPLIER_ALLOW_CACHE:
        return _SUPPLIER_ALLOW_CACHE[key]
    try:
        items = get_supplier_products(int(id_no), keyword=str(product_no))
        for it in (items or []):
            if str(it.get("productNo")) == str(product_no):
                v = it.get("isAllowPurchase")
                if v is None:
                    _SUPPLIER_ALLOW_CACHE[key] = None
                else:
                    _SUPPLIER_ALLOW_CACHE[key] = (v not in (False, 0, "0", "false", "False"))
                return _SUPPLIER_ALLOW_CACHE[key]
    except Exception as _e:
        print("  ⚠️ [supplier_allowed] 取数异常，按未知处理：%s" % str(_e)[:120])
    _SUPPLIER_ALLOW_CACHE[key] = None
    return None


def get_supplier_product(id_no, product_no):
    """单个货源商品详情（含 outApiList / productStandardType 等发货能力标志）。"""
    j = _post("/api/AcprSerivces/GetSupplierDetail",
              {"idNo": int(id_no), "productNo": str(product_no)})
    return ((j or {}).get("data") or {}).get("data") or {}


def get_supplier_common_params(id_no, product_no):
    """货源商品的下单参数模板（直充类要靠它拿「充值账号/链接」等占位符）。"""
    j = _post("/api/AcprSerivces/GetSupplierCommonParamList",
              {"idNo": int(id_no), "productNo": str(product_no)})
    return ((j or {}).get("data") or {}).get("data") or []

def save_sku_alds(cfg):
    return _post("/api/AldsInfo/SaveSkuAldsInfo", cfg)

def save_goods_alds(cfg):
    return _post("/api/AldsInfo/SaveGoodsAldsInfo", cfg)

def add_goods(gids):
    # gids: list[str]
    return _post("/api/AldsInfo/AddGoods", gids)

def open_recharge(gids, types, virtual=True):
    # gids: list[str], types: list[int]
    return _post("/api/GoodsManage/OpenRecharge",
                 {"goodsIds": list(gids), "rechargeAccountTypes": list(types), "virtualGoods": virtual})

def search_goods(keyword="", page=1, size=50):
    return _post("/api/GoodsManage/SearchGoodsList",
                 {"keyword": keyword, "page": page, "pageSize": size})

def save_goods_setting(gid, auto_polish=True, sold_auto=True, interval_days=1, publish_time="00:00"):
    return _post("/api/GoodsManage/SaveGoodsSetting",
                 {"goodsId": str(gid), "autoPolish": auto_polish, "soldAutoPublish": sold_auto,
                  "intervalDays": interval_days, "publishTime": publish_time})

def update_item_status(gid, online=True, virtual_game_goods=False):
    """上架/下架。⚠️ 正确字段是 online（不是 status/onSale），
    旧实现发 {"status":0} 会被后端**静默忽略**（返回 isSuccess 但状态不动）。"""
    return _post("/api/GoodsManage/UpdateItemStatus",
                 {"online": bool(online), "goodsId": str(gid),
                  "virtualGameGoods": bool(virtual_game_goods)})


def edit_item(payload):
    """整体保存商品（改 SKU / 价格 都走这里）。payload = GetItemInfo 的 data.data 改后整体。"""
    return _post("/api/GoodsManage/Edit", payload)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    g = get_goods_alds("1089303794792")
    print(json.dumps(g, ensure_ascii=False)[:2000])
