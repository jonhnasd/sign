# -*- coding: utf-8 -*-
"""阿奇索全店体检 v2（只读，不改任何配置）+ 自愈前置。

三类检查：
  ① 配置     商品级 sendTypeOption/提取/spType/autoSend/登记 + SKU级 spType/acc/pno/param/库存
  ② 货源可用性 每个 pno 在货源侧是否存在 / 限购区间是否覆盖 multiple / 参数类型是否与已配一致
  ③ 价格规则  引流款 <5元硬下限 / 售价低于进价(亏本)

自愈前置 ensure_ready()：桥接不在→后台拉起；token 失效→经桥接续期/开新标签页。

用法:
  python agiso_audit.py                # 全店体检（含货源检查）
  python agiso_audit.py <goodsId>      # 单商品
  python agiso_audit.py --no-source    # 跳过货源侧检查（快）
输出: agiso_audit_report.json
"""
import sys, os, json, time, subprocess
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agiso_direct as A
import alds_dict as D

SP = D.SP_TYPE
NODE = "C:/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
EDGE_BRIDGE = os.path.abspath(os.path.join(HERE, ".."))

_src_cache = {}


def _src_check(pno, acct):
    """返回 (detail|None, err|None)。err 非空=无法校验（接口异常/平台无接口），非『不存在』。"""
    key = (str(pno), int(acct))
    if key not in _src_cache:
        try:
            raw = D.detail_raw(pno, acct)
        except Exception as e:
            raw = {"code": -1, "msg": str(e)[:80]}
        if not raw:
            _src_cache[key] = (None, "平台无接口")
        elif raw.get("code") != 1000:
            _src_cache[key] = (None, "接口异常(code=%s %s)" % (raw.get("code"), raw.get("msg")))
        else:
            det = raw.get("data")
            _src_cache[key] = (det, None if det else "pno 在货源侧不存在")
    return _src_cache[key]


