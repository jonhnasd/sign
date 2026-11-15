# -*- coding: utf-8 -*-
"""main_image —— 主图能力（唯一实现）。

从 create_from_pno.py 迁出（2026-11-14），原因：
  主图全套函数只活在建品脚本里，deploy 的 ①-⑬ 环节表没有「主图」，
  于是任何不经过 create_from_pno 的入口（按阿奇索 ID 上 SKU、存量返工、
  老商品补图）天然没有主图能力 —— 同一个错误修在建品链路，ID 链路看不见。

固定方案（范式库 §七·八）：复刻式生图 —— 必须有参考图、图生图、七段骨架 prompt、
出图后逐字核验白名单、写 manifest 供 guard ⑨b 验收。
禁止静默回退「通用会员卡片 + 模型画文字」的纯文生图。

参考图优先级：调用方 --ref > 固定素材库该 pno 的商品图 > 停止（报缺图）。
"""
import os
import subprocess
import sys
import time

import agiso_direct as A
import replica_main_image as R
from . import media
from .item import item_of, ok

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 🔴 2026-11-15：改走 paths.py 单一配置源（原先 4 处写死 C:\Users\Administrator\...）。
#    换机器时设 DSH_SOPS_BIN / DSH_AGE_KEY / DSH_CREDENTIALS / DSH_KUAIPAO 即可。
try:
    from paths import CFG as _CFG
except Exception:
    _CFG = None

SOPS_BIN = str((_CFG.sops_bin if _CFG else None) or
               r"C:\Users\Administrator\.workbuddy\tools\crypto\sops.exe")
SOPS_KEY_FILE = str((_CFG.age_key if _CFG else None) or
                    r"C:\Users\Administrator\.workbuddy\tools\crypto\age\keys.txt")
CRED_YAML = str((_CFG.credentials if _CFG else None) or
                r"C:\Users\Administrator\Desktop\obisidian\obisidian\secrets\credentials.sops.yaml")
KUAIPIAO_GEN = str((_CFG.kuaipao_gen if _CFG else None) or
                   r"C:\Users\Administrator\Desktop\workbuddy\文档提取\_yq_poster\kuaipao_gen.py")
KUAIPIAO_MODEL = "gpt-image-2.6"


