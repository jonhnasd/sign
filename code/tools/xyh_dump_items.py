# -*- coding: utf-8 -*-
"""在已开的闲鱼页面里，按 itemId 批量取【标题 + 描述文案 + 档位价格】。
用于对标学习 / 自查自家商品文案。
用法: python xyh_dump_items.py <tabId> <itemId> [<itemId> ...]
"""
import json, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
RPC = "http://127.0.0.1:8787/rpc"
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

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
  var desc='', cands=[it.desc, it.description, it.itemDesc, rd.desc, rd.description];
  if(it.descUrl && typeof it.descUrl==='object'){ cands.push(it.descUrl.desc, it.descUrl.content); }
  for(var i=0;i<cands.length;i++){ if(typeof cands[i]==='string' && cands[i].length>desc.length){desc=cands[i];} }
  var imgs=(it.images||[]).map(function(x){return (x&&x.url)||x||'';});
  return JSON.stringify({ok:true, title:it.title||'', desc:desc,
     min:((it.minPrice||0)/100), max:((it.maxPrice||0)/100),
     sold:it.soldCnt||'', browse:it.browseCnt||'', wish:it.wantCnt||'',
     seller:sd.nick||'', imgs:imgs, skus:sk, n:sk.length});
 }catch(e){return 'ERR:'+(e&&e.message);}
})"""


def call(cmd, params, t=90):
    body = json.dumps({"cmd": cmd, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
    return json.loads(_OP.open(req, timeout=t).read().decode())


def ev(code, tab, t=90):
    r = call("eval", {"tabId": tab, "code": code}, t)
    d = r.get("data") or {}
    return d.get("value") if d.get("ok") else {"__err": r.get("error") or d.get("error")}


def main():
    tab = int(sys.argv[1])
    ids = sys.argv[2:]
    out = []
    for iid in ids:
        raw = None
        for _ in range(3):
            raw = ev("%s('%s')" % (DETAIL_JS, iid), tab)
            if isinstance(raw, str) and not raw.startswith("ERR:"):
                try:
                    raw = json.loads(raw); break
                except Exception:
                    raw = None
            time.sleep(1.2)
        out.append({"itemId": iid, "detail": raw})
        d = raw if isinstance(raw, dict) else {}
        print("=" * 70)
        print(f"itemId={iid}  浏览={d.get('browse')} 想要={d.get('wish')} 售={d.get('sold')} 价格={d.get('min')}~{d.get('max')}")
        print("标题:", d.get("title"))
        if d.get("skus"):
            for s in d["skus"]:
                print(f"   档位 {s.get('prop')} → ¥{s.get('price')} (库存{s.get('qty')})")
        print("-" * 70)
        print((d.get("desc") or "").strip() or "(无描述)")
        print()
        time.sleep(0.5)
    fn = "_xyh_items_%s.json" % ("_".join(ids[:3]) if ids else "x")
    json.dump(out, open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→ %s" % fn)


if __name__ == "__main__":
    main()
