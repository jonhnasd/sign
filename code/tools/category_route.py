# -*- coding: utf-8 -*-
"""类目线路判定（闲鱼/阿奇索）—— 基于实测通的接口。

## 接口实测结论（2026-11-15，用户要求「类目的接口你测试下」）

之前我只试了 4 个路径就断言「类目接口全部下线」，**这个结论是错的**。
从 SPA 打包 JS 里提取出完整接口清单后逐个实测：

| 接口 | 结果 | 用途 |
|---|---|---|
| `GetNewCategoryList` | ⛔ 此接口已经下线 | — |
| `GetCategoryList` | ⛔ 此接口已经下线 | — |
| `GetCategory` | 空 | — |
| `GetDivision` | ✅ **985KB 完整区划树**（34省/394市/2814区） | 地区随机 |
| `GetNewHistoryCategories` | ✅ 本店用过的 channelCatId 列表 | **线路发现** |
| `GetLocalCategoryIdList` | ✅ 75 个本地类目 ID | 参考 |
| `GetEasyBuyCategoryIdList` | ✅ 便捷购类目 ID | 参考 |
| `GetItemBizTypeList` | ✅ 业务类型（普通C2C/验货宝/虚拟游戏） | 参考 |
| `GetVirtualSpBizTypeList` | ✅ `["25","22","23","20"]` | spBizType 合法值 |
| `GetHistoryDivision` | ✅ 本店用过的地区 | 参考 |

**类目树本身仍无法查询**（GetNewCategoryList 确实下线了），
但 `GetNewHistoryCategories` 能告诉我们「本店实际用过哪些线路」，
配合已知线路表可以判断模板线路是否合法。

## 已知线路表

| categoryId | channelCatId | spBizType | 可发商品 |
|---|---|---|---|
| 50025461 | 35d467e7358057b0a7f7e02f36b0b49a | 25 | **通用虚拟商品**（会员直充/卡密/积分） |
| 50023914 | 4687e5abc9d918d7a7f7e02f36b0b49a | — | 剪映等**视频剪辑类**专用 |

🔴 2026-11-15 事故：拿 b 站商品（50023914 剪映线）当模板建抖音短剧 →
   发布报 `Remote service error，类目检查限制`。换 50025461 后成功。
"""

# 通用虚拟商品线路：默认首选
GENERAL = {
    "categoryId": 50025461,
    "channelCatId": "35d467e7358057b0a7f7e02f36b0b49a",
    "spBizType": "25",
    "name": "通用虚拟商品",
}

# 受限线路：只有专属品类能用，混用会被闲鱼拒
RESTRICTED = {
    50023914: {
        "channelCatId": "4687e5abc9d918d7a7f7e02f36b0b49a",
        "name": "视频剪辑类（剪映线）",
        "keywords": ("剪映", "必剪", "快影", "剪辑", "醒图", "美图"),
    },
}

# channelCatId → categoryId 反查
CHANNEL_TO_CAT = {v["channelCatId"]: k for k, v in RESTRICTED.items()}
CHANNEL_TO_CAT[GENERAL["channelCatId"]] = GENERAL["categoryId"]


def fetch_history_channels():
    """本店实际用过的 channelCatId 列表（接口实测可用）。

    失败返回 []，不抛异常 —— 这是辅助信息，不该阻断建品。
    """
    try:
        import agiso_direct as A
        r = A._post("/api/GoodsManage/GetNewHistoryCategories", {})
        d = (r or {}).get("data") or {}
        lst = d.get("data")
        if isinstance(lst, list):
            return [str(x) for x in lst if x]
    except Exception:
        pass
    return []


def fetch_sp_biz_types():
    """spBizType 合法值（接口实测返回 ["25","22","23","20"]）。"""
    try:
        import agiso_direct as A
        r = A._post("/api/GoodsManage/GetVirtualSpBizTypeList", {})
        d = (r or {}).get("data") or {}
        lst = d.get("data")
        if isinstance(lst, list):
            return [str(x) for x in lst]
    except Exception:
        pass
    return []


def resolve(template_category_id, template_channel_id, title="", verbose=True):
    """决定最终用哪个类目线路。

    返回 {"categoryId","channelCatId","spBizType","name","switched_from","reason"}
    """
    tcid = template_category_id
    tch = template_channel_id
    title = str(title or "")

    if tcid == GENERAL["categoryId"]:
        return dict(GENERAL, switched_from=None, reason="模板已是通用线路")

    if tcid in RESTRICTED:
        rule = RESTRICTED[tcid]
        hit = [w for w in rule["keywords"] if w in title]
        if hit:
            out = {
                "categoryId": tcid,
                "channelCatId": rule["channelCatId"],
                "spBizType": GENERAL["spBizType"],
                "name": rule["name"],
                "switched_from": None,
                "reason": "商品属该线路专属品类（命中「%s」），保留模板类目" % "、".join(hit),
            }
            if verbose:
                print("  类目         : %s（%s）" % (rule["name"], out["reason"]))
            return out
        out = dict(GENERAL, switched_from=tcid,
                   reason="模板是受限线路「%s」，但商品不属该品类 → 纠偏回通用线路" % rule["name"])
        if verbose:
            print("  ⚠️ 类目纠偏   : %s → 通用虚拟商品(%d)"
                  % (rule["name"], GENERAL["categoryId"]))
            print("                 %s" % out["reason"])
        return out

    out = dict(GENERAL, switched_from=tcid,
               reason="模板类目 %s 不在已知线路表 → 回退通用线路" % tcid)
    if verbose:
        print("  ⚠️ 类目未知   : 模板 categoryId=%s → 回退通用线路(%d)"
              % (tcid, GENERAL["categoryId"]))
    return out


def describe():
    lines = ["通用线路: categoryId=%d channelCatId=%s spBizType=%s"
             % (GENERAL["categoryId"], GENERAL["channelCatId"], GENERAL["spBizType"])]
    for cid, r in RESTRICTED.items():
        lines.append("受限线路: categoryId=%d (%s) 专属词=%s"
                     % (cid, r["name"], "/".join(r["keywords"])))
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== 类目线路表 ===")
    print(describe())
    print()
    print("=== 接口：本店用过的线路 ===")
    hist = fetch_history_channels()
    if hist:
        for c in hist:
            cid = CHANNEL_TO_CAT.get(c)
            print("  %s  →  %s" % (c, ("categoryId=%d" % cid) if cid else "未知线路"))
    else:
        print("  （接口无返回）")
    print()
    print("=== 接口：spBizType 合法值 ===")
    print(" ", fetch_sp_biz_types() or "（无返回）")
