# -*- coding: utf-8 -*-
"""类目线路判定（闲鱼/阿奇索）。

## 为什么需要这个模块

闲鱼类目查询接口**全部已下线**（2026-11-15 实测）：
  GetNewCategoryList → 「此接口已经下线，请刷新页面或重启鱼店长客户端」
  GetCategoryList    → 同上
  GetCategory        → 空
所以**无法按商品性质自动查类目**，只能靠「模板继承 + 已知线路表」。

## 已知线路表

| categoryId | channelCatId | spBizType | 可发商品 |
|---|---|---|---|
| 50025461 | 35d467e7358057b0a7f7e02f36b0b49a | 25 | **通用虚拟商品**（会员直充/卡密/积分） |
| 50023914 | 4687e5abc9d918d7a7f7e02f36b0b49a | — | 剪映等**视频剪辑类**专用 |

🔴 2026-11-15 实测事故：拿 b 站商品（`50023914`）当模板建抖音短剧 →
   发布报 `Remote service error，类目检查限制,请联系闲鱼运营`。
   换 `50025461` 后一次发布成功。

## 策略

1. 默认走通用线路 `50025461`（覆盖会员直充、卡密、积分等绝大多数商品）。
2. 模板带过来的类目若是**受限线路**（如剪映线），且商品不是该线路专属品类 →
   自动纠偏回通用线路，并打印原因。
3. 商品确实属于受限线路专属品类（如剪映）→ 保留模板类目。
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
        # 标题里出现这些词才算该线路专属品类
        "keywords": ("剪映", "必剪", "快影", "剪辑", "醒图", "美图"),
    },
}


def resolve(template_category_id, template_channel_id, title="", verbose=True):
    """决定最终用哪个类目线路。

    返回 {"categoryId", "channelCatId", "spBizType", "name", "switched_from", "reason"}
    """
    tcid = template_category_id
    tch = template_channel_id
    title = str(title or "")

    # 模板就是通用线路 → 直接用
    if tcid == GENERAL["categoryId"]:
        return dict(GENERAL, switched_from=None, reason="模板已是通用线路")

    # 模板是受限线路
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
        # 不是该线路品类 → 纠偏回通用线路，否则发布会被拒
        out = dict(GENERAL, switched_from=tcid,
                   reason="模板是受限线路「%s」，但商品不属该品类 → 纠偏回通用线路" % rule["name"])
        if verbose:
            print("  ⚠️ 类目纠偏   : %s → 通用虚拟商品(%d)"
                  % (rule["name"], GENERAL["categoryId"]))
            print("                 %s" % out["reason"])
        return out

    # 未知类目：保守用通用线路（模板可能来自奇怪来源）
    out = dict(GENERAL, switched_from=tcid,
               reason="模板类目 %s 不在已知线路表 → 回退通用线路" % tcid)
    if verbose:
        print("  ⚠️ 类目未知   : 模板 categoryId=%s → 回退通用线路(%d)"
              % (tcid, GENERAL["categoryId"]))
    return out


def describe():
    """给文档/自检用的线路说明。"""
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
    print("=== 判定示例 ===")
    cases = [
        (50025461, "35d467e7358057b0a7f7e02f36b0b49a", "抖音短剧会员14天"),
        (50023914, "4687e5abc9d918d7a7f7e02f36b0b49a", "抖音短剧会员14天"),
        (50023914, "4687e5abc9d918d7a7f7e02f36b0b49a", "剪映SVIP会员1个月"),
        (99999999, "x", "某商品"),
    ]
    for cid, ch, t in cases:
        print()
        print("  模板 categoryId=%s 标题=%s" % (cid, t))
        r = resolve(cid, ch, t)
        print("    → categoryId=%s name=%s" % (r["categoryId"], r["name"]))
