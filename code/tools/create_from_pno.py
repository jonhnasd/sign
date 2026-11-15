# -*- coding: utf-8 -*-
"""从货源编号（pno）直接在阿奇索新建宝贝，并把结果接上 deploy.py 一条龙。

2026-11-12 实测打通（见 Obsidian [[操作-从货源编号新建宝贝]]）：
  InsertDraft  -> 建草稿（整份商品 payload，26 字段，itemId=0）
  SearchDraftGoodsList -> 回读草稿 id
  PublishDraft {"ids":[id]} -> 返回异步 code
  GetPublishDraftResult/{code} -> 轮询发布结果（成功拿 itemId）
  DeleteDraft {"ids":[id]} -> 清理草稿

🔴 2026-11-12 自动驾驶授权（用户定）：默认直接做，尽量不问。
  • 默认行为（不加 --dry）：建草稿 → 发布到闲鱼 → 跑 deploy.py 一条龙 → 快跑生主图置顶。
  • 标题违规（搭子/伴游/地陪 等触发 SECURITY_WARN_ERROR）→ 自动剔除/改写并重试，不用等用户。
  • 主图生图统一走快跑 API（gpt-image-2.6），不经用户同意；仍过 prompt_guard 禁词校验。
  • 🔴 2026-11-14 固定：主图**只能走复刻式生图**（replica_main_image.py 七段骨架 + 图生图 --ref）。
    参考图优先级 = --ref 指定图 > 固定素材库该 pno 的货源商品图；取不到就停止生图并报缺图，
    **禁止静默回退到旧的「通用会员卡片 + 模型画文字」纯文生图模板**。
  • 例外（需用户拍板）：外部充值、删除已上架商品、改已上架核心配置（含替换已上架商品主图）。

用法:
  python create_from_pno.py --acct 95425 --pno 26374            # 全自动驾驶：建+图+发+deploy
  python create_from_pno.py --acct 95425 --pno 26374 --dry      # 只预览，不写不发布
  python create_from_pno.py --acct 95425 --pno 26374 --nopublish # 建草稿+生图，不发布
  python create_from_pno.py --acct 95425 --pno 26374 --noimg    # 建+发，不重新生主图
  python create_from_pno.py --delete <draftId>
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

import agiso_direct as A
import alds_dict as D          # 详情/直充类型推断（2026-11-15 发布前置闸使用）
import replica_main_image as R   # 🔴 复刻式生图固定入口（范式库 §七·八，2026-11-14 固化）

# 🔴 2026-11-14 模块化：货源解析 / 主图 / 媒体上传 / 商品读取 已收口到 alds_kit，
# 本文件只剩「建品编排」（算 payload → 建草稿 → 发布 → 拼 spec → 调 deploy）。
# 旧函数名全部保留为别名，外部脚本（_replace_main_1425 / _probe_template_gid）不受影响。
from alds_kit import supplier as _supplier
from alds_kit import main_image as _main_image
from alds_kit.item import item_of as _item_of, ok
from alds_kit.supplier import (find_product, product_family, skus_from_family,
                               tier_val as _tier_val)
from alds_kit.main_image import (gen_and_set_main_image, gen_main_prompt,
                                 set_main_image, strip_template_images,
                                 get_kuaipao_key)

HERE = os.path.dirname(os.path.abspath(__file__))
PROFIT = 0.066                      # 与 deploy.py DEFAULT_PROFIT 一致：售价 = 成本 / 0.934
# 2026-11-12 草稿实测：搭子/伴游/地陪 → SECURITY_WARN_ERROR（地陪/伴游）。2026-11-12 用户定：命中即自改不反问。
RISK_WORDS = ('搭子', '伴游', '地陪', '陪练', '陪玩', '自动发货', '秒到账', '秒到', '秒充')
SERVER_FIELDS = ('id', 'createTime', 'modifyTime', 'failDesc', 'platformShopId', 'itemId')


def drafts():
    r = A._post('/api/GoodsManage/SearchDraftGoodsList', {'pageIndex': 1, 'pageSize': 50})
    return (((r.get('data') or {}).get('data') or {}).get('items') or [])


def delete_draft(did):
    return A._post('/api/GoodsManage/DeleteDraft', {'ids': [did]})


def clean_title(name, override=''):
    t = override or name
    removed = [w for w in RISK_WORDS if w in t]
    for w in RISK_WORDS:
        t = t.replace(w, '')
    t = re.sub(r'\s{2,}', ' ', t).strip()
    if len(t.encode('utf-8')) > 90:
        t = t.encode('utf-8')[:90].decode('utf-8', 'ignore')
    return t, removed


def build_payload(prod, acct, pno, template, args):
    """以草稿/现有商品为模板，替换标题、价格、描述，生成 InsertDraft payload。"""
    p = {k: v for k, v in template.items() if k not in SERVER_FIELDS}
    title, removed = clean_title(str(prod.get('productTitle', '')), args.title)
    cost = float(prod.get('productCost') or 0)
    if cost <= 0:
        raise RuntimeError('pno=%s 成本读不到（productCost=%s），拒绝发布' % (pno, cost))
    price = float(args.price) if args.price else round(cost / (1 - PROFIT), 2)
    if price < cost:
        raise RuntimeError('售价 %.2f < 进价 %.2f，触发 NO_LOSS 硬闸' % (price, cost))

    p.update({
        'title': title,
        'desc': args.desc or ('%s，官方渠道发货。下单后按页面提示填写必要信息，'
                              '虚拟商品非实物，账号填写错误造成的问题由买家承担。' % title),
        'reservePrice': '%.2f' % price,
        'originalPrice': '%.2f' % price,
        'outerId': args.outer_id or ('%s-%s' % (acct, pno)),
        'itemId': 0,
        'itemSkuList': [],
        'pvList': [],
        'quantity': 9999,
        'virtual': True,
        'timedPublish': False,
        'virtualGameGoods': False,
    })
    # 服务端硬校验：divisionIdList 必须是完整 3 级
    if len(p.get('divisionIdList') or []) != 3:
        p['divisionIdList'] = ['130000', '130300', '130304']
    return p, {'title': title, 'risk_words_removed': removed, 'cost': cost,
               'price': price, 'productType': prod.get('productType')}


# 档位切分（tier_val / family_stem / product_family）已迁到 alds_kit.supplier

def title_from_plan(prod, family, args):
    """按**在售档位**生成标题：默认只写最高档（highest），可显式铺全档（all）。

    🔴 2026-11-15（用户定）：标题档位摘要与主图档位同口径 —— 默认最高档。
    旧行为直接把货源标题当标题，货源名里的档位（如「1个月」）会与实际在售档位不符；
    多档时又把全部档位塞进标题。现在统一由 `deploy._copy_title` 按 plan 生成，plan 已过成本闸。
    """
    import deploy as DP
    kind = 'recharge' if int(prod.get('productType') or 0) == 1 else 'kaomi'
    # 用 with_cost=True 先取成本：resolve_skus 再取一次容易撞上货源限流返回 None 而整批中止。
    skus = skus_from_family(family, args.pno, with_cost=True)
    if not skus:
        return ''
    usable, skipped = [], []
    for s in skus:
        # 成本读不到的档不参与标题档位判断（不发它，也就不该写进标题）
        (usable if s.get('cost') is not None else skipped).append(s)
    if skipped:
        print('  [标题] 成本读不到，档位不参与标题：%s'
              % "、".join(str(s.get('val')) for s in skipped))
    if not usable:
        return ''
    plan = DP.resolve_skus({'skus': usable}, args.acct, PROFIT, kind)
    if not plan:
        return ''
    name = DP.clean_goods_name(str(prod.get('productTitle') or ''))
    # 货源名本身常带一档（「…尊贵会员1个月」），不剥掉会和档位摘要重复成「1个月 12个月」
    for _v in sorted({str(p.get('val') or '') for p in plan}, key=len, reverse=True):
        if _v and name.endswith(_v):
            _stripped = name[: -len(_v)].rstrip(' ·-|/')
            if _stripped:
                name = _stripped
            break
    return DP._copy_title(name, plan, kind != 'recharge', '',
                          getattr(args, 'title_sku_mode', 'highest'))


def emit_spec(meta, acct, pno, item_id, family=None, title='', desc='', additional='',
              main_image='keep', main_ref='', account_label='', template_img_url='',
              main_image_sku_mode='highest', recharge_types=None, buyer_field='',
              title_sku_mode='highest', preview=False):
    """输出可喂给 deploy.py 的 spec；默认带出产品线全档（多 SKU，不是单档）。

    🔴 2026-11-14 模块化：主图不再是「建品脚本自己干活」，而是写进 spec 交给
    deploy 的 ⑭ 环节执行（与 ID 链路同一段代码）。这样「主图该怎么画」只有一处，
    建品链路和按 ID 上 SKU 链路不会再各修一次。
      main_image=replica → ⑭ 复刻式重做 + 清模板占位图
      main_image=skip    → 不碰图（--noimg / dry）
    """
    kind = 'recharge' if meta['productType'] == 1 else 'kaomi'
    # 🔴 2026-11-14 收口：档位列表由 supplier.skus_from_family 唯一生成（与 ID 链路的
    #    supplier.build_skus 同一实现）；with_cost=False 保持「价格留空让 deploy 现场取」，
    #    不把可能过期的清单价写死进 spec。
    skus = skus_from_family(family, pno, with_cost=False)
    if not skus:
        skus = [{'val': str(pno), 'pno': str(pno)}]
    spec = {
        'goods': str(item_id) if item_id else '',
        'kind': kind,
        'acct': int(acct),
        # 主图参考图的身份键固定使用用户给出的目标 pno；SKU 全档列表不能改写这个键。
        'pno': str(pno),
        'property': '档位',
        'skus': skus,
        'allow_no_detail_text': True,   # 新建宝贝常无详情 OCR，放行以免 deploy 中止
        '_note': ('由 create_from_pno.py 生成；档位=产品线全档（价格留空让 deploy.py 按 6.6% 算）；'
                  'goods 为空表示尚未发布，发布后填入再跑 deploy.py'),
    }
    if title:
        spec['title'] = title
    if desc:
        spec['desc'] = desc
    if additional:
        spec['additional'] = additional
    if main_image and main_image != 'keep':
        spec['main_image'] = main_image
    if main_image_sku_mode != 'highest':
        spec['main_image_sku_mode'] = main_image_sku_mode
    # 标题档位模式随 spec 落盘：ID 链路调 deploy 时也按同口径生成标题
    if title_sku_mode and title_sku_mode != 'highest':
        spec['title_sku_mode'] = title_sku_mode
    if main_ref:
        spec['main_ref'] = main_ref
    if account_label:
        spec['account_label'] = account_label
    if template_img_url:
        spec['template_img_url'] = template_img_url
    # 买家填写文案走唯一出口（规则在 replica_main_image，supplier 只是取用）
    if kind == 'recharge':
        _bf = _supplier.buyer_field_of(pno, acct)
        if buyer_field:
            spec['buyer_field'] = buyer_field
        elif _bf.get('field'):
            spec['buyer_field'] = _bf['field']
        # 🔴 2026-11-15：直充账号类型随 spec 落盘，避免 ⑩ 现场推断失败后静默跳过（⑤ 报红）。
        #    显式传入优先；否则用调用方已解析出的 types。
        if recharge_types:
            spec['recharge_types'] = list(recharge_types)
            spec['var_key'] = spec.get('var_key') or 'account'
            spec['var_name'] = spec.get('var_name') or '充值账号'
    # 🔴 2026-11-15：`--dry` 只写 spec_preview_<pno>.json，**绝不覆盖** deploy 正在用的
    #    spec_from_pno_<pno>.json。实测教训：dry 预览把生产 spec 的 goods/main_ref/desc 冲掉，
    #    后续 phase_copy/phase_main_image 全部失效（读不到商品 + 抛 ReplicaRefMissing）。
    fname = ('spec_preview_%s.json' if preview else 'spec_from_pno_%s.json') % pno
    out = os.path.join(HERE, fname)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    return out


# 发布被拦截时二次激进剔除的候选词（含已知风控 + 常见敏感词，不在标题里出现也安全）
AGGRO_WORDS = ('搭子', '伴游', '地陪', '自动发货', '秒到', '秒充', '代充', '代购',
               '黄牛', '私下', '微信', '加我', '联系方式', '兼职', '引流', '刷单',
               '返利', '佣金', '离线', '秒回', '24h', '24小时')


# 🔴 主图能力（get_kuaipao_key / gen_main_prompt / set_main_image / strip_template_images /
#    gen_and_set_main_image）已迁到 alds_kit.main_image（2026-11-14 模块化收敛），
#    本文件顶部 import 保留同名，外部调用不变。

def _aggressive_title(title):
    t = title
    for w in AGGRO_WORDS:
        t = t.replace(w, "")
    return re.sub(r"\s{2,}", " ", t).strip()


def insert_draft_with_retry(payload, max_try=2):
    """建草稿；被标题/安全风控拦截时自动重写标题重试一次。返回 (resp, err, final_title)。"""
    final_title = payload.get("title", "")
    last_err = None
    for i in range(max_try):
        r = A._post("/api/GoodsManage/InsertDraft", payload)
        if ok(r):
            return r, None, final_title
        msg = json.dumps(r, ensure_ascii=False)
        last_err = msg
        if i < max_try - 1 and any(k in msg for k in
                                   ("SECURITY", "违规", "搭子", "伴游", "地陪", "标题", "敏感", "风控", "安全")):
            print("     ⚠️ 写入被拦截，自动重写标题重试: " + msg[:160])
            final_title = _aggressive_title(final_title)
            payload = dict(payload)
            payload["title"] = final_title
            continue
        break
    return None, last_err, final_title


def _find_item_id_by_title(title):
    """发布结果不回 itemId；改为按标题在售检索拿 goodsId。"""
    g = A.search_goods(title) or {}
    items = ((g.get('data') or {}).get('data') or {}).get('items') or []
    t = str(title).replace(' ', '')
    for x in items:
        if str(x.get('goodsName') or '').replace(' ', '') == t:
            return str(x.get('goodsId'))
    for x in items:
        if t in str(x.get('goodsName') or ''):
            return str(x.get('goodsId'))
    return None


def _resolve_published_id(payload, title, data):
    i = _extract_item_id(data)
    if i:
        return i
    return _find_item_id_by_title(payload.get('title') or title)


def do_publish_with_retry(did, payload, title, timeout=90):
    """发布；被标题/安全风控拦截时，激进清洗标题 → 删草稿重插 → 重发一次。返回 item_id。"""
    data, _ = publish(did, timeout)
    item_id = _resolve_published_id(payload, title, data)
    if item_id:
        return item_id
    msg = json.dumps(_, ensure_ascii=False)
    if any(k in msg for k in ("SECURITY", "违规", "搭子", "伴游", "地陪", "标题", "敏感", "风控", "安全")):
        print("     ⚠️ 发布被拦截，自动重写标题重发: " + msg[:160])
        new_title = _aggressive_title(title)
        delete_draft(did)
        p2 = dict(payload)
        p2["title"] = new_title
        r2, err2, _ = insert_draft_with_retry(p2)
        if not r2:
            print("     ⚠️ 重插失败: " + str(err2)[:200])
            return None
        did2 = None
        for x in drafts():
            if str(x.get("outerId")) == str(p2.get("outerId")):
                did2 = x.get("id")
                break
        if not did2:
            return None
        data2, _ = publish(did2, timeout)
        return _resolve_published_id(p2, new_title, data2)
    return item_id


def _extract_item_id(data):
    if isinstance(data, dict):
        return data.get("itemId") or data.get("goodsId")
    if isinstance(data, str) and data.isdigit():
        return data
    return None


def draft_fail_desc(draft_id):
    """回读草稿上的失败原因（发布失败时服务端把原因写在 failDesc）。"""
    for x in drafts():
        if str(x.get('id')) == str(draft_id):
            return x.get('failDesc')
    return None


def publish(draft_id, timeout=90):
    r = A._post('/api/GoodsManage/PublishDraft', {'ids': [draft_id]})
    if not ok(r):
        return None, r
    code = ((r.get('data') or {}).get('data') or '')
    print('PublishDraft -> code =', code)
    deadline = time.time() + timeout
    last = r
    while time.time() < deadline and code:
        time.sleep(3)
        res = A._post('/api/GoodsManage/GetPublishDraftResult/' + str(code), {})
        last = res
        # 🔴 2026-11-13 修：外层 res['data']['isSuccess'] 只表示「查询请求成功」，
        #    **不是**「发布成功」。真正的结果在内层 res['data']['data']：
        #    successCount>0 才算发布成功，failCount>0 表示失败，
        #    两者都是 0 说明还在异步处理中（processStatus=false），必须继续轮询。
        #    旧代码误用外层 isSuccess → 第一次轮询就返回 successCount=0 → 拿不到 itemId，
        #    还把「还在处理中」误报成「发布失败」。
        outer = res.get('data') or {}
        inner = outer.get('data') or {}
        if not isinstance(inner, dict):
            inner = {}
        sc = int(inner.get('successCount') or 0)
        fc = int(inner.get('failCount') or 0)
        if sc > 0:
            print('  发布成功 successCount=%s' % sc)
            return inner, res
        if fc > 0:
            fd = draft_fail_desc(draft_id)
            print('  ❌ 发布失败 successCount=0 failCount=%s' % fc)
            if fd:
                print('  失败原因(failDesc):', fd)
            res = dict(res)
            res['_failDesc'] = fd
            return None, res
        print('  轮询: 处理中...', json.dumps(inner, ensure_ascii=False)[:160])
        if '过期' in str(outer.get('errorMsg')) or '过期' in str(inner.get('errorMsg')):
            break
    fd = draft_fail_desc(draft_id)
    if fd:
        print('  ❌ 发布未成功，草稿 failDesc:', fd)
        last = dict(last)
        last['_failDesc'] = fd
    return None, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--acct', type=int, default=95425, help='供货商账号 idNo（志远 95425 / 思券 99569）')
    ap.add_argument('--pno', help='货源商品编号，如 26374')
    ap.add_argument('--keyword', default='', help='缩小货源目录搜索的关键词；留空=全量翻页')
    ap.add_argument('--title', default='', help='覆盖自动标题')
    ap.add_argument('--desc', default='', help='覆盖自动描述')
    ap.add_argument('--additional', default='', help='覆盖 SKU 发货说明（写入 deploy spec）')
    ap.add_argument('--price', default='', help='覆盖默认售价（成本/0.934）')
    ap.add_argument('--outer-id', default='', help='商品编码，默认 <acct>-<pno>')
    ap.add_argument('--template-gid', default='', help='从该现有商品取类目/图片模板（默认用草稿箱最近草稿）')
    ap.add_argument('--delete', default='', help='删除指定草稿 id 后退出')
    ap.add_argument('--dry', action='store_true', help='只预览 payload 与 spec，不写不发布不生图')
    ap.add_argument('--go', action='store_true', help='执行（建草稿）。与 --dry 互斥，默认等效 --go')
    ap.add_argument('--nopublish', action='store_true', help='只建草稿+生图，不发布到闲鱼')
    ap.add_argument('--noimg', action='store_true', help='跳过快跑生主图（沿用模板图）')
    ap.add_argument('--ref', default='', help='复刻式生图参考图（本地路径或 URL），优先级最高；'
                                              '留空则取固定素材库中该 pno 的货源商品图')
    ap.add_argument('--account-label', default='',
                    help='人工指定买家填写文案（如「手机号」「华为账号」），覆盖自动解析；'
                         '货源原文没写清时用它兜底')
    ap.add_argument('--recharge-types', default='',
                    help='人工指定直充账号类型，逗号分隔数字（1手机 2固话 4平台账号 8QQ 16微信 32邮箱 128剪映号 256抖音ID）；'
                         '留空则按货源参数模板+介绍文字+图片OCR自动推断，推断不出会在发布前中止')
    ap.add_argument('--allow-default-desc', action='store_true',
                    help='允许在上游无文字素材且未给 --desc 时使用草稿默认描述（默认禁止：会停在 78 字缺档位对照）')
    ap.add_argument('--title-sku-mode', choices=('highest', 'all'), default='highest',
                    help='标题档位摘要模式：默认 highest（只写在售最高档）；all 写全部在售档位')
    ap.add_argument('--main-image-sku-mode', choices=('highest', 'all'), default='highest',
                    help='主图档位展示模式：默认 highest（出售中最高档）；all 展示上架的全部档位并提醒')
    args = ap.parse_args()

    if args.delete:
        print('DeleteDraft:', json.dumps(delete_draft(args.delete), ensure_ascii=False)[:400])
        return
    if not args.pno:
        ap.error('必须给 --pno（或 --delete <id>）')

    prod, all_products = find_product(args.acct, args.pno, args.keyword)
    family = product_family(prod, all_products, args.pno)
    print('货源命中:', json.dumps(prod, ensure_ascii=False)[:300])
    print('同账号目录条数:', len(all_products), '｜ productType 1=官方直充 2=卡密')
    print('同产品线全档:', len(family), [(x.get('productNo'), x.get('productTitle')) for x in family][:10])

    # 🔴 2026-11-13 停售前置闸：目标货源或同线档位暂停销售 → 不上架，避免买家付款发不出货。
    _tgt_state = A.supplier_allowed(args.acct, args.pno)
    if _tgt_state is False:
        print('\n❌ 目标货源 pno=%s 已暂停销售（isAllowPurchase=false），整件中止，未做任何上架。' % args.pno)
        return
    _susp = [x.get('productNo') for x in family if A.supplier_allowed(args.acct, x.get('productNo')) is False]
    if _susp:
        print('⚠️ 已剔除暂停销售的同线档位（不上架）：', _susp)
        family = [x for x in family if A.supplier_allowed(args.acct, x.get('productNo')) is not False]
    if not family:
        print('\n❌ 同产品线全部档位均暂停销售，整件中止，未做任何上架。')
        return

    if args.template_gid:
        it = A.get_item(args.template_gid)
        tpl = ((it.get('data') or {}).get('data') or {})
        tpl['imgList'] = [{'imgUrl': u} for u in (tpl.get('imgUrls') or [])[:1]]
        tpl.setdefault('categoryName', '')
        tpl.setdefault('spBizType', '25')
        tpl.setdefault('categoryId', 50025461)
        tpl.setdefault('channelCatId', '35d467e7358057b0a7f7e02f36b0b49a')
        tpl.setdefault('divisionIdList', ['130000', '130300', '130304'])
        tpl.setdefault('itemBizType', 2)
        tpl.setdefault('logisticsMode', 4)
        tpl.setdefault('stuffStatus', 0)
        tpl.setdefault('tradeType', 0)
        tpl.setdefault('templateId', 0)
        tpl.setdefault('transportFee', '0')
        tpl.setdefault('divisionId', 0)
        tpl.setdefault('onlyTaskSelf', False)
    else:
        ds = drafts()
        # 🔴 只挑字段完整的草稿当模板：Publish 失败会写一条 title=None 的空草稿，
        #    拿它当模板会得到 categoryId=0 / imgList=[] 的废 payload。
        good = [x for x in ds if x.get('title') and (x.get('categoryId') or 0) > 0
                and (x.get('imgList') or [])]
        if not good:
            raise RuntimeError('草稿箱没有字段完整的模板；请给 --template-gid')
        tpl = good[0]
        print('模板草稿:', tpl.get('id'), '|', tpl.get('title'))

    # 🔴 2026-11-15：标题档位摘要按「在售档位」生成，默认最高档（用户定）。
    #    必须在 build_payload 之前定标题，让 InsertDraft 一次就发对，不靠发布后再改名。
    if not (args.title or '').strip():
        try:
            _auto_title = title_from_plan(prod, family, args)
            if _auto_title:
                args.title = _auto_title
                print('按在售档位生成标题（%s）: %s' % (args.title_sku_mode, _auto_title))
        except SystemExit:
            print('⚠️ 标题档位推断中止（成本无法核实），沿用货源标题')
        except Exception as _e:
            print('⚠️ 标题档位推断失败（%s），沿用货源标题' % _e)

    payload, meta = build_payload(prod, args.acct, args.pno, tpl, args)
    # 🔴 模板法必带一张模板商品首图当占位（发布要求 ≥1 图），记下它，发布+置顶后精确删除
    template_img_url = ((tpl.get('imgUrls') or tpl.get('imgList') or [''])[0] or '')
    if isinstance(template_img_url, dict):
        template_img_url = template_img_url.get('imgUrl') or ''
    print()
    print('生成 payload（%d 字段）:' % len(payload))
    print('  title       :', meta['title'])
    if meta['risk_words_removed']:
        print('  ⚠️ 已剔除风控词:', meta['risk_words_removed'])
    print('  成本 / 售价 : %.3f / %.2f' % (meta['cost'], meta['price']))
    print('  kind(推算)  :', 'recharge' if meta['productType'] == 1 else 'kaomi')
    print('  categoryId  :', payload.get('categoryId'), '| channelCatId:', payload.get('channelCatId'))
    print('  outerId     :', payload.get('outerId'))
    print('  imgList     :', json.dumps(payload.get('imgList'), ensure_ascii=False)[:220])

    # 🔴 2026-11-15 发布前置闸：把「事后巡检才发现」的两个缺口提前到发布之前。
    #    背景：26652 一轮跑完 exit_code=0 但 ⑦（78 字默认描述）与 ⑤（直充类型未开）双红，
    #    商品已上线成残品，只能事后返工。此处宁可停下，不发残品。
    _kind = 'recharge' if meta['productType'] == 1 else 'kaomi'
    _detail = {}
    try:
        _detail = D.detail(args.pno, args.acct) or {}
    except Exception as _e:
        print('⚠️ 详情读取失败（%s），按「无文字素材」处理' % _e)
    # 🔴 2026-11-15：把图片识别结果（detail_ocr/<pno>.txt，由 Agent 多模态写入）并入判定素材。
    #    需求原话：「充值账号看商品主图和介绍里面需要客户填写什么」。介绍是图片时只有 OCR 能拿到。
    _ocr_path = os.path.join(HERE, 'detail_ocr', '%s.txt' % args.pno)
    if os.path.exists(_ocr_path):
        try:
            _ocr = open(_ocr_path, encoding='utf-8').read().strip()
        except Exception:
            _ocr = ''
        if _ocr:
            _detail['_ocr'] = _ocr
            print('  已载入图片识别结果 detail_ocr/%s.txt（%d 字）' % (args.pno, len(_ocr)))
    _dtext = ''
    for _k in ('goodsDescribe', 'text', 'notice', '_ocr'):
        _v = _detail.get(_k)
        if isinstance(_v, str):
            _dtext += _v
    _dtext = _dtext.strip()

    # ① 描述闸：上游文字素材不足以生成≥100字含【档位对照】的描述 + 未给 --desc → 必红
    #    判据不是「完全无文字」：26652 的 goodsDescribe 只有「24小时官方充值｜1-10分钟到账」15 字，
    #    非空但远不够撑起七段文案，auto_copy 会产出缺【档位对照】的短文。故按长度判定。
    DESC_MIN_MATERIAL = 60
    _desc_missing = (not (args.desc or '').strip()) and len(_dtext) < DESC_MIN_MATERIAL
    # ② 直充类型闸：推断不出 + 未显式给 → ⑩ 会跳过，⑤ 必红
    _types = []
    if (args.recharge_types or '').strip():
        try:
            _types = [int(x) for x in args.recharge_types.replace('，', ',').split(',') if x.strip()]
        except ValueError:
            raise SystemExit('--recharge-types 只能是逗号分隔的数字，收到：%r' % args.recharge_types)
        _types_note = '命令行显式指定'
    else:
        _types, _types_note = D.recharge_types_from_detail(_detail)
        _types = _types or []
    # 🔴 2026-11-15：识别出的类型自动转成买家填写文案，供主图印「下单填写X」与描述【填写内容】。
    #    显式 --account-label 优先；否则用类型推断结果（手机号/平台账号/账号ID…）。
    _buyer_label = (args.account_label or '').strip() or D.buyer_label_for(_types)
    _types_missing = _kind == 'recharge' and not _types

    print()
    print('── 发布前置闸 ──')
    print('  详情文字素材 : %s' % (('%d 字%s' % (len(_dtext), '' if len(_dtext) >= DESC_MIN_MATERIAL
                                                   else '（不足 %d 字）' % DESC_MIN_MATERIAL))
                                    if _dtext else '无（纯图片/空）'))
    print('  描述来源     : %s' % ('--desc 手写' if (args.desc or '').strip() else
                                  ('将由 auto_copy 依详情生成' if len(_dtext) >= DESC_MIN_MATERIAL
                                   else '❌ 无足够素材（会停在默认 78 字、缺【档位对照】）')))
    if _kind == 'recharge':
        print('  直充账号类型 : %s' % (('%s（%s）' % (_types, _types_note)) if _types
                                      else '❌ 未推断出，且未显式指定'))
        print('  买家填写项   : %s' % (_buyer_label or '（未识别，主图不印填写句）'))
    _blocked = []
    if _desc_missing and not args.allow_default_desc:
        _blocked.append('描述：上游无文字素材且未给 --desc（会停在默认 78 字、缺【档位对照】）'
                        ' → 补 --desc，或加 --allow-default-desc 明确接受默认描述')
    if _types_missing:
        _blocked.append('直充账号类型：推断不出买家要填什么 → 给 --recharge-types'
                        '（1手机 2固话 4平台账号 8QQ 16微信 32邮箱 128剪映号 256抖音ID）'
                        '，或 --account-label 说明填写项')
    if _blocked:
        if args.dry:
            print('\n⚠️ [dry] 以下问题会导致 --go 被中止：')
            for b in _blocked:
                print('   · ' + b)
        else:
            print('\n❌ 已中止（未建草稿、未发布、未做任何线上改动）：')
            for b in _blocked:
                print('   · ' + b)
            print('\n补齐后重跑同一条命令即可。')
            return
    else:
        print('  ✅ 通过')

    if args.dry:
        print('\n[dry] 只预览，不写不发布不生图。去掉 --dry 即全自动：建草稿→生图→发布→deploy。')
        print('spec 预览:', emit_spec(meta, args.acct, args.pno, '', family,
                                  title=args.title, desc=args.desc, additional=args.additional,
                                  recharge_types=_types, buyer_field=_buyer_label,
                                  account_label=_buyer_label,
                                  main_image_sku_mode=args.main_image_sku_mode,
                                  title_sku_mode=args.title_sku_mode,
                                  preview=True))
        return

    r, err, final_title = insert_draft_with_retry(payload)
    print('\nInsertDraft ->', 'OK' if r else ('失败: ' + str(err)[:400]))
    if not r:
        print('失败，按 errorMsg 修字段；未产生任何商品。')
        return
    meta['title'] = final_title
    did = None
    for x in drafts():
        if str(x.get('outerId')) == str(payload.get('outerId')):
            did = x.get('id')
            break
    print('草稿 id =', did)
    if not did:
        print('⚠️ 未回读到草稿，请手工检查草稿箱。')
        return

    item_id = None
    if not args.nopublish:
        item_id = do_publish_with_retry(did, payload, final_title)
        print('发布结果: itemId =', item_id)
        if not item_id:
            fd = draft_fail_desc(did)
            if fd:
                print('❌ 发布失败原因:', fd)
                if '类目' in str(fd):
                    print('   → 类目校验不通过：换一个 categoryId/channelCatId 结构的模板商品再试'
                          '（--template-gid），或给该货源单独建一条类目线路。')
            else:
                print('⚠️ 发布未拿到 itemId，草稿留箱待查；先用 --noimg 跑 deploy 也可。')
    else:
        print('只建草稿、未发布（--nopublish）。草稿箱可人工核对，删除用 --delete <id>。')

    out = emit_spec(meta, args.acct, args.pno, item_id, family,
                    title=args.title, desc=args.desc, additional=args.additional,
                    main_image=('replica' if (item_id and not args.noimg) else 'skip'),
                    main_ref=args.ref, account_label=_buyer_label,
                    template_img_url=template_img_url,
                    main_image_sku_mode=args.main_image_sku_mode,
                    title_sku_mode=args.title_sku_mode,
                    recharge_types=_types, buyer_field=_buyer_label)
    print('spec →', out)

    if item_id:
        print('\n[deploy] 自动接一条龙（--go 真写）...')
        deploy_py = os.path.join(HERE, 'deploy.py')
        dr = subprocess.run([sys.executable, deploy_py, out, '--go'],
                            capture_output=True, text=True, timeout=900,
                            encoding='utf-8', errors='replace')
        print(dr.stdout[-2500:] if len(dr.stdout) > 2500 else dr.stdout)
        if dr.stderr.strip():
            print('[deploy stderr]', dr.stderr[-800:])
        # 🔴 2026-11-14：主图不再在这里做 —— 已写进 spec.main_image，由 deploy ⑭ 执行
        #    （与按 ID 上 SKU 链路同一段代码，避免「建品修好了、ID 链路没修」）
        print('下一步核对: python onepipe_guard.py --inspect')
    else:
        print('发布拿到 itemId 后填入 spec.goods 再跑 deploy.py。')


if __name__ == '__main__':
    main()
