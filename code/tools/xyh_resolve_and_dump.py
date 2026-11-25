# -*- coding: utf-8 -*-
"""从闲鱼分享短链（或个人主页 URL）出发，抓某个卖家闲鱼号的全部商品，
并逐件提取【标题 / 描述文案 / 档位价格】，用于对标学习标题与文案写法。

用法:
  python xyh_resolve_and_dump.py "<分享短链或userId或个人主页URL>" [--out out.json] [--maxpage 20]

产出:
  _xyh_<uid>_dump.json   原始数据
  _xyh_<uid>_titles.txt  人读的标题+描述清单
"""
import json, os, re, sys, time, argparse, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
RPC = "http://127.0.0.1:8787/rpc"
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOOLS = r"C:/Users/Administrator/WorkBuddy/2026-09-22-11-37-41/edge-bridge/tools"


def call(cmd, params, t=90):
    body = json.dumps({"cmd": cmd, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
    return json.loads(_OP.open(req, timeout=t).read().decode())


def ev(code, tab, t=90):
    r = call("eval", {"tabId": tab, "code": code}, t)
    d = r.get("data") or {}
    return d.get("value") if d.get("ok") else {"__err": r.get("error") or d.get("error")}


def new_tab(url, wait=6.0):
    r = call("tab_new", {"url": url}, 60)
    d = r.get("data") or {}
    tab = d.get("tabId") or d.get("id") or r.get("tabId")
    if tab is None:
        print("[!] tab_new 未返回 tabId:", json.dumps(r, ensure_ascii=False)[:300])
        return None
    time.sleep(wait)
    return int(tab)


LIST_JS = r"""(async function(uid, pn, ps){
 try{
  var res = await window.lib.mtop.request({api:'mtop.idle.web.xyh.item.list',v:'1.0',
      type:'POST',dataType:'json',data:{userId:String(uid),pageNumber:pn,pageSize:ps}});
  var d=(res&&res.data)||{};
  var cards=(d.cardList||[]).map(function(c){var cd=c.cardData||{};var dp=cd.detailParams||{};
      return {itemId:String(cd.itemId||dp.itemId||''), title:String(cd.title||dp.title||''),
              price:cd.soldPrice||cd.price||'', sold:cd.soldCnt||cd.wantCnt||''};});
  return JSON.stringify({n:cards.length, nextPage:d.nextPage||null, total:d.totalCount||null, items:cards});
 }catch(e){return 'ERR:'+(e&&e.message);}
})"""

# 详情：额外抓描述文案（多个候选字段全带回来）
DETAIL_JS = r"""(async function(iid){
 try{
  var res = await window.lib.mtop.request({api:'mtop.taobao.idle.pc.detail',v:'1.0',
      type:'POST',dataType:'json',data:{itemId:String(iid)}});
  var rd=(res&&res.data)||{};
  var it=(rd.itemDO)||{};
  var sk=(it.skuList||[]).map(function(s){
     var prop=(s.propertyList||[]).map(function(p){return (p.propertyText||'')+'='+(p.valueText||'');}).join('|');
     return {skuId:String(s.skuId||''), price:((s.priceInCent||0)/100), qty:s.quantity, prop:prop};
  });
  var sd=(rd.sellerDO)||{};
  var desc='';
  var cands=[it.desc, it.description, it.itemDesc, rd.desc, rd.description];
  if(it.descUrl && typeof it.descUrl==='object'){ cands.push(it.descUrl.desc, it.descUrl.content); }
  for(var i=0;i<cands.length;i++){ if(typeof cands[i]==='string' && cands[i].length>desc.length){desc=cands[i];} }
  var imgs=(it.images||[]).map(function(x){return (x&&x.url)||x||'';});
  return JSON.stringify({ok:true, title:it.title||'', desc:desc,
     min:((it.minPrice||0)/100), max:((it.maxPrice||0)/100),
     sold:it.soldCnt||'', browse:it.browseCnt||'', wish:it.wantCnt||'',
     seller:sd.nick||'', sellerId:String(sd.sellerId||sd.userId||''),
     imgs:imgs, skus:sk, n:sk.length});
 }catch(e){return 'ERR:'+(e&&e.message);}
})"""


def resolve_uid(arg):
    """短链 → userId"""
    if re.fullmatch(r"\d{8,20}", arg):
        return arg, "直接给了 userId"
    m = re.search(r"[?&]userId=(\d+)", arg)
    if m:
        return m.group(1), "URL 里直接带 userId"
    print("[1] 打开分享链接解析 userId …")
    tab = new_tab(arg, wait=7.0)
    if tab is None:
        return None, None
    for _ in range(3):
        raw = ev("location.href", tab)
        if isinstance(raw, str):
            m = re.search(r"[?&]userId=(\d+)", raw)
            if m:
                return m.group(1), "分享链接跳转 → %s" % raw[:110]
        time.sleep(2)
    # 兜底：读页面里出现的 userId
    raw = ev("(document.documentElement.innerHTML.match(/userId[=\\\\?\\\"']{1,3}(\\d{6,20})/)||[])[1]||''", tab)
    if isinstance(raw, str) and raw.strip():
        return raw.strip(), "从页面 HTML 抓到的 userId"
    return None, "解析失败，tab=%s" % tab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--out")
    ap.add_argument("--maxpage", type=int, default=20)
    a = ap.parse_args()

    uid, how = resolve_uid(a.target)
    print("userId = %s   （%s）" % (uid, how))
    if not uid:
        return

    home = "https://www.goofish.com/personal?userId=%s" % uid
    tab = new_tab(home, wait=6.0)
    if tab is None:
        return
    print("[2] 店铺页 tab =", tab)

    # 商品列表
    items, page, empty = [], 1, 0
    while page <= a.maxpage:
        d = None
        for _ in range(4):
            raw = ev("%s(%r,%d,20)" % (LIST_JS, uid, page), tab)
            if isinstance(raw, str) and not raw.startswith("ERR:"):
                try:
                    d = json.loads(raw); break
                except Exception:
                    d = None
            time.sleep(1.5)
        if d is None:
            print("  page %d 失败，停" % page); break
        got = d.get("items") or []
        print("  page %d: %d 条 (total=%s)" % (page, len(got), d.get("total")))
        items += got
        if not got:
            break
        page += 1
        time.sleep(0.5)

    seen, uniq = set(), []
    for it in items:
        if it.get("itemId") and it["itemId"] not in seen:
            seen.add(it["itemId"]); uniq.append(it)
    print("[3] 商品总数(去重) = %d" % len(uniq))

    # 逐件详情
    for i, it in enumerate(uniq, 1):
        raw = None
        for _ in range(3):
            raw = ev("%s('%s')" % (DETAIL_JS, it["itemId"]), tab)
            if isinstance(raw, str) and not raw.startswith("ERR:"):
                try:
                    it["detail"] = json.loads(raw); break
                except Exception:
                    pass
            time.sleep(1.2)
        if "detail" not in it:
            it["detail"] = {"ok": False}
        dt = it["detail"]
        print("[%2d/%d] %-14s sku=%-3s %s" % (i, len(uniq), it["itemId"], dt.get("n", 0), (it.get("title") or "")[:40]))
        time.sleep(0.4)

    out = a.out or ("_xyh_%s_dump.json" % uid)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"userId": uid, "seller": (uniq[0]["detail"].get("seller") if uniq else ""),
                   "items": uniq}, f, ensure_ascii=False, indent=1)
    print("→ %s" % out)

    # 人读清单
    lines = ["# 闲鱼号 %s 全部商品（%d 件）" % (uid, len(uniq)), ""]
    for i, it in enumerate(uniq, 1):
        dt = it.get("detail") or {}
        lines.append("## %02d. itemId=%s" % (i, it["itemId"]))
        lines.append("- 标题：%s" % (dt.get("title") or it.get("title") or ""))
        lines.append("- 价格：%s ~ %s   已售=%s 浏览=%s" % (dt.get("min"), dt.get("max"), dt.get("sold"), dt.get("browse")))
        if dt.get("skus"):
            lines.append("- 档位：")
            for s in dt["skus"]:
                lines.append("    · %s → ¥%s（库存 %s）" % (s.get("prop"), s.get("price"), s.get("qty")))
        desc = (dt.get("desc") or "").strip()
        if desc:
            lines.append("- 描述：")
            for ln in desc.splitlines():
                if ln.strip():
                    lines.append("    " + ln.strip())
        lines.append("")
    tf = out.replace(".json", "_titles.txt")
    open(tf, "w", encoding="utf-8").write("\n".join(lines))
    print("→ %s" % tf)


if __name__ == "__main__":
    main()
