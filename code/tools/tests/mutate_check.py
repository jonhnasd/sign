# -*- coding: utf-8 -*-
"""变异测试：故意把代码改坏，确认 golden 会报错（测试如果从不报错就是摆设）。

只在进程内 monkeypatch，不改任何文件。跑完退出码 0 = 每个变异都被抓到。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import deploy as D
import replica_main_image as R
import run_golden as G


def run_once(label, want_fail=True):
    """跑一轮 golden，返回失败条数。want_fail=False 表示基线（期望 0 条）。"""
    G.FAIL[:] = []
    G.PASS[0] = 0
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        try:
            G.main()
        except Exception as e:
            G.FAIL.append('golden 运行异常：%s: %s' % (type(e).__name__, e))
    finally:
        sys.stdout = old
    n = len(G.FAIL)
    got = (n > 0) if want_fail else (n == 0)
    print('  %-34s → 失败 %d 条 %s' % (label, n, '✅ 符合预期' if got else '❌ 不符合预期'))
    if n and want_fail:
        for x in G.FAIL[:2]:
            print('        · %s' % x[:110])
    return n


def main():
    missed = 0
    print('基线（未改代码）')
    if run_once('原样', want_fail=False) != 0:
        missed += 1

    print('\nM1 买家字段退化成 popup 字段名（165 事故原状）')
    orig_rbf = R.resolve_buyer_field

    def bad_rbf(popup_fields, *texts):
        r = orig_rbf(popup_fields, *texts)
        fn = ((popup_fields or [{}])[0] or {}).get('title') or ''
        return dict(r, field=fn or r.get('field'), kind='字段名')
    R.resolve_buyer_field = bad_rbf
    try:
        if not run_once('图/文案印字段名'):
            missed += 1
    finally:
        R.resolve_buyer_field = orig_rbf

    print('\nM2 主图白名单混入参数名（禁用词溜进合成清单）')
    orig_wl = R.text_whitelist

    def bad_wl(*a, **k):
        return orig_wl(*a, **k) + ['充值账号']
    R.text_whitelist = bad_wl
    try:
        if not run_once('白名单含「充值账号」'):
            missed += 1
    finally:
        R.text_whitelist = orig_wl

    print('\nM3 定价回退到旧 3.5% 口径（÷0.965）')
    orig_rs = D.resolve_skus

    def bad_rs(spec, acct, profit, kind):
        return orig_rs(spec, acct, 0.035, kind)
    D.resolve_skus = bad_rs
    try:
        if not run_once('旧 3.5% 利润率'):
            missed += 1
    finally:
        D.resolve_skus = orig_rs

    print('\nM4 货源查询忽略 source，错误复用同 pno 的其他供应商图片')
    orig_lookup = R.lookup_supplier

    def bad_lookup(pno, source=''):
        return orig_lookup(pno, '')
    R.lookup_supplier = bad_lookup
    try:
        if not run_once('跨来源同 pno 错误复用'):
            missed += 1
    finally:
        R.lookup_supplier = orig_lookup

    print('\nM5 解析器信任 lookup 的身份标记，未二次核对 source+pno')
    orig_lookup = R.lookup_supplier

    def wrong_identity_lookup(pno, source=''):
        info = orig_lookup(pno, '')
        if info.get('found'):
            info = dict(info, identity_verified=True)
        return info
    R.lookup_supplier = wrong_identity_lookup
    try:
        if not run_once('身份标记伪造仍跨来源命中'):
            missed += 1
    finally:
        R.lookup_supplier = orig_lookup

    print('\nM6 缺参考图时静默回退到虚构通用图')
    orig_resolve = R.resolve_reference

    def bad_resolve(pno, acct, cli_ref='', *, validate=True):
        try:
            return orig_resolve(pno, acct, cli_ref, validate=validate)
        except R.ReplicaRefMissing:
            return {'ref_url': 'https://example.invalid/generic.png', 'ref_source': 'fallback',
                    'ref_acct': str(acct), 'ref_source_name': '', 'ref_pno': str(pno),
                    'match': 'fallback', 'evidence': 'bad fallback'}
    R.resolve_reference = bad_resolve
    try:
        if not run_once('缺图静默回退'):
            missed += 1
    finally:
        R.resolve_reference = orig_resolve

    print('\nM7 默认展示全部 SKU（应被 golden 抓住）')
    orig_select = R.select_sku_display

    def bad_select(item_skus, mode='highest'):
        return orig_select(item_skus, 'all')
    R.select_sku_display = bad_select
    try:
        if not run_once('默认最高档退化成全档'):
            missed += 1
    finally:
        R.select_sku_display = orig_select

    print('\nM8 全档位模式缺少提醒（应被 golden 抓住）')
    orig_select = R.select_sku_display

    def bad_all_reminder(item_skus, mode='highest'):
        result = orig_select(item_skus, mode)
        if result.get('mode') == 'all':
            result = dict(result, reminder='')
        return result
    R.select_sku_display = bad_all_reminder
    try:
        if not run_once('全档位展示无提醒'):
            missed += 1
    finally:
        R.select_sku_display = orig_select

    print('\n=== 变异 %d 个，漏报 %d 个 %s' % (8, missed, '✅ 全部抓到' if not missed else '❌ 有漏'))
    return 1 if missed else 0


if __name__ == '__main__':
    sys.exit(main())
