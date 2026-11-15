# -*- coding: utf-8 -*-
"""media —— 图片上传到阿奇索媒体库（唯一实现）。

合并自两处重复代码（2026-11-14）：
  · deploy.upload_media(raw, name)            → 返回 (url, imageId)，⑬ 详情图用
  · create_from_pno._upload_media(raw, name)  → 只取 url，主图用

行为与旧实现一致：multipart 字段名必须是 `files`（`file`/`media`/`img` 都报
「上传文件数量错误」）；返回 ossKey，拼成 oss 直链写进 imgUrls，保存时后端自动
转存闲鱼 CDN，所以不用自己传闲鱼。
"""
import json
import ssl
import urllib.request
import uuid

import agiso_direct as A

MEDIA_UPLOAD_PATH = "/api/GoodsManage/MediaUpload"
OSS_BASE = "https://agiso-oss1.oss-cn-zhangjiakou.aliyuncs.com/"

_CTYPE = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
          ".gif": "image/gif", ".webp": "image/webp"}


def _opener():
    """跳过证书校验：货源图床/阿里 OSS 证书链在本机偶发不可信（旧实现即如此）。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                       urllib.request.HTTPSHandler(context=ctx))


def upload_media(raw, name="upload.png"):
    """图片 bytes → (可写进 imgUrls 的 URL, imageId)。

    token 由 agiso_direct 维护；失效时旧实现会抛异常，这里保持同样行为，不静默兜底。
    """
    if not A.TOKEN:
        A.TOKEN = A.token_from_browser(open_if_missing=False)
    b = "----wb" + uuid.uuid4().hex
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ".png"
    ctype = _CTYPE.get(ext, "image/png")
    body = ('--%s\r\nContent-Disposition: form-data; name="files"; filename="%s"\r\n'
            'Content-Type: %s\r\n\r\n' % (b, name, ctype)).encode()
    body += raw + ('\r\n--%s--\r\n' % b).encode()
    req = urllib.request.Request(
        A.BASE + MEDIA_UPLOAD_PATH, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=" + b,
                 "Authorization": "Bearer " + A.TOKEN,
                 "x_front": "1", "X-Requested-With": "XMLHttpRequest"})
    with _opener().open(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    dd = ((d or {}).get("data") or {}).get("data") or {}
    if not dd.get("ossKey"):
        raise RuntimeError("MediaUpload 失败: " + json.dumps(d, ensure_ascii=False)[:200])
    return OSS_BASE + dd["ossKey"], dd.get("imageId")


def upload_file(path, name=""):
    """本地文件 → 同上。name 留空则用文件名（决定 Content-Type）。"""
    import os
    nm = name or os.path.basename(path)
    with open(path, "rb") as f:
        return upload_media(f.read(), nm)