def get_kuaipao_key():
    """快跑 key 走 sops 加密凭据，运行时解密、明文不落盘。"""
    if os.environ.get("KUAIPAO_API_KEY"):
        return os.environ["KUAIPAO_API_KEY"]
    env = dict(os.environ)
    env["SOPS_AGE_KEY_FILE"] = SOPS_KEY_FILE
    try:
        # 本机 sops 版本不支持嵌套 --extract，解密整个 kuaipao 子映射再按行取 key
        out = subprocess.run([SOPS_BIN, "--decrypt", "--extract", '["kuaipao"]',
                              CRED_YAML], capture_output=True, text=True, env=env, timeout=60)
    except Exception as e:
        raise RuntimeError("sops 解密快跑 key 失败: %s" % e)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError("sops 解密快跑 key 失败: " + (out.stderr or out.stdout)[:300])
    for line in out.stdout.splitlines():
        s = line.strip()
        if s.startswith("key:") or s.startswith("key "):
            return s.split(":", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("sops 解密结果中未找到 kuaipao.key: " + out.stdout[:200])


def gen_main_prompt(title, sku_labels, account_label, product_name='', brand_hint='',
                    sku_display_mode='highest'):
    """唯一主图提示词入口 = 复刻式七段骨架（范式库 §七·八）。

    旧实现（通用会员卡片 + 模型画文字、title[:22] 硬截断）已废弃：
    文字交给模型必失真、标题被切出孤字、无参考图也无商品 Logo。
    """
    name = product_name or R.clean_product_name(title)
    return R.build_prompt(name, sku_labels, account_label, brand_hint, sku_display_mode)


def set_main_image(gid, png_path):
    """两步法把本地 png 设成商品主图（只改 imgUrls/imgList）。

    为什么两步：直接写 CDN 图会被后端拒；先追加 oss 直链让后端转存闲鱼 CDN，
    回读出 CDN 地址后再置顶，才能既换主图又保留其余图片。
    """
    A.TOKEN = A.token_from_browser(open_if_missing=False)
    item = item_of(gid)
    if not item.get("title"):
        raise RuntimeError("读商品 %s 失败，无法设主图" % gid)
    old_urls = list(item.get("imgUrls") or [])
    old_list = list(item.get("imgList") or [])
    raw = open(png_path, "rb").read()
    oss, _ = media.upload_media(raw, "main_%s.png" % gid)
    # ① 旧图 + OSS 新图 → 后端转存闲鱼 CDN
    e1 = dict(item)
    e1["imgUrls"] = old_urls + [oss]
    e1["imgList"] = old_list + [{"imgUrl": oss}]
    r1 = A.edit_item(e1)
    if not ok(r1):
        raise RuntimeError("① Edit 失败: " + str(r1)[:200])
    time.sleep(3)
    back = item_of(gid)
    cur = list(back.get("imgUrls") or [])
    new_cdn = [u for u in cur if u not in old_urls and "agiso-oss" not in u]
    if not new_cdn:
        raise RuntimeError("① 未发现闲鱼 CDN 转存链接: " + str(cur)[:200])
    cdn = new_cdn[0]
    # ② 主图置顶，保留其余图片（详情图等不被覆盖）
    others = [u for u in cur if u != cdn]
    e2 = dict(back)
    e2["imgUrls"] = [cdn] + others
    e2["imgList"] = [{"imgUrl": cdn}] + [{"imgUrl": u} for u in others]
    r2 = A.edit_item(e2)
    if not ok(r2):
        raise RuntimeError("② Edit 失败: " + str(r2)[:200])
    time.sleep(3)
    fin = item_of(gid)
    urls = list(fin.get("imgUrls") or [])
    good = bool(urls and urls[0] == cdn)
    if not good:
        raise RuntimeError("主图置顶回读失败：线上首图不是新生成图片（cdn=%s, urls=%s)"
                           % (cdn, urls[:3]))
    print("     主图置顶: %s ｜ 共 %d 张图 ✅" % (cdn.rsplit("/", 1)[-1], len(urls)))
    return cdn


def strip_template_images(gid, template_url):
    """🔴 2026-11-14（165 事故）：模板法建品会把模板商品首图当占位图带进来。

    原因链：`InsertDraft` 整份复制模板 → `imgList` 只有 1 张模板图（发布要求 ≥1 图）
    → `set_main_image()` 只把自有图插到最前、保留 others → deploy ⑬ 只增不删
    → 模板图必然残留，只能靠 ⑬ 报红后人工清。

    修法：按建草稿时记录的模板图 URL 精确删除（不靠猜、不误删自有图），
    置顶之后执行，买家看不到中间态；删到 0 张则中止（闲鱼要求至少 1 图）。
    """
    if not template_url:
        return None
    item = item_of(gid) or {}
    urls = list(item.get('imgUrls') or [])
    keep = [u for u in urls if u != template_url]
    if len(keep) == len(urls):
        return None
    if not keep:
        print("     ⚠️ 模板图是唯一一张图，跳过清理（闲鱼要求至少 1 张）")
        return None
    item['imgUrls'] = keep
    item['imgList'] = [{'imgUrl': u} for u in keep]
    r = A.edit_item(item)
    if not ok(r):
        raise RuntimeError("模板残留图清理失败: %s" % str(r)[:200])
    time.sleep(1.0)
    back = (item_of(gid) or {}).get('imgUrls') or []
    if template_url in back:
        raise RuntimeError("模板残留图清理回读失败：目标图仍在线上 %s" % template_url)
    print("     模板占位图已清理：%d → %d 张" % (len(urls), len(back)))
    return back


def preflight_reference(pno, acct, cli_ref=''):
    """线上写操作前的参考图预检；失败必须抛 ReplicaRefMissing。"""
    return R.resolve_reference(pno, acct, cli_ref, validate=True)


def gen_and_set_main_image(gid, title, dry, pno, acct, cli_ref='', upload=True,
                           label_override='', sku_display_mode='highest'):
    """复刻式生图 → 两步法上传置顶 → 写 manifest。返回线上主图 URL（或本地图路径）。

    缺参考图 / 回读不到自身 SKU 档位 / 生图上传失败时抛异常，禁止上层继续写入。
    upload=False 只出本地预览图（不动线上主图）。
    """
    ref = preflight_reference(pno, acct, cli_ref)
    if dry:
        print("     [dry] 参考图预检通过：%s" % ref.get("evidence"))
        print("     [dry] 跳过生图与上传（加 --go 才真做）")
        return None
    src = R.source_of(acct)
    info = R.lookup_supplier(pno, src)
    # 🔴 买家字段必须用**具体标识**（手机号/微博昵称/华为账号），不能印阿奇索字段名「充值账号」。
    # 三类才印「下单填写X」：①具体标识 ②平台账号 ③人工显式指定。卡密不印；原文没写清也不印。
    account_label = str(label_override or '').strip()
    if not account_label:
        kind = info.get('buyer_kind') or ''
        if str(info.get('form') or '') == '卡密':
            print("     ℹ️ 卡密类：主图不印「下单填写」句（买家无需填账号）")
        elif kind in ('标识', '平台账号'):
            account_label = info.get('buyer_field') or ''
            print("     买家填写：%s（%s）" % (account_label, info.get('buyer_evidence', '')))
        else:
            print("     ⚠️ 主图不印「下单填写」句：货源原文没写清买家填什么（%s）" % info.get('buyer_evidence', ''))
            print("        依据不足不猜；确认后可传 label_override / --account-label 显式指定")

    # 档位必须取目标商品自身 SKU（线上回读），不照抄参考商品的旧档位
    item = item_of(gid) or {}
    selection = R.select_sku_display(item.get('itemSkuList') or [], sku_display_mode)
    sku_labels = selection['labels']
    if selection.get('reminder'):
        print("     %s" % selection['reminder'])
    print("     SKU 展示模式: %s ｜ 判定依据: %s" % (
        selection['mode'], selection['selection_evidence']))

    ref_local = os.path.join(TOOLS_DIR, "_replica_ref_%s.png" % gid)
    ref_src = ref.get("ref_url")
    try:
        R.download_ref(ref_src, ref_local)
    except Exception as e:
        raise R.ReplicaRefMissing("参考图获取失败：%s" % e)

    name = R.clean_product_name(title)
    prompt = gen_main_prompt(title, sku_labels, account_label, name,
                             sku_display_mode=selection['mode'])
    tmp_p = os.path.join(TOOLS_DIR, "_kp_prompt_%s.txt" % gid)
    tmp_o = os.path.join(TOOLS_DIR, "_kp_out_%s" % gid)
    open(tmp_p, "w", encoding="utf-8").write(prompt)
    env = dict(os.environ)
    env["KUAIPAO_API_KEY"] = get_kuaipao_key()
    print("     复刻式生图（%s，图生图）｜参考图: %s" % (KUAIPIAO_MODEL, str(ref_src)[:110]))
    print("     档位(自身SKU): %s ｜ 买家填写: %s" % (
        " / ".join(sku_labels), account_label or "无（不印填写句）"))
    print("     ⚠️ 出图后逐字核验白名单: %s" % " / ".join(
        R.text_whitelist(name, sku_labels, account_label)))
    r = subprocess.run([sys.executable, KUAIPIAO_GEN, "--prompt-file", tmp_p,
                        "--out", tmp_o, "--model", KUAIPIAO_MODEL, "--ref", ref_local],
                       capture_output=True, text=True, env=env, timeout=360,
                       # 🔴 2026-11-15：Windows 默认 GBK 解码子进程输出，中文/emoji 会抛
                       #    UnicodeDecodeError（0x80）并顶到线程里，表现为 exit code 1
                       #    但实际生图已成功 —— 会误导排障方向。
                       encoding="utf-8", errors="replace")
    try:
        if r.returncode != 0:
            raise RuntimeError("生图失败: " + (r.stderr or r.stdout)[:400])
        png = tmp_o + ".png" if os.path.exists(tmp_o + ".png") else (
            tmp_o + ".jpg" if os.path.exists(tmp_o + ".jpg") else None)
        if not png:
            raise RuntimeError("生图输出未找到: " + tmp_o + ".*")
        if not upload:
            print("     本地预览图（未上传，不动线上主图）: %s" % png)
            return png
        cdn = set_main_image(gid, png)
        # 生成记录：guard ⑨b 靠这份记录验收，缺记录/非复刻式/未核验一律不算完成
        R.write_manifest(
            gid, mode=R.VALID_MODE,
            sku_display_mode=selection['mode'],
            displayed_skus=selection['displayed_skus'],
            sku_selection_evidence=selection['selection_evidence'],
            all_skus_reminder=selection.get('reminder') or None,
            ref_source=ref.get("ref_source"),
            ref_source_name=ref.get("ref_source_name"),
            ref_match=ref.get("match"),
            ref_evidence=ref.get("evidence"),
            ref_pno=ref.get("ref_pno"), ref_acct=ref.get("ref_acct"),
            ref_url=ref.get("ref_url"),
            product_name=name, sku_labels=sku_labels, account_label=account_label,
            whitelist=R.text_whitelist(name, sku_labels, account_label),
            prompt_sha256=R.sha256_text(prompt),
            out_sha256=R.sha256_file(png),
            main_img_url=cdn, uploaded=bool(cdn), whitelist_verified=False,
        )
        print("     生成记录已写：mode=replica ref_pno=%s（guard ⑨b 可验收）" % pno)
        print("     ⚠️ 白名单未逐字核验前 ⑨b 会红。核验后执行：")
        print("        python replica_main_image.py --mark-verified --gid %s --note \"<核验结论>\"" % gid)
        return cdn
    finally:
        for f in (tmp_p, ref_local):
            if os.path.exists(f):
                os.remove(f)
        if upload:
            for f in (tmp_o + ".png", tmp_o + ".jpg"):
                if os.path.exists(f):
                    os.remove(f)


def ensure_main_image(gid, mode, title, pno, acct, dry=False,
                      cli_ref='', label_override='', template_url='',
                      sku_display_mode='highest'):
    """编排器统一入口：按 contract.MAIN_IMAGE_MODES 决定做不做。

    · replica → 复刻式重做 + 清模板残留图
    · keep    → 不碰图（返回现有主图 URL）
    · skip    → 什么都不做
    返回 (主图 URL, 动作说明)。replica 失败直接抛异常，阻止编排器继续线上写入。
    """
    if mode == "skip":
        return None, "跳过（main_image=skip）"
    if mode == "keep":
        urls = (item_of(gid) or {}).get("imgUrls") or []
        return (urls[0] if urls else None), "保留现有主图（main_image=keep）"
    if mode != "replica":
        return None, "未知 main_image 模式：%s" % mode
    cdn = gen_and_set_main_image(gid, title, dry, pno, acct,
                                 cli_ref=cli_ref, label_override=label_override,
                                 sku_display_mode=sku_display_mode)
    if cdn and template_url:
        strip_template_images(gid, template_url)
    return cdn, "复刻式重做"
