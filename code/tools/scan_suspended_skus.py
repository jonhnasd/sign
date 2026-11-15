#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""每天上品时扫描在线商品里「货源已暂停销售」的 SKU，自动把其库存置 0。

数据源：上SKU库.json（在线 SKU 权威源）。
可售态：agiso_direct.supplier_allowed(acct, pno)（底层 isAllowPurchase）。

⚠️ 安全设计：
  · token 失效（401）时 supplier_allowed 会静默返回 None（保守放行），本脚本用「健康探针」
    先探一次取数链路；若不可用（401 / issuccess=false / 异常）→ 整体中止，不置0任何 SKU、
    也不谎报「全部正常」。
  · 单条取数失败（None）仅跳过该条，不阻断其他。
  · 置0 用 edit_item 整体保存（与 set_sku_qty.py 同路），回读校验 quantity==0，幂等。

用法：
  python scan_suspended_skus.py --dry            # 只报告，不置0
  python scan_suspended_skus.py --go             # 报告 + 真实置0
  python scan_suspended_skus.py --go --ledger=<路径>

deploy.py 上品主流程在 --go 时自动调用 scan(auto=True)。
"""
import copy
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agiso_direct as A

LEDGER = r"C:/Users/Administrator/Desktop/obisidian/obisidian/上SKU库.json"


def load_token():
    if getattr(A, "TOKEN", None):
        return True
    try:
        A.TOKEN = A.token_from_browser(open_if_missing=False)
        return bool(A.TOKEN)
    except Exception as e:
        print("  ⚠️ 无法加载阿奇索 token：%s" % str(e)[:120])
        return False


def health_probe(acct, pno):
    """返回 (ok, reason)。ok=False 表示取数链路不可用（如 401），应整体中止。

    ⚠️ 不能只看「是否抛异常/是否错误 dict」：401 时 get_supplier_products 常返回**空 list**
    （而非错误体），会让「isAllowPurchase 全部 None」被误判为「全部可售、0 命中」的假绿。
    所以探针要求：对真实存在的 pno 必须**真的命中匹配项**，否则即视为取数失败。
    """
    try:
        items = A.get_supplier_products(int(acct), keyword=str(pno))
    except Exception as e:
        return False, "取数异常: %s" % str(e)[:120]
    if isinstance(items, dict):
        if items.get("__http") in (401, "401"):
            return False, "阿奇索返回 401（token 失效）"
        if items.get("issuccess") is False:
            return False, "接口 issuccess=false: %s" % str(items)[:200]
    if not isinstance(items, list) or len(items) == 0:
        return False, "货源列表为空（token 失效或接口异常）"
    if not any(str(it.get("productNo")) == str(pno) for it in items):
        return False, "未命中探针 pno（取数链路异常）"
    return True, "ok"


def _edit_ok(r):
    return '"issuccess":true' in json.dumps(r, ensure_ascii=False).lower().replace(" ", "")


def set_zero_by_sku_id(gid, sku_id):
    it = A.get_item(str(gid))
    d = (it or {}).get("data") or {}
    item = d.get("data") or d
    skus = item.get("itemSkuList") or []
    if not skus:
        return False, "get_item 无 SKU"
    target = [s for s in skus if str(s.get("skuId")) == str(sku_id)]
    if len(target) != 1:
        return False, "skuId %s 命中 %d 个" % (sku_id, len(target))
    if int(target[0].get("quantity") or 0) == 0:
        return True, "已为0（幂等）"
    payload = copy.deepcopy(item)
    for s in payload["itemSkuList"]:
        if str(s.get("skuId")) == str(sku_id):
            s["quantity"] = 0
    r = A.edit_item(payload)
    if not _edit_ok(r):
        return False, "edit_item 失败: %s" % json.dumps(r, ensure_ascii=False)[:200]
    back = (A.get_item(str(gid)) or {}).get("data") or {}
    back = back.get("data") or back
    for s in (back.get("itemSkuList") or []):
        if str(s.get("skuId")) == str(sku_id):
            return (True, "置0成功") if int(s.get("quantity") or 0) == 0 else (False, "回读仍非0: %s" % s.get("quantity"))
    return False, "回读无该 SKU"


def scan(auto=False, ledger_path=LEDGER):
    if not load_token():
        print("❌ token 缺失，扫描中止")
        return
    ledger = json.load(open(ledger_path, encoding="utf-8"))
    products = ledger.get("products", [])

    # 健康探针：取一个在线商品的 pno 探取数链路
    probe = None
    for p in products:
        if p.get("status") == "在线" and p.get("skus"):
            probe = (p["source_account"], p["skus"][0]["pno"])
            break
    if probe:
        ok, why = health_probe(*probe)
        if not ok:
            print("⚠️ 取数链路不可用（%s），本次扫描中止，未改动任何商品。" % why)
            return

    hits, unknowns = [], []
    for p in products:
        if p.get("status") != "在线":
            continue
        gid, name, acct = p["goods_id"], p["name"], p["source_account"]
        for s in p.get("skus", []):
            pno, sku_id = str(s["pno"]), s.get("sku_id")
            st = A.supplier_allowed(acct, pno)
            if st is False:
                hits.append((gid, name, s.get("label"), pno, sku_id, acct))
            elif st is None:
                unknowns.append((gid, name, s.get("label"), pno))

    print("=== 暂停销售扫描结果 ===")
    print("⛔ 暂停销售命中: %d 个 SKU" % len(hits))
    for h in hits:
        print("   %s | %s | 档位=%s pno=%s skuId=%s" % (h[0], h[1], h[2], h[3], h[4]))
    print("❓ 未知(取数失败/字段缺失，跳过): %d 个" % len(unknowns))
    for u in unknowns:
        print("   %s | %s | 档位=%s pno=%s" % (u[0], u[1], u[2], u[3]))

    if not hits:
        print("✅ 无暂停销售 SKU，无需处理。")
        return
    if not auto:
        print("\n>>> DRY 模式，未置0。加 --go 执行。")
        return

    print("\n--- 执行库存置0 ---")
    for h in hits:
        gid, name, label, pno, sku_id, acct = h
        ok, why = set_zero_by_sku_id(gid, sku_id)
        print("  [%s] %s/%s pno=%s skuId=%s -> %s" % ("✅" if ok else "❌", gid, label, pno, sku_id, why))


def main():
    auto = "--go" in sys.argv
    ledger = LEDGER
    for a in sys.argv[1:]:
        if a.startswith("--ledger="):
            ledger = a.split("=", 1)[1]
    scan(auto=auto, ledger_path=ledger)


if __name__ == "__main__":
    main()
