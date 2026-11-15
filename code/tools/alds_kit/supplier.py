# -*- coding: utf-8 -*-
"""supplier —— 货源解析（唯一实现）。

收口三处逻辑（2026-11-14）：
  · create_from_pno._tier_val / _family_stem / product_family / find_product
  · replica_main_image.lookup_supplier（固定素材库）
  · deploy._detail_cache + resolve_buyer_field（现场 GetDetail）

🔴 买家字段的双来源必须显式选，不许隐式混合：
  · 现场（推荐）：detail 来自 alds_dict.detail()，是当前真实配置；
  · 素材库（回落）：固定素材库里 2026-11-04 的快照，可能已过期。
  两者解析规则完全相同（都用 replica_main_image.resolve_buyer_field），
  区别只在数据来源 —— 由调用方决定，本模块不猜。
"""
import re

import agiso_direct as A
import replica_main_image as R

# 档位单位词表：优先「数字+单位」，其次纯档位词
TIER_UNITS = r'(个月|年卡|月卡|周卡|天卡|季卡|星期卡|小时|天|年|月|周|次|张|点|积分|GB)'
TIER_PURE = r'(月卡|年卡|周卡|天卡|季卡)'


def tier_val(title):
    """从货源标题里抽档位值。

    规则（2026-11-13 修，勿回退）：
      ① 优先在『』书名号内找 ——「魔音工坊VIP标准版『月卡』」→「月卡」
      ② 其次找「数字+单位」——「知乎盐选会员1个月」→「1个月」
      ③ 最后才用旧的宽松正则兜底
    🔴 旧实现只认「数字+单位」，遇到「档位在前、限价在后」的标题（如
       「『月卡』…限价25.8」）会抽成 "25"——把限价当档位名，SKU 档位全错。
    """
    t = str(title)
    m = re.search(r'『([^』]+)』', t)
    if m:
        inner = m.group(1).strip()
        m2 = re.search(r'\d+\s*' + TIER_UNITS, inner)
        if m2:
            return m2.group(0).replace(' ', '')
        m3 = re.search(TIER_PURE, inner)
        if m3:
            return m3.group(1)
        if inner:
            return inner
    m2 = re.search(r'\d+\s*' + TIER_UNITS, t)
    if m2:
        return m2.group(0).replace(' ', '')
    m3 = re.search(TIER_PURE, t)
    if m3:
        return m3.group(1)
    m4 = re.search(r'\d+[\u4e00-\u9fa5A-Za-z]{0,4}', t)
    return m4.group(0) if m4 else None


def family_stem(title):
    """产品线前缀 = 标题里「档位标记」之前的稳定部分。

    🔴 2026-11-13 修：旧实现用 re.split(r'\\d')[0]，遇到「『月卡』…限价25.8」
       会把价格截进前缀 → 同产品线其他档位匹配不上。现同时看『』与第一个数字，取更早者。
    """
    t = str(title)
    cut = len(t)
    i = t.find('『')
    if i >= 0:
        cut = min(cut, i)
    m = re.search(r'\d', t)
    if m:
        cut = min(cut, m.start())
    return t[:cut]


def product_family(prod, all_products, target_pno=None):
    """同一产品线的全档：档位标记之前的标题前缀相同（不跨产品线）。
    去重：同一档位值（如两个「1个月」）只保留一个，优先保留用户指定的 pno。"""
    stem = family_stem(prod.get('productTitle', ''))
    fam = [x for x in all_products if str(x.get('productTitle', '')).startswith(stem)]
    ordered = sorted(fam, key=lambda x: (0 if str(x.get('productNo')) == str(target_pno) else 1,
                                         str(x.get('productNo'))))
    seen, out = {}, []
    for x in ordered:
        v = tier_val(x.get('productTitle'))
        if not v or v not in seen:
            seen[v] = x
            out.append(x)
    return sorted(out, key=lambda x: str(x.get('productNo')))


def find_product(acct, pno, keyword=''):
    """全量翻页找 pno（get_supplier_products 已内建翻页）；返回该货源商品记录。"""
    lst = A.get_supplier_products(acct, keyword) if keyword else A.get_supplier_products(acct)
    hit = [x for x in lst if str(x.get('productNo')) == str(pno)]
    if not hit:
        raise RuntimeError('在账号 %s 的货源目录里找不到 pno=%s（共 %d 条）' % (acct, pno, len(lst)))
    return hit[0], lst