# ---------- 自愈 ----------
def ensure_ready():
    """确保桥接在线 + token 可用；返回 dict 供报告。"""
    st = {"bridge": False, "token": False, "healed": []}
    import urllib.request
    def alive():
        try:
            with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=4) as r:
                return json.loads(r.read().decode())
        except Exception:
            return None
    h = alive()
    if not h or not h.get("ok"):
        try:
            subprocess.Popen([NODE, "server.mjs"], cwd=EDGE_BRIDGE,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            st["healed"].append("拉起 edge-bridge")
            time.sleep(4)
            h = alive()
        except Exception as e:
            st["heal_err"] = str(e)[:120]
    st["bridge"] = bool(h and h.get("ok"))
    # token：直接调一次接口，401/失败则续期
    r = A.search_goods("", 1, 1)
    if isinstance(r, dict) and r.get("__http") == 401:
        if A._refresh_token():
            st["healed"].append("token 续期")
            r = A.search_goods("", 1, 1)
    st["token"] = bool(isinstance(r, dict) and ((r.get("data") or {}).get("data") or {}).get("items") is not None)
    if st["bridge"] and not st["token"]:
        # 页面网络坏 → 开新标签页让 SPA 续期
        try:
            A._bridge("tab_new", {"url": "https://aldsidle.agiso.com/#/goodsManage/goodsList"}, 30)
            time.sleep(7)
            if A._refresh_token():
                st["healed"].append("开新标签页续 token")
                st["token"] = True
        except Exception:
            pass
    return st


# ---------- 单商品体检 ----------
def audit_goods(gid, row=None, with_source=True, verbose=True):
    """返回真问题 list[str]；顺带打印。"""
    gid = str(gid)
    g = (A.get_goods_alds(gid).get("data") or {}).get("data") or {}
    d = (A.get_item(gid).get("data") or {}).get("data") or {}
    sl = d.get("itemSkuList") or []
    name = str(d.get("title") or d.get("goodsName") or "")[:34]
    setting = (row or {}).get("setting") if isinstance((row or {}).get("setting"), dict) else {}
    conf_types = setting.get("rechargeAccountTypes")
    issues, warns = [], []

    # ① 商品级
    if g.get("sendTypeOption") != 28:
        issues.append("商品级 sendTypeOption=%s(应28)" % g.get("sendTypeOption"))
    if g.get("enableSendByTiqu") is not True:
        issues.append("商品级 提取未开")
    if g.get("autoSend") is not True:
        issues.append("商品级 autoSend=%s" % g.get("autoSend"))
    if g.get("spType") != 6:
        (warns if g.get("defineSku") is True else issues).append(
            "商品级 spType=%s(%s)" % (g.get("spType"), SP.get(g.get("spType"))))
    if (g.get("idNo") or 0) == 0 and (g.get("defineSku") is True):
        issues.append("商品级 未登记(idNo=0)")

    # ① SKU 级 + ② 货源 + ③ 价格
    for s in sl:
        sid = str(s.get("skuId") or s.get("id"))
        sd = (A.get_sku_alds(gid, sid).get("data") or {}).get("data") or {}
        val = (s.get("propertyList") or [{}])[0].get("valueText") or sid
        price = s.get("price")
        if sd.get("spType") != 6:
            issues.append("SKU %s(%s) spType=%s(%s)" % (sid, val, sd.get("spType"), SP.get(sd.get("spType"))))
        if not sd.get("supplierAccountId"):
            issues.append("SKU %s(%s) 无货源(acc=0)" % (sid, val))
        if str(sd.get("supplierProductNo") or "0") in ("", "0", "None"):
            issues.append("SKU %s(%s) 无货源编号" % (sid, val))
        if sd.get("sendTypeOption") != 28 or sd.get("enableSendByTiqu") is not True:
            issues.append("SKU %s(%s) 提取/发货方式异常" % (sid, val))
        if not sd.get("autoSend"):
            issues.append("SKU %s(%s) autoSend未开" % (sid, val))
        if s.get("quantity") in (0, None):
            issues.append("SKU %s(%s) 库存=0" % (sid, val))
        if sd.get("productType") == 1 and not sd.get("supplierParamJson"):
            issues.append("SKU %s(%s) 直充缺参数" % (sid, val))

        # ② 货源可用性（仅在货源平台可自动校验时）
        pno = sd.get("supplierProductNo"); acct = sd.get("supplierAccountId")
        if with_source and pno and acct:
            if int(acct) not in D.VERIFIABLE_ACCTS:
                warns.append("SKU %s(%s) 货源平台 %s 无 v3 接口，跳过自动校验"
                             % (sid, val, D.ACCT_PLATFORM.get(int(acct), acct)))
            else:
                det, err = _src_check(pno, acct)
                if err:
                    warns.append("SKU %s(%s) 货源校验跳过：%s（pno=%s %s）"
                                 % (sid, val, err, pno, D.ACCT_PLATFORM.get(int(acct))))
                else:
                    try:
                        mn, mx = det.get("minQuantity"), det.get("maxQuantity")
                        mult = sd.get("multiple")
                        if mn is not None and mx is not None and mult is not None:
                            if not (float(mn) <= float(mult) <= float(mx)):
                                issues.append("SKU %s(%s) multiple=%s 超出货源限购[%s~%s]（会不发货）"
                                              % (sid, val, mult, mn, mx))
                    except Exception:
                        pass
                    # 参数类型一致性（仅直充；只认货源明确要求，通用名不报）
                    if sd.get("productType") == 1 and conf_types:
                        sug, note = D.recharge_types_from_detail(det)
                        conf_list = list(conf_types) if isinstance(conf_types, (list, tuple)) else [conf_types]
                        if sug and not set(sug) <= set(conf_list):
                            issues.append("SKU %s(%s) 标识直充 %s 缺货源要求的 %s（%s）"
                                          % (sid, val, conf_list, sug, note))
        # ③ 价格规则
        if price is not None:
            is_first = "首单" in str(val)
            if is_first and float(price) < D.FIRST_ORDER_MIN_PRICE:
                warns.append("SKU %s(%s) 引流价 %s < 5元（参考下限，非硬规则）" % (sid, val, price))
            if with_source and pno and acct and int(acct) in D.VERIFIABLE_ACCTS:
                det, err = _src_check(pno, acct)
                if det:
                    try:
                        cost = float(det.get("salesPrice"))
                        if float(price) < cost and not is_first:
                            warns.append("SKU %s(%s) 售价 %s < 进价 %s（亏本）" % (sid, val, price, cost))
                    except Exception:
                        pass

    kind = "单品" if not sl else ("多SKU(%d)" % len(sl))
    if verbose:
        if issues:
            print("❌ %s %s %s" % (gid, name, kind))
            for i in issues:
                print("     - %s" % i)
            for w in warns:
                print("     · [提示] %s" % w)
        elif warns:
            print("⚠️ %s %s %s" % (gid, name, kind))
            for w in warns:
                print("     · %s" % w)
        else:
            print("✅ %s %s %s" % (gid, name, kind))
    return issues


# ---------- 全店 ----------
def main():
    args = sys.argv[1:]
    with_source = "--no-source" not in args
    only = next((a for a in args if a.isdigit()), None)

    print("-- 自愈前置 --")
    st = ensure_ready()
    print("   桥接=%s token=%s %s" % (st["bridge"], st["token"], ("自愈:" + ",".join(st["healed"])) if st["healed"] else ""))
    if not st["token"]:
        print("❌ token 不可用，无法体检（请确认 agiso 已登录）")

    rows = ((A.search_goods("", 1, 100).get("data") or {}).get("data") or {}).get("items") or []
    if only:
        rows = [x for x in rows if str(x.get("goodsId")) == only] or [{"goodsId": only}]
    print("全店商品数 = %d\n" % len(rows))

    report, total, warns_n = [], 0, 0
    for x in rows:
        gid = str(x.get("goodsId"))
        try:
            iss = audit_goods(gid, row=x, with_source=with_source)
        except Exception as e:
            print("ERR %s %s" % (gid, str(e)[:120])); iss = ["执行异常:" + str(e)[:80]]
        if iss:
            total += len(iss)
            report.append({"goodsId": gid, "name": str(x.get("goodsName"))[:40], "issues": iss})
    print("\n===== 真问题: %d 条 / 涉及商品 %d =====（货源检查=%s）" % (total, len(report), with_source))
    with open(os.path.join(HERE, "agiso_audit_report.json"), "w", encoding="utf-8") as f:
        json.dump({"ready": st, "issues": report}, f, ensure_ascii=False, indent=2)
    print("报告已存 agiso_audit_report.json")
    return total


if __name__ == "__main__":
    main()
