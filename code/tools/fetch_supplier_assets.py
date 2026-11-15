# -*- coding: utf-8 -*-
"""三家货源「固定素材」通用抓取脚本（只读，不产生资金变动）。

口径（用户 2026-11-13 定）：
  · 固定：货源编号、商品名、商品图、介绍、弹窗/购买须知、详情、充值表单字段
  · 不固定：进价、库存、可售、余额、限价 —— 一律不写入交付物，只在运行时现取
  · 只保留「直充 / 卡密」两类商品
  · 思券清单与详情优先复用历史全量快照（2026-11-04 已抓 1123 全量 + 1081 详情），
    不再全量重抓；只对「实时清单有、快照没有」的差集增量补抓。

用法：
  python fetch_supplier_assets.py --out <目录> [--candidate-csv X] [--skip-list]
    --siquan-snapshot P  思券详情快照 JSON（默认自动取最新 sqqy88商品详情原始-*.json）
    --siquan-full P      思券阿奇索侧全量 JSON（默认 货源_思券全量.json）
    --no-fetch-missing   连差集也不补抓，纯离线复用
    --skip-detail        只出清单、接口表和索引，不生成详情素材

输出（均在 --out 下）：
  货源商品清单.json   三家全量直充/卡密商品，只有固定字段
  货源素材_详情.json  介绍 / 弹窗 / 详情 / 图集 / 充值表单
  货源接口网址.json   三家接口清单（不含凭据）
  ../项目-三家货源固定素材库.md   Obsidian 入口笔记
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 🔴 2026-11-15：TOOLS 用自身位置推导（换盘符/换用户名都不影响）；
#    DOC 走 paths.py 的 kuaipao_gen 父目录，不再写死 `Desktop\workbuddy\文档提取`。
TOOLS = Path(__file__).resolve().parent
try:
    from paths import CFG as _CFG
except Exception:
    _CFG = None
DOC = Path((_CFG.kuaipao_gen if _CFG else None) or
           r"C:\Users\Administrator\Desktop\workbuddy\文档提取\_yq_poster\kuaipao_gen.py").parent.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(DOC))
os.environ.setdefault("SQQY_IFACE", "")  # 2026-11-13 实测：默认路由即可，无需绑定 WiFi 网卡

# 思券历史全量（用户 2026-11-13 指出：之前已抓过，直接复用，不再全量重抓）
SIQUAN_FULL = DOC / "货源_思券全量.json"          # 阿奇索侧 1123 条
SIQUAN_DETAIL_GLOB = "sqqy88商品详情原始-*.json"  # 自有站 1081 条详情全量

# 三家类型码 → 统一形态。只保留这两类，其余（实物/其他）排除。
FORM = {
    "志远": {1: "卡密", 3: "直充"},
    "商战": {1: "卡密", 2: "直充"},
    "思券": {1: "卡密", 2: "直充"},
}

# 接口网址（只记路径与用途，凭据一律不写进笔记/交付物）
ENDPOINTS = [
    {"source": "志远", "acct": 95425, "host": "https://zy.kkam.cn",
     "proto": "v3 / POST JSON / 头 X-APP-ID, X-Version, X-Timestamp, X-Signature",
     "sign": "md5(app_id + secret + version + ts + body_json)",
     "endpoints": [
         {"name": "商品列表", "url": "/api/v3/goods/getList", "body": '{"keyword":"","page":1,"pageSize":100}',
          "note": "分页，读 data.allPage；goodsId = pno"},
         {"name": "商品详情", "url": "/api/v3/goods/getDetail", "body": '{"goodsId":1220}',
          "note": "imgUrl 商品图 / goodsDescribe 简介 / goodsDetail 详情HTML / buyNotice 购买须知(弹窗) / rechargeTemplates 充值表单(弹窗字段)"},
         {"name": "账户余额", "url": "/api/v3/user/getAccount", "body": "{}", "note": "易变字段，按需现取"},
     ],
     "form_field": "goodsType：1=卡密 / 3=直充"},
    {"source": "商战", "acct": 96810, "host": "https://www.qqkami.com",
     "proto": "开放 API / POST 表单 / customerid + sign / 证书链需 CERT_NONE",
     "sign": "表单字段 sign（接口秘钥）",
     "endpoints": [
         {"name": "全量商品列表", "url": "/api.php/Client/goodsList", "body": "customerid, sign",
          "note": "限 300 秒 1 次；客户端有 _qqkami_catalog.json 本地缓存"},
         {"name": "商品详情", "url": "/api.php/Client/goodsInfo", "body": "id, customerid, sign",
          "note": "限 1 秒 1 次；img 商品图 / info 介绍HTML / notice 购买须知(弹窗) / template 充值表单(弹窗字段) / recharge_url"},
         {"name": "批量指定商品", "url": "/api.php/Client/designatedProductList", "body": "id(逗号分隔)",
          "note": "限 3 秒 1 次"},
         {"name": "商家信息/余额", "url": "/api.php/Client/getCustomerInfo", "body": "customerid, sign",
          "note": "易变字段，按需现取"},
     ],
     "form_field": "type：1=卡密 / 2=直充"},
    {"source": "思券", "acct": 99569, "host": "http://88.sqqy88.cn",
     "proto": "CRMEB H5 (/front/diy/*) + uni-app (/uni/*) 双前端，各自独立签名",
     "sign": 'H5: md5(md5(md5("front"+KEY)+ts))+ts ; uni: md5(md5(md5("h5"+KEY)+ts))+ts',
     "endpoints": [
         {"name": "商品列表(全量)", "url": "/front/diy/goods/index",
          "body": '{"cid":"","page":1,"limit":20}',
          "note": "cid 必须为空才是全量；limit 不起作用，一次返回全部"},
         {"name": "分类树", "url": "/front/diy/category/index", "body": "{}", "note": "—"},
         {"name": "商品详情", "url": "/uni/categoods", "body": '{"id":"1181","sku_id":""}',
          "note": "需 Authorization: Bearer <JWT>；goods_img/goods_imgs 图 / goods_info 介绍HTML / goods_notice 购买须知(弹窗) / attach 充值表单(弹窗字段) / recharge_url / demo_url"},
         {"name": "实际券后价", "url": "/uni/goods/get_goods_price", "body": '{"quantity":1,"goods_id":1181}',
          "note": "易变字段，按需现取"},
     ],
     "form_field": "goods_type：1=卡密 / 2=虚拟(直充)"},
]


def _dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print("  写出 %s (%d 字节)" % (path.name, path.stat().st_size))


def fetch_zhiyuan():
    import v3_huafei as v
    p = v.PLATFORMS["卡密 zy.kkam"]
    out, page, all_page = [], 1, 1
    while page <= all_page:
        r = v.call_v3(p, "/goods/getList", {"keyword": "", "page": page, "pageSize": 100})
        d = r.get("data") or {}
        items = d.get("items") or d.get("list") or []
        all_page = int(d.get("allPage") or 1)
        for g in items:
            form = FORM["志远"].get(int(g.get("goodsType") or 0))
            if not form:
                continue
            out.append({"source": "志远", "acct": 95425, "pno": str(g.get("goodsId")),
                        "name": g.get("name") or "", "form": form,
                        "img": g.get("imgUrl") or ""})
        if page % 20 == 0:
            print("  志远 %d/%d 页, 已收 %d" % (page, all_page, len(out)))
        page += 1
    return out


def fetch_shangzhan():
    import qqkami as q
    cat = q.catalog()
    out = []
    for g in cat or []:
        form = FORM["商战"].get(int(g.get("type") or 0))
        if not form:
            continue
        img = g.get("img") or ""
        if img.startswith("//"):
            img = "https:" + img
        out.append({"source": "商战", "acct": 96810, "pno": str(g.get("id")),
                    "name": g.get("name") or "", "form": form, "img": img})
    return out


def fetch_siquan():
    import sqqy88_fetch as F
    r = F.get_goods()
    items = r.get("data") or []
    if not isinstance(items, list):
        items = items.get("list") or []
    out = []
    for g in items:
        form = FORM["思券"].get(int(g.get("goods_type") or 0))
        if not form:
            continue
        out.append({"source": "思券", "acct": 99569, "pno": str(g.get("id")),
                    "name": g.get("goods_name") or "", "form": form,
                    "img": g.get("goods_img") or ""})
    return out


# ---------------------------------------------------------------- 思券历史快照复用
def load_siquan_full(path=None):
    """阿奇索侧 1123 条思券全量，只取固定字段，零网络请求。"""
    p = Path(path) if path else SIQUAN_FULL
    if not p.exists():
        print("  思券历史全量缺失: %s" % p)
        return []
    rows = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for g in rows:
        form = FORM["思券"].get(int(g.get("goods_type") or 0))
        if not form:
            continue
        out.append({"source": "思券", "acct": 99569, "pno": str(g.get("id")),
                    "name": g.get("goods_name") or "", "form": form,
                    "img": g.get("goods_img") or "",
                    "_origin": "阿奇索侧全量快照"})
    return out


def latest_siquan_snapshot(explicit=""):
    if explicit:
        return Path(explicit)
    found = sorted(DOC.glob(SIQUAN_DETAIL_GLOB))
    return found[-1] if found else None


def load_siquan_assets(snap_path):
    """把 2026-11-04 已抓好的思券详情全量转成统一素材格式，零网络请求。"""
    if not snap_path or not Path(snap_path).exists():
        return []
    p = Path(snap_path)
    rows = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        g = r.get("goods") or {}
        if not g:
            continue
        form = FORM["思券"].get(int(g.get("goods_type") or 0))
        if not form:
            continue
        imgs = g.get("goods_imgs") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        out.append({"source": "思券", "pno": str(g.get("id") or r.get("id")),
                    "name": g.get("goods_name") or "", "form": form,
                    "img": g.get("goods_img") or "",
                    "imgs": ["http://88.sqqy88.cn" + u if str(u).startswith("/") else u for u in imgs],
                    "intro_html": g.get("goods_info") or "",
                    "notice_html": g.get("goods_notice") or "",
                    "popup_fields": g.get("attach") or [],
                    "card_option": g.get("card_option") or [],
                    "recharge_url": g.get("recharge_url") or "",
                    "demo_url": g.get("demo_url") or "",
                    "_origin": "本地历史详情快照 " + p.name})
    return out


def siquan_catalog(out_dir, full_path=None):
    """思券清单 = 阿奇索侧 1123 全量 + 实时目录新增 pno，按 pno 合并去重（不重抓详情）。"""
    merged = {x["pno"]: x for x in load_siquan_full(full_path)}
    f = Path(out_dir) / "货源商品清单.json"
    if f.exists():
        for x in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            if x.get("source") != "思券":
                continue
            cur = merged.get(x["pno"])
            if cur:
                for k in ("name", "img", "form"):
                    if not cur.get(k) and x.get(k):
                        cur[k] = x[k]
            else:
                merged[x["pno"]] = x
    return list(merged.values())


def siquan_live_catalog(out_dir, force=False):
    """自有站实时目录 pno 集合：一次请求 + 本地缓存，用于发现新编号和判定差集。

    清单文件里含阿奇索侧独有的 pno（自有站没有详情），不能用它判差集，
    否则会把 43 个抓不到的商品也当成「待补抓」。
    """
    cache = Path(out_dir) / "思券实时目录.json"
    if cache.exists() and not force:
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            items = d.get("items") or []
            return {str(x["pno"]): x for x in items}, d.get("时间", "")
        except Exception:
            pass
    try:
        items = fetch_siquan()
    except Exception as e:
        print("  思券实时目录失败，保留历史全量: %s" % str(e)[:120])
        return {}, ""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    _dump(cache, {"时间": stamp,
                  "说明": "自有站实时目录，仅用于发现新编号与判定详情差集；不含价格库存",
                  "合计": len(items), "items": items})
    return {x["pno"]: x for x in items}, stamp


def siquan_detail(one):
    import sqqy88_fetch as F
    r = F.get_goods_detail(one["pno"])
    g = ((r.get("data") or {}).get("goods") or {})
    if not g:
        return {"source": "思券", "pno": one["pno"], "name": one["name"],
                "_err": r.get("msg") or r.get("_error") or "empty"}
    imgs = g.get("goods_imgs") or []
    if isinstance(imgs, str):
        imgs = [imgs]
    return {"source": "思券", "pno": one["pno"], "name": one["name"], "form": one["form"],
            "img": g.get("goods_img") or one.get("img") or "",
            "imgs": ["http://88.sqqy88.cn" + u if str(u).startswith("/") else u for u in imgs],
            "intro_html": g.get("goods_info") or "", "notice_html": g.get("goods_notice") or "",
            "popup_fields": g.get("attach") or [], "card_option": g.get("card_option") or [],
            "recharge_url": g.get("recharge_url") or "", "demo_url": g.get("demo_url") or "",
            "detail_fields": 51}


def zhiyuan_detail(one):
    import v3_huafei as v
    p = v.PLATFORMS["卡密 zy.kkam"]
    r = v.detail(p, int(one["pno"]))
    d = r.get("data") or {}
    if not d:
        return {"source": "志远", "pno": one["pno"], "name": one["name"], "_err": str(r.get("info") or "empty")[:120]}
    return {"source": "志远", "pno": one["pno"], "name": one["name"], "form": one["form"],
            "img": d.get("imgUrl") or one.get("img") or "",
            "intro_html": d.get("goodsDetail") or "", "short_desc": d.get("goodsDescribe") or "",
            "notice_html": d.get("buyNotice") or "", "popup_fields": d.get("rechargeTemplates") or [],
            "sku": d.get("goodsSku") or [], "spec": d.get("goodsSpec") or []}


def shangzhan_detail(one):
    import qqkami as q
    r = q.raw_goods_info(one["pno"])
    d = r.get("data") or {}
    if not d:
        return {"source": "商战", "pno": one["pno"], "name": one["name"], "_err": str(r.get("info") or "empty")[:120]}
    img = d.get("img") or ""
    if img.startswith("//"):
        img = "https:" + img
    return {"source": "商战", "pno": one["pno"], "name": one["name"], "form": one["form"],
            "img": img or one.get("img") or "", "intro_html": d.get("info") or "",
            "notice_html": d.get("notice") or "", "popup_fields": d.get("template") or "",
            "recharge_url": d.get("recharge_url") or ""}


def load_candidates(csv_path):
    """从 0-20元可上SKU_全量.csv 读候选 (来源关键字, 商品ID)，只用于限定详情抓取范围。"""
    import csv
    keys = set()
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            src = (row.get("来源") or "").strip()
            pno = (row.get("商品ID") or "").strip()
            if not src or not pno:
                continue
            label = "商战" if "商战" in src else ("志远" if "志远" in src else ("思券" if "思券" in src else ""))
            if label:
                keys.add((label, pno))
    return keys


def write_index_note(out, st):
    """在 Obsidian 库根生成可读入口笔记（符合《操作层规范》四要素）。"""
    p = out.parent / "项目-三家货源固定素材库.md"
    L = []
    a = L.append
    a("---")
    a("created: 2026-11-13")
    a("updated: " + st["date"])
    a("tags: [货源, 素材库, 选品]")
    a("type: 项目")
    a("status: active")
    a("---")
    a("")
    a("# 项目-三家货源固定素材库")
    a("")
    a("## 🚀 快速开始")
    a("")
    a("> [!note] 一句话")
    a("> 抓素材用 `fetch_supplier_assets.py`（复用历史全量 + 增量补抓），**查素材一律用 `query_supplier_assets.py`**；两个 JSON 共 17 万行，禁止直接 Read。")
    a("")
    a("### 前置条件")
    a("- 三家接口可访问；思券已有 2026-11-04 全量快照，默认**不重抓、不用手机、不用绑网卡**")
    a("- 凭据走 sops / 环境变量，不写进笔记或任何交付物")
    a("- 输出目录固定为 `货源素材/`；本笔记与四个 JSON 同在 Obsidian 库内")
    a("")
    a("### 一键入口")
    a("```bash")
    _out_dir = (_CFG.assets_dir if _CFG else None) or \
        Path.home() / "Desktop" / "obisidian" / "obisidian" / "货源素材"
    a('python "%s" --out "%s" --skip-list' % (
        (TOOLS / "fetch_supplier_assets.py").as_posix(), Path(_out_dir).as_posix()))
    a("```")
    a("")
    a("### 预期输出")
    a("```")
    a("✓ 四个 JSON 时间戳更新；控制台出现「思券复用历史详情快照 N 条（零网络请求）」")
    a("✓ 清单只含直充/卡密；详情素材含图集、介绍、购买须知、充值表单")
    a("✗ 某家清单为 0 条 → 检查网络/token，保留上次结果，不用空数据覆盖")
    a("```")
    a("")
    a("### 完整步骤")
    a("1. 清单 `货源商品清单.json`：一行一个「来源#pno」，只存固定字段。")
    a("2. 素材 `货源素材_详情.json`：按 pno 索引图片、介绍、弹窗、详情。")
    a("3. 接口 `货源接口网址.json`；`思券实时目录.json` 是实时 pno 缓存，仅用于发现新编号 / 判详情差集。")
    a("4. 每日推荐读清单找候选；价格、库存、可售一律现场取，不读表内数值。")
    a("")
    a("---")
    a("")
    a("## 一、本次入库规模")
    a("")
    a("| 来源 | 清单条数 | 说明 |")
    a("|---|---:|---|")
    for label in ("志远", "商战", "思券"):
        note = "复用 %s（1123 全量）+ 实时目录差集" % st["full"] if label == "思券" else "目录接口全量，只留直充/卡密"
        a("| %s | %d | %s |" % (label, st["by_source"].get(label, 0), note))
    a("| **合计** | **%d** | 生成于 %s |" % (st["list_total"], st["date"]))
    a("")
    a("- 思券详情快照 `%s`：复用 **%d** 条，零网络请求" % (st["snapshot"], st["siquan_reused"]))
    a("- 思券自有站实时目录：**%d** 个 pno（缓存，只用于 diff）" % st["siquan_live"])
    a("- 思券差集增量补抓：**%d** 条；仅在阿奇索侧可见、自有站无详情：**%d** 条（清单保留，素材标待补）" % (st["siquan_missing"], st["no_detail"]))
    a("- 当前详情素材合计：**%d** 条" % st["assets_total"])
    a("")
    a("## 二、固定 / 易变分层（用户 2026-11-13 定）")
    a("")
    a("| 固定，长期存库 | 易变，每次现场取，绝不落表 |")
    a("|---|---|")
    a("| 来源#pno、商品名、形态、品牌/产品线 | 当日进价 / 供货价 / 限价 |")
    a("| 商品图、图集、参考图路径 | 库存、可售、停售 |")
    a("| 商品介绍 HTML、购买须知（弹窗） | 余额、起购区间 |")
    a("| 充值表单字段、详情原文 | 真实成本与充值参数（下单前 GetDetail 核） |")
    a("| 跨源同款关系、人工备注、已上架台账 | — |")
    a("")
    a("> ⚠️ 表格里的「建议售价 / 单净利」是源池挂牌价，不是 6.6% 执行价；排序一律用 `进价 ÷ 0.934` 重算。")
    a("")
    a("## 三、接口网址（不含凭据）")
    a("")
    a("| 来源 | 接口 | 名称 | 用途 / 关键字段 |")
    a("|---|---|---|---|")
    for src in ENDPOINTS:
        for e in src["endpoints"]:
            a("| %s | `%s%s` | %s | %s |" % (src["source"], src["host"], e["url"], e["name"], e["note"]))
    a("")
    a("签名与协议见 `货源接口网址.json` 的 `proto` / `sign` 字段；凭据一律不入库。")
    a("")
    a("## 三·补、弹窗字段在哪（三家口径不同）")
    a("")
    a("| 来源 | 介绍 / 详情 | 购买须知（弹窗） | 充值表单（弹窗字段） |")
    a("|---|---|---|---|")
    a("| 志远 | `goodsDetail` | `buyNotice`（多数为空） | `rechargeTemplates` |")
    a("| 商战 | `info` | `notice`（多数为空） | `template`（候选池全覆盖） |")
    a("| 思券 | `goods_info` | `goods_notice` | `attach` |")
    a("")
    a("> 志远/商战的「购买须知」原字段多为空，弹窗内容主要落在充值表单字段里，不是漏抓。")
    a("")
    a("## 四、买家文案红线")
    a("")
    a("- 货源编号、货源网站名称、供应商名称、域名**不得**出现在标题、描述、SKU 使用说明、主图中。")
    a("- 素材入库是内部原文，不是可直接发布的买家文案；套模板前须过 `sanitize_buyer_copy()`，写回前二次清洗，`onepipe_guard.py` 巡检。")
    a("- 商品图保留品牌 Logo，去水印与平台标识；主图按「复刻参考图、定点替换文字」生成。")
    a("")
    a("## 五、维护约定")
    a("")
    a("- 思券已有全量（1123 清单 + 1081 详情），**不要重跑全量详情抓取**；只跑差集。")
    a("- 新编号靠实时目录 diff 发现；取数失败就保留上次结果并标「数据已过期」。")
    a("- 本脚本是通用入口（`--out` / `--candidate-csv` / `--siquan-snapshot` / `--merge`），同类需求不再写一次性脚本。")
    a("")
    a("## 六、查询方式（AI 不要直接读 JSON）")
    a("")
    a("> [!warning] 清单 12.5 万行、详情 4.7 万行，`Read` 会在 2000 行处截断。")
    a("> 查任何商品一律走 `query_supplier_assets.py`；速查表 [[AI速查表]]（`货源素材/AI速查表.md`）只有 44 行，可整份读进上下文。")
    a("> 两个 JSON 与 [[AI速查表]] 均由本脚本每次入库后**自动写回 Obsidian**，无需手工维护。")
    a("")
    a("```bash")
    a('PY="%s"' % Path(sys.executable).as_posix())
    a('Q="%s"' % (TOOLS / "query_supplier_assets.py").as_posix())
    a('"$PY" "$Q" --pno 1220                        # 精确查（跨三家）')
    a('"$PY" "$Q" --keyword 剪映 --source 志远 --limit 10')
    a('"$PY" "$Q" --pno 1220 --show intro --chars 600')
    a('"$PY" "$Q" --stats                           # 统计与覆盖率')
    a('"$PY" "$Q" --write-digest                   # 重建 AI 速查表')
    a("```")
    a("")
    a("- 默认只输出 20 行、约 2 KB，单次约 120 ms；`素材` 短码 G 主图 / I 图集 / T 介绍 / N 购买须知 / F 充值表单。")
    a("- 本地查的是固定字段；进价、库存、可售、余额、限价仍须上架时现场取，本库不提供。")
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("  写出 %s (%d 字节)" % (p.name, p.stat().st_size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--detail-limit", type=int, default=0,
                    help="无候选表时，志远/商战详情抓取上限；0=不抓")
    ap.add_argument("--candidate-csv", default="", help="候选池 CSV，只抓这些 pno 的详情")
    ap.add_argument("--workers", type=int, default=8, help="详情并发数（商战强制 1，接口限 1 秒 1 次）")
    ap.add_argument("--merge", action="store_true", help="与已有 货源素材_详情.json 合并去重")
    ap.add_argument("--skip-list", action="store_true", help="跳过志远/商战列表抓取，复用已有清单")
    ap.add_argument("--skip-detail", action="store_true")
    ap.add_argument("--siquan-snapshot", default="", help="思券详情历史快照，默认取最新")
    ap.add_argument("--siquan-full", default="", help="思券阿奇索侧全量，默认 货源_思券全量.json")
    ap.add_argument("--no-fetch-missing", action="store_true", help="连差集也不补抓，纯离线复用")
    ap.add_argument("--refresh-siquan-live", action="store_true",
                    help="强制重取一次思券实时目录（默认读缓存，仍不重抓详情）")
    ap.add_argument("--no-digest", action="store_true",
                    help="不自动重建 货源素材/AI速查表.md（默认每次入库后自动写回 Obsidian）")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cand = load_candidates(args.candidate_csv) if args.candidate_csv else set()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # ---- 1/4 清单：志远/商战实时目录；思券复用历史全量，不重抓 ----
    list_file = out / "货源商品清单.json"
    if args.skip_list and list_file.exists():
        old = json.loads(list_file.read_text(encoding="utf-8"))["items"]
        other = [x for x in old if x["source"] != "思券"]
        print("== 1/4 复用已有清单 %d 条；思券改用历史全量合并 ==" % len(old))
    else:
        print("== 1/4 拉志远/商战清单（思券复用历史全量，不重抓）==")
        other = []
        for label, fn in [("志远", fetch_zhiyuan), ("商战", fetch_shangzhan)]:
            try:
                got = fn()
                print("  %s: %d 条" % (label, len(got)))
                other.extend(got)
            except Exception as e:
                print("  %s 失败: %s: %s" % (label, type(e).__name__, str(e)[:160]))
    sq_items = siquan_catalog(out, args.siquan_full)
    live_map, live_time = siquan_live_catalog(out, force=args.refresh_siquan_live)
    sq_live = set(live_map)
    known = {x["pno"] for x in sq_items}
    for pno in sq_live - known:           # 历史全量里没有、实时目录新出现的 pno
        sq_items.append(live_map[pno])
    print("  思券实时目录 %d 条（%s，仅用于 diff，不抓详情）" % (len(sq_live), live_time or "缓存"))
    all_items = other + sq_items
    print("  思券: %d 条（历史全量 + 实时目录差集合并）" % len(sq_items))
    _dump(list_file,
          {"抓取时间": now,
           "口径": "仅固定字段（编号/名称/形态/商品图）；进价、库存、可售等易变字段一律不入库",
           "思券口径": "复用 货源_思券全量.json 与 sqqy88商品详情原始-*.json 历史快照，不重抓全量",
           "合计": len(all_items), "items": all_items})

    # ---- 2/4 接口网址 ----
    print("== 2/4 写接口网址 ==")
    _dump(out / "货源接口网址.json",
          {"说明": "只记 host / 路径 / 参数用途，凭据不写进笔记或交付物", "sources": ENDPOINTS})

    # ---- 3/4 详情素材：思券优先复用历史快照 ----
    print("== 3/4 详情素材（思券复用历史全量，只对差集增量补抓）==")
    asset_file = out / "货源素材_详情.json"
    assets, seen = [], set()
    if args.merge and asset_file.exists():
        for a in json.loads(asset_file.read_text(encoding="utf-8")).get("items", []):
            k = (a.get("source"), a.get("pno"))
            if k not in seen and not a.get("_err"):
                seen.add(k)
                assets.append(a)
        print("  合并已有素材 %d 条" % len(assets))

    snap = latest_siquan_snapshot(args.siquan_snapshot)
    reused = load_siquan_assets(snap)
    if reused:
        idx = {(a.get("source"), a.get("pno")): i for i, a in enumerate(assets)}
        for a in reused:
            k = (a["source"], a["pno"])
            if k in idx:
                assets[idx[k]] = a
            else:
                idx[k] = len(assets)
                assets.append(a)
            seen.add(k)
    print("  思券复用历史详情快照 %s：%d 条（零网络请求）" %
          (snap.name if snap else "无", len(reused)))

    missing = [x for x in all_items
               if x["source"] == "思券" and ("思券", x["pno"]) not in seen and x["pno"] in sq_live]
    if not args.skip_detail and not args.no_fetch_missing and missing:
        print("  思券差集补抓 %d 个 ..." % len(missing))
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for fu in as_completed([ex.submit(siquan_detail, x) for x in missing]):
                r = fu.result()
                assets.append(r)
                if not r.get("_err"):
                    seen.add(("思券", r["pno"]))
    else:
        print("  思券差集 %d 个，本次不补抓" % len(missing))

    if not args.skip_detail:
        def pick(label):
            pool = [x for x in all_items if x["source"] == label]
            if cand:
                pool = [x for x in pool if (label, x["pno"]) in cand]
            elif args.detail_limit > 0:
                pool = pool[:args.detail_limit]
            else:
                pool = []
            return [x for x in pool if (label, x["pno"]) not in seen]

        def run_parallel(label, fn, subset, workers):
            if not subset:
                return
            print("  %s 详情 %d 个，并发 %d ..." % (label, len(subset), workers))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                for fu in as_completed([ex.submit(fn, x) for x in subset]):
                    assets.append(fu.result())

        run_parallel("志远", zhiyuan_detail, pick("志远"), args.workers)
        sz = pick("商战")
        if sz:
            print("  商战详情 %d 个（1 秒 1 次，串行）..." % len(sz))
            for i, x in enumerate(sz, 1):
                assets.append(shangzhan_detail(x))
                if i % 50 == 0:
                    print("    %d/%d" % (i, len(sz)))
        if not cand and args.detail_limit <= 0:
            print("  提示：志远/商战详情未指定候选表或上限，接口与字段映射已记录")

    _dump(asset_file,
          {"抓取时间": now,
           "字段说明": "intro_html=介绍/详情HTML, notice_html=弹窗购买须知, popup_fields=弹窗充值表单字段, imgs=图集",
           "思券口径": "主体复用本地历史详情快照，仅差集走网络",
           "合计": len(assets), "items": assets})

    # ---- 4/4 Obsidian 入口笔记 + AI 速查表（每次入库自动写回，避免统计过期）----
    print("== 4/4 写 Obsidian 索引 + 速查表 ==")
    by_source = {}
    for x in all_items:
        by_source[x["source"]] = by_source.get(x["source"], 0) + 1
    write_index_note(out, {
        "date": now[:10], "list_total": len(all_items), "by_source": by_source,
        "assets_total": len([a for a in assets if not a.get("_err")]),
        "siquan_reused": len(reused), "siquan_missing": len(missing),
        "siquan_live": len(sq_live),
        "no_detail": len([x for x in all_items
                          if x["source"] == "思券" and ("思券", x["pno"]) not in seen]),
        "snapshot": snap.name if snap else "无",
        "full": (Path(args.siquan_full).name if args.siquan_full else SIQUAN_FULL.name),
    })

    # 速查表是 Obsidian 内可被 AI 整读的小文件；每次素材入库后自动重建，
    # 保证「清单条数 / 覆盖率 / 数据时间」与四个 JSON 始终一致。
    if not args.no_digest:
        try:
            import subprocess
            q = Path(__file__).with_name("query_supplier_assets.py")
            r = subprocess.run([sys.executable, str(q), "--dir", str(out), "--write-digest"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60)
            msg = (r.stdout or "").strip() or (r.stderr or "").strip()[:160]
            print("  AI速查表: %s" % (msg or "无输出"))
        except Exception as e:
            print("  AI速查表重建失败（不影响入库）: %s: %s" % (type(e).__name__, str(e)[:120]))
    print("完成。")


if __name__ == "__main__":
    main()
