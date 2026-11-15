# -*- coding: utf-8 -*-
"""商战网络「关键词搜索商品」通道。

背景：商战**开放 API 没有关键词搜索**（goodsList 是 300 秒 1 次的全量列表，不接受关键词）。
唯一可用的关键词入口是**前台搜索页** https://www.qqkami.com/search/{kw}?random=<ts>，
页面下一步就渲染出商品编号；拿到编号后再用 qqkami.detail(gid) 走 API 取详情。

本模块通过 edge-bridge(127.0.0.1:8787) 驱动浏览器完成「搜 → 读编号」。
用户日常开着 qqkami 页面时零等待。
"""
import json
import time
import urllib.parse
import urllib.request

RPC = "http://127.0.0.1:8787/rpc"
DEFAULT_TAB = 1679434860          # 默认 qqkami 标签；不存在时自动挑选
_op = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 绕开本机代理


def _rpc(cmd, params, timeout=60):
    body = json.dumps({"cmd": cmd, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"content-type": "application/json"})
    return json.loads(_op.open(req, timeout=timeout).read())


def _eval(code, tab=None, wait=90):
    tab = tab or pick_tab()
    r = _rpc("eval", {"tabId": tab, "code": code}, timeout=wait + 30)
    return (r.get("data") or {}).get("value") or r


def pick_tab():
    """挑一个 qqkami 标签；没有则返回默认值。"""
    try:
        d = _rpc("tabs_list", {}, timeout=25)
        for t in (d.get("data") or []):
            if "qqkami" in str(t.get("url") or ""):
                return t.get("id")
    except Exception:
        pass
    return DEFAULT_TAB


_READ = r'''(function(){
  var ids=[];
  document.querySelectorAll('a').forEach(function(a){
    var h=a.getAttribute('href')||'';
    if(h.indexOf('/category/detail/')>=0) ids.push(h.split('/').pop());
  });
  return JSON.stringify({url:location.href, ids:Array.from(new Set(ids)),
                         txt:(document.body.innerText||'')});
})()'''


def search_front(kw, tab=None, wait=10):
    """前台搜索 → [{'id': '66920', 'name': '...'}]（按页面出现顺序）。"""
    tab = tab or pick_tab()
    url = "https://www.qqkami.com/search/" + urllib.parse.quote(kw) + "?random=" + str(int(time.time() * 1000))
    _eval("try{location.href='%s';}catch(e){};'go'" % url, tab=tab, wait=40)
    time.sleep(wait)
    v = _eval(_READ, tab=tab)
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    try:
        o = json.loads(s)
    except Exception:
        return []
    ids = [str(x) for x in (o.get("ids") or [])]
    if not ids:
        # 兜底：按「商品编号」行的下一个数字解析
        lines = [l.strip() for l in str(o.get("txt") or "").split("\n")]
        for i, l in enumerate(lines):
            if l == "商品编号":
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j].isdigit():
                        ids.append(lines[j]); break
    # 解析「商品名 + 商品编号」成对出现：编号行上方最近的一条长文本即商品名
    lines = [l.strip() for l in str(o.get("txt") or "").split("\n")]
    SKIP = {"限时价", "面值价", "类型", "订单耗时", "终端限价", "立即购买", "商品编号",
            "：", ":", "自动充值", "卡密兑换"}
    name_of = {}
    for i, l in enumerate(lines):
        if l != "商品编号":
            continue
        gid = None
        for j in range(i + 1, min(i + 4, len(lines))):
            if lines[j].isdigit():
                gid = lines[j]
                break
        if not gid:
            continue
        nm = ""
        for k in range(i - 1, max(0, i - 8), -1):
            cand = lines[k]
            if (cand and cand not in SKIP and not cand.startswith("：")
                    and not cand.isdigit() and len(cand) > 4):
                nm = cand
                break
        name_of.setdefault(gid, nm)
    out, seen = [], set()
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        out.append({"id": i, "name": name_of.get(i, "")})
    return out


def search_with_detail(kw, limit=None, tab=None):
    """前台搜编号 + API 取详情（返回归一化字段）。注意 API 限 1 秒 1 次。"""
    import qqkami as Q
    rows = search_front(kw, tab=tab)
    if limit:
        rows = rows[:limit]
    out = []
    for r in rows:
        d = (Q.detail(r["id"]) or {}).get("data") or {}
        if d:
            d["id"] = r["id"]
            out.append(d)
    return out


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "讯飞"
    rows = search_front(kw)
    print("命中 %d 个商品编号：" % len(rows))
    for r in rows[:40]:
        print("  ", r["id"])
