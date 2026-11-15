# -*- coding: utf-8 -*-
"""重构回归对比：旧版（_bak_20261114/create_from_pno.py）vs 新版（能力层 alds_kit）。

只比纯逻辑（档位解析 / 产品线 / payload 组装），不联网络、不写线上。
用法：python _test_alds_kit.py
"""
import importlib.util
import sys
import types
import os

import agiso_direct as A

HERE = os.path.dirname(os.path.abspath(__file__))

FAKE = [
    {'productNo': 165, 'productTitle': '优酷会员『7天』直充', 'productCost': 6.5, 'productType': 1},
    {'productNo': 166, 'productTitle': '优酷会员『1个月』直充', 'productCost': 13.8, 'productType': 1},
    {'productNo': 167, 'productTitle': '优酷会员『3个月』直充', 'productCost': 38.0, 'productType': 1},
    {'productNo': 170, 'productTitle': '爱奇艺『月卡』限价25.8', 'productCost': 9.9, 'productType': 1},
    {'productNo': 171, 'productTitle': '知乎盐选会员1个月', 'productCost': 11.0, 'productType': 2},
]
A.get_supplier_products = lambda *a, **k: FAKE

TPL = {
    'title': 'x', 'desc': 'x', 'categoryId': 50025461,
    'channelCatId': '35d467e7358057b0a7f7e02f36b0b49a',
    'divisionIdList': ['130000', '130300', '130304'],
    'imgList': [{'imgUrl': 'https://a/b.png'}], 'imgUrls': ['https://a/b.png'],
    'reservePrice': '1.00', 'originalPrice': '1.00', 'quantity': 10,
}
ARGS = types.SimpleNamespace(title='', desc='', price='', outer_id='', template_gid='')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def main():
    new = load(os.path.join(HERE, 'create_from_pno.py'), 'new_cfp')
    old = load(os.path.join(HERE, '_bak_20261114', 'create_from_pno.py'), 'old_cfp')
    bad = 0

    print('== 档位解析 tier_val')
    for t in [x['productTitle'] for x in FAKE] + ['魔音工坊VIP标准版『月卡』', '『月卡』…限价25.8',
                                                  '标价1元 30天', '永久']:
        a, b = new._tier_val(t), old._tier_val(t)
        okk = a == b
        bad += 0 if okk else 1
        print('  %-28s new=%-8s old=%-8s %s' % (t, a, b, 'OK' if okk else '❌'))

    print('== 产品线 product_family')
    for pno in (165, 166, 170, 171):
        prod = [x for x in FAKE if x['productNo'] == pno][0]
        a = [(x['productNo'], new._tier_val(x['productTitle'])) for x in new.product_family(prod, FAKE, pno)]
        b = [(x['productNo'], old._tier_val(x['productTitle'])) for x in old.product_family(prod, FAKE, pno)]
        okk = a == b
        bad += 0 if okk else 1
        print('  pno=%-4s new=%-40s old=%-40s %s' % (pno, a, b, 'OK' if okk else '❌'))

    print('== payload 组装 build_payload')
    for pno in (165, 170, 171):
        prod = [x for x in FAKE if x['productNo'] == pno][0]
        a, ma = new.build_payload(prod, 95425, str(pno), dict(TPL), ARGS)
        b, mb = old.build_payload(prod, 95425, str(pno), dict(TPL), ARGS)
        # 🔴 2026-11-15：地区改为「随机省会」（用户定），每次结果不同，
        #    新旧等价性比对必须排除这两个字段，否则每跑一次都报差异。
        #    地区正确性由 tests/test_divisions.py 单独保证。
        _DIV_KEYS = ('divisionId', 'divisionIdList')
        a_cmp = {k: v for k, v in a.items() if k not in _DIV_KEYS}
        b_cmp = {k: v for k, v in b.items() if k not in _DIV_KEYS}
        okk = (a_cmp == b_cmp) and (ma == mb)
        bad += 0 if okk else 1
        print('  pno=%-4s 售价=%-6s 标题=%-24s %s' % (
            pno, ma['price'], ma['title'], 'OK' if okk else '❌ 差异'))
        if not okk:
            for k in set(a_cmp) | set(b_cmp):
                if a_cmp.get(k) != b_cmp.get(k):
                    print('      字段 %s: new=%r old=%r' % (k, a_cmp.get(k), b_cmp.get(k)))

    print('== find_product 找不到时的报错文本')
    try:
        new.find_product(95425, '999')
    except RuntimeError as e:
        print('  ', str(e)[:70])
        bad += 0 if '找不到 pno=999' in str(e) else 1

    print('\n=== 差异项 = %d %s' % (bad, '✅ 全部一致' if not bad else '❌ 需修复'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
