# -*- coding: utf-8 -*-
"""省会地区编码 —— 数据来自**闲鱼接口**，不是手写推算。

## 为什么改成接口取数

2026-11-15 用户要求「类目的接口你测试下」，顺带把地区接口也测通了：
  `POST /api/GoodsManage/GetDivision`  → 985433 字符，34 省 / 394 市 / 2814 区
  嵌套树结构：省.children = 市，市.children = 区

**这推翻了我之前手写编码表的做法。** 手写时我把 `130304` 标成「保定市新市区」，
接口显示真实是 **秦皇岛市北戴河区** —— 手写推断不可靠，必须用接口。

## 本模块职责

  ① 从接口拉全量区划树，缓存到本地 JSON（离线可用）
  ② 只保留「省会城市」：省会 = 该省下 id 形如 `XX0100` 的市
  ③ 随机选一个省会 + 该市一个真实存在的区，拼成 3 级 divisionIdList

缓存文件：`_cn_divisions_cache.json`
"""

import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cn_divisions_cache.json")

# 直辖市：省=市，直接取该市下的区
MUNICIPALITIES = {"110000", "120000", "310000", "500000"}


def _fetch_tree():
    """从闲鱼接口拉全量区划树。"""
    import agiso_direct as A
    r = A._post("/api/GoodsManage/GetDivision", {})
    d = (r or {}).get("data") or {}
    tree = d.get("data")
    if not isinstance(tree, list) or not tree:
        raise RuntimeError("GetDivision 无数据: %s" % str(d)[:120])
    return tree


def _walk(nodes, depth=0, out=None):
    """扁平化：[(node, depth)]。"""
    if out is None:
        out = []
    for n in nodes or []:
        out.append((n, depth))
        _walk(n.get("children") or [], depth + 1, out)
    return out


def refresh_cache(verbose=True):
    """重新拉接口并写缓存。"""
    tree = _fetch_tree()
    json.dump(tree, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    flat = _walk(tree)
    if verbose:
        print("  ✓ 已缓存 %d 省 / %d 节点 → %s"
              % (len(tree), len(flat), os.path.basename(CACHE)))
    return tree


def load_tree(allow_fetch=True):
    """读缓存；没有就拉接口。"""
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            pass
    if not allow_fetch:
        raise RuntimeError("无地区缓存且不允许联网")
    return refresh_cache(verbose=False)


def capitals(tree=None):
    """返回全部省会候选 [(divisionIdList, 名称, 省名, 市名, 区名)]。

    省会判据：省下 id 形如 `XX0100` 的市（国家码表里省会固定为 XX0100）。
    直辖市：省码 == 市码（110000/110100），直接取该市下的区。
    """
    tree = tree if tree is not None else load_tree()
    out = []
    for prov in tree:
        pid = str(prov.get("id") or "")
        if not pid.endswith("0000"):
            continue
        pname = prov.get("shortName") or prov.get("name") or ""
        cities = prov.get("children") or []
        if not cities:
            continue
        # 选省会：优先 XX0100，直辖市取自身
        cap = None
        if pid in MUNICIPALITIES:
            cap = cities[0] if cities else None
        else:
            for c in cities:
                cid = str(c.get("id") or "")
                if cid.endswith("0100") and cid[:2] == pid[:2]:
                    cap = c
                    break
        if not cap:
            continue
        cid = str(cap.get("id") or "")
        cname = cap.get("shortName") or cap.get("name") or ""
        dists = [d for d in (cap.get("children") or []) if str(d.get("id") or "")]
        if not dists:
            continue
        for d in dists:
            did = str(d.get("id") or "")
            if not did or did.endswith("00"):
                continue
            dname = d.get("shortName") or d.get("name") or ""
            label = ("%s%s" % (cname, dname)) if pid in MUNICIPALITIES \
                else ("%s %s %s" % (pname, cname, dname))
            out.append(([pid, cid, did], label, pname, cname, dname))
    return out


def pick(rng=None, avoid=None, tree=None):
    """随机选一个省会城市的真实区。

    avoid: 要避开的 divisionId / divisionIdList 末位列表
    """
    r = rng or random
    pool = capitals(tree)
    if not pool:
        raise RuntimeError("省会列表为空，检查地区缓存")
    if avoid:
        avoid_set = {str(a) for a in avoid}
        filtered = [x for x in pool if x[0][2] not in avoid_set and x[0][1] not in avoid_set]
        if filtered:
            pool = filtered
    dl, label, pname, cname, dname = r.choice(pool)
    return {
        "divisionId": int(dl[2]),
        "divisionIdList": list(dl),
        "name": label,
        "province": pname, "city": cname, "district": dname,
    }


def all_divisions(tree=None):
    """[(divisionIdList, 名称)] 全表（每省只取省会第一个区，用于展示）。"""
    seen = {}
    for dl, label, p, c, d in capitals(tree):
        key = (dl[0], dl[1])
        if key not in seen:
            seen[key] = (dl, label)
    return list(seen.values())


if __name__ == "__main__":
    print("=== 拉取/读取地区树 ===")
    tree = load_tree()
    print("  省级节点:", len(tree))
    caps = capitals(tree)
    print("  省会区级候选:", len(caps))
    print()
    print("=== 每省省会（首个区）===")
    for dl, label in all_divisions(tree):
        print("  %-30s %s" % ("/".join(dl), label))
    print()
    print("=== 随机抽 5 次 ===")
    for _ in range(5):
        p = pick(tree=tree)
        print("  %-32s %s" % ("/".join(p["divisionIdList"]), p["name"]))