def skus_from_family(family, target_pno=None, with_cost=True):
    """货源记录列表 → spec.skus（档位值 + pno + cost）。**纯函数，不联网**。

    同一档位值只留一个，优先用户指定的 target_pno（与 product_family 去重口径一致）。
    成本读不到就不写 cost 字段 —— 留给 deploy.resolve_skus 现场取，绝不填假数。
    with_cost=False 用于 create_from_pno 出 spec：宁可让 deploy 现场取价，
    也不把可能过期的清单价写死进 spec（清单是快照，成本每天会变）。
    """
    ordered = sorted(family or [],
                     key=lambda x: (0 if str(x.get('productNo')) == str(target_pno) else 1,
                                    str(x.get('productNo'))))
    seen, out = set(), []
    for x in ordered:
        v = tier_val(x.get('productTitle'))
        if not v or v in seen:
            continue
        seen.add(v)
        item = {'val': v, 'pno': str(x.get('productNo'))}
        c = x.get('productCost')
        if with_cost and c not in (None, ''):
            try:
                item['cost'] = float(c)
            except (TypeError, ValueError):
                pass
        out.append(item)
    return out


def resolve_family(acct, pno, keyword=''):
    """联网：pno → (货源记录, 同产品线全档列表)。唯一查档入口。"""
    prod, lst = find_product(acct, pno, keyword)
    return prod, product_family(prod, lst, pno)


def build_skus(acct, pno, explicit=None, keyword=''):
    """ID 链路专用：只给 acct + pno → 完整 skus（同产品线全档）。

    合并规则（2026-11-14 用户定「模块组装」的落地）：
      · 产品线里有的档 → 全部带上（val/pno/cost 自动补）
      · explicit 里写了同一档位 → **以 explicit 为准**（用户手写的价/成本不许被覆盖）
      · explicit 里有但产品线里没有的档 → 原样保留（可能是跨线自选）

    返回 (skus, meta)。meta 只用于打印，不参与决策。
    🔴 不做成本/售价闸门 —— 那是 deploy.resolve_skus 的职责，这里只负责「有哪些档」。
    🔴 **不从货源目录带 cost**：目录的 productCost 与真实进价口径不同
       （志远要乘 multiple、思券以 GetDetail 为准），带错会让亏本判据失效。
       成本一律交给 deploy 现场取（prefilter_spec_costs → D.cost）。
       用户在 explicit 里显式写的 cost 例外，那是人工确认过的值。
    """
    prod, family = resolve_family(acct, pno, keyword)
    base = skus_from_family(family, pno, with_cost=False)
    ex = {}
    for s in (explicit or []):
        if s.get('val'):
            ex[str(s['val'])] = {k: v for k, v in s.items() if v not in (None, '')}
    out = []
    for s in base:
        e = ex.pop(str(s['val']), None)
        out.append(dict(s, **(e or {})) if e else dict(s))
    for v in ex.values():
        out.append(dict(v))
    return out, {'product': prod, 'family_count': len(family),
                 'explicit_count': len(explicit or []), 'filled': len(out)}


def buyer_field_of(pno, acct=0, detail=None):
    """买家下单要填的具体项 → {field, kind, evidence, form, source}。

    两类合法空值（都不猜）：
      · form=卡密  → 买家无需填账号，主图不印「下单填写」句
      · kind=回落  → 货源原文没写清填什么，描述写「按页面提示填写」，主图不印

    detail 给了就用现场数据（alds_dict.detail 的 rechargeTemplates/text/notice），
    否则回落固定素材库快照。规则本身只在 replica_main_image 一份。
    """
    src = R.source_of(acct) if acct else ""
    info = R.lookup_supplier(pno, src) or {}
    out = {
        'field': '', 'kind': '', 'evidence': '', 'form': info.get('form') or '',
        'source': '素材库', 'img': info.get('img') or '', 'name': info.get('name') or '',
    }
    if detail:
        try:
            bf = R.resolve_buyer_field(detail.get('rechargeTemplates') or [],
                                       detail.get('text') or '',
                                       detail.get('notice') or '')
            out.update({'field': str(bf.get('field') or ''),
                        'kind': bf.get('kind') or '',
                        'evidence': bf.get('evidence') or '',
                        'source': '现场'})
            if bf.get('fallback'):
                out['field'] = ''
            return out
        except Exception as e:
            out['evidence'] = '现场解析失败：%s' % e
            return out
    if info.get('buyer_kind') in ('标识', '平台账号') and info.get('buyer_field'):
        out.update({'field': info['buyer_field'], 'kind': info['buyer_kind'],
                    'evidence': info.get('buyer_evidence') or ''})
    else:
        out.update({'kind': info.get('buyer_kind') or '回落',
                    'evidence': info.get('buyer_evidence') or ''})
    return out
