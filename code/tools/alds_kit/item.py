# -*- coding: utf-8 -*-
"""item —— 商品读写的最小封装（唯一实现）。

为什么单独一层：`get_item` 返回结构有两层 data 包裹（`data.data`），
旧代码在 create_from_pno 里叫 `_item_of`、在 deploy 里叫 `_dd`，各写一遍。
这里给一个名字，后续新代码只用这里的。
"""
import agiso_direct as A


def ok(r):
    """阿奇索接口成功判据：data.isSuccess（不是 HTTP 200）。"""
    return bool((r.get('data') or {}).get('isSuccess'))


def item_of(gid, draft=False):
    """读商品全量（已解包 data.data）。读不到返回 {}，由调用方判错。"""
    r = A.get_item(str(gid), draft=draft)
    d = (r or {}).get("data") or {}
    return d.get("data") or d


def set_images(gid, urls):
    """只改图片字段（imgUrls + imgList 同步），其余原样回传。

    🔴 必须两个字段一起改：只改 imgUrls 而 imgList 不同步，回读会不一致。
    """
    it = item_of(gid)
    if not it.get("title"):
        raise RuntimeError("读商品 %s 失败，无法改图片" % gid)
    it["imgUrls"] = list(urls)
    it["imgList"] = [{"imgUrl": u} for u in urls]
    return A.edit_item(it)


def image_urls(gid):
    return list((item_of(gid) or {}).get("imgUrls") or [])
