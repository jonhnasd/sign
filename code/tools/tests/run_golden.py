# -*- coding: utf-8 -*-
"""golden 回归 —— 用真跑过的商品锁住关键输出，防止改动静默改变行为。

**纯离线**：只调纯函数，不联网、不写线上、不发请求。
覆盖的契约（每条都对应一次真实事故或用户明确定的规则）：

  A. 档位解析      货源标题 → 「7天 / 1个月 / 天卡」 （169 商品踩过「限价25.8」当档位）
  B. 买家填写项    popup_fields + 货源原文 → 买家真正该填的标识（165 事故：印成字段名「充值账号」）
  C. 主图允许文字  product_name + 档位 + 填写项 → 白名单；白名单外一律不许上图
  D. 图上禁词      参数名 / 到账时效 / 官方背书 / 价格 四类不得上图
  E. 留证一致性    manifest 记录的 account_label 必须等于现在解析出的 buyer_field
  F. 定价契约      成本 → 售价；成本>20 剔除；售价<成本中止；手写价原样保留（照抄闲鱼价）
  G. 参考图来源    显式参考图优先；否则严格按 source+pno；缺图/跨来源/跨 pno 失败

用法：
    python tests/run_golden.py            # 断言（退出码 0 = 全过）
    python tests/run_golden.py --bless    # 首次把当前输出写进 case 的 expect
    python tests/run_golden.py -v         # 打印每条明细
"""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

GOLDEN = os.path.join(HERE, 'golden')

FAIL = []
PASS = [0]
VERBOSE = '-v' in sys.argv


def _ok(cond, label, detail=''):
    if cond:
        PASS[0] += 1
        if VERBOSE:
            print('  ✅ %s' % label)
    else:
        FAIL.append('%s %s' % (label, detail))
        print('  ❌ %s %s' % (label, detail))
    return bool(cond)


def _eq(actual, expect, label):
    """expect 为 None 表示这条还没录过（首次运行）→ 不判红，值会被写回去。"""
    if expect is None:
        if VERBOSE:
            print('  ○ %s 首次录制 = %r' % (label, actual))
        return True
    return _ok(actual == expect, label, '（实际 %r ≠ 期望 %r）' % (actual, expect))


def load_cases():
    out = []
    for fn in sorted(os.listdir(GOLDEN)):
        if not fn.endswith('.json'):
            continue
        with io.open(os.path.join(GOLDEN, fn), encoding='utf-8') as f:
            out.append((fn, json.load(f)))
    return out


# ---------------------------------------------------------------- 单例断言
def run_recharge(case, D, R):
    """直充案例：买家填写项 + 主图白名单 + 禁词 + 留证一致性。"""
    fx = case['fixture']
    res = R.resolve_buyer_field(fx.get('popup_fields'), fx.get('intro_html', ''),
                                fx.get('notice_html', ''))
    actual = {'buyer_field': res.get('field'), 'buyer_kind': res.get('kind')}

    _eq(res.get('field'), case['expect'].get('buyer_field'), '[%s] 买家应填字段' % case['id'])

    # B 的根因断言：字段名本身绝不能当买家填写内容印出来
    field_name = ((fx.get('popup_fields') or [{}])[0] or {}).get('title') or ''
    if field_name and res.get('field') and field_name != res['field']:
        _ok(field_name not in (res['field'] or ''),
            '[%s] 字段名「%s」未被当成填写内容' % (case['id'], field_name))

    # C 主图允许文字
    wl = R.text_whitelist(fx.get('product_name', ''), fx.get('sku_labels') or [],
                          res.get('field') or '')
    actual['whitelist'] = wl
    exp_wl = case['expect'].get('whitelist')
    if exp_wl is not None:
        _eq(sorted(wl), sorted(exp_wl), '[%s] 主图白名单' % case['id'])

    # D 白名单内每一项本身不得是图上禁词（除商品名/档位豁免）
    allow = ' '.join([fx.get('product_name', '')] + list(fx.get('sku_labels') or []))
    for t in wl:
        hit = R.forbidden_on_image(t, allow)
        _ok(not hit, '[%s] 白名单项「%s」不是禁词' % (case['id'], t), '（命中 %s）' % hit)

    # E 留证一致性：图上真印的 vs 现在算出来的
    mf_label = fx.get('manifest_account_label') or ''
    if mf_label and res.get('field'):
        _ok(mf_label == res['field'] or res['field'] in mf_label,
            '[%s] 主图留证与解析一致' % case['id'],
            '（图=%s 应=%s）' % (mf_label, res['field']))
        actual['manifest_account_label'] = mf_label
    mf_wl = fx.get('manifest_whitelist') or []
    if mf_wl:
        _ok(sorted(mf_wl) == sorted(wl), '[%s] 留证白名单与当前白名单一致' % case['id'],
            '（图=%r 算=%r）' % (sorted(mf_wl), sorted(wl)))
    return actual


def run_kaomi(case, D, R):
    """卡密/照抄价案例：手写价原样保留 + 档位 + 不印填写句。"""
    fx = case['fixture']
    spec = {'property': fx.get('property') or '档位',
            'skus': [{'val': s['val'], 'pno': s['pno'], 'cost': s['cost'], 'price': s['price']}
                     for s in fx['skus']]}
    plan = D.resolve_skus(spec, case['acct'], fx.get('profit', 0.066), case['kind'])
    got = [{'val': p['val'], 'cost': p['cost'], 'price': p['price']} for p in plan]
    exp = [{'val': s['val'], 'cost': s['cost'], 'price': s['price']} for s in fx['skus']]
    _eq(got, exp, '[%s] 手写售价原样落地' % case['id'])
    return {'skus': got}


# ---------------------------------------------------------------- 全局不变量
def run_invariants(D, R):
    """不依赖具体商品的关系断言 —— 商品换了也不会误红，但行为改了必红。"""
    print('\n-- 不变量 --')
    # F1 成本 → 售价 = round(cost/0.934, 2)，且售价 ≥ 成本
    for cost in (1.39, 3.29, 5.09, 6.5, 12.09, 20.0):
        spec = {'property': '档位', 'skus': [{'val': 'X', 'pno': '1', 'cost': cost}]}
        plan = D.resolve_skus(spec, 95425, 0.066, 'kaomi')
        want = round(cost / 0.934, 2)
        _ok(len(plan) == 1 and abs(plan[0]['price'] - want) < 1e-9,
            '定价 成本%.2f → %.2f' % (cost, want),
            '（实际 %r）' % (plan[0]['price'] if plan else None))
        _ok(plan and plan[0]['price'] >= cost, '定价 成本%.2f 不亏本' % cost)

    # F2 成本闸：>20 剔除，=20 保留（resolve_skus 会打印被剔除的档，属于正常输出，吞掉避免误读）
    spec = {'property': '档位', 'skus': [{'val': 'A', 'pno': '1', 'cost': 20.00},
                                        {'val': 'B', 'pno': '2', 'cost': 20.01}]}
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        plan = D.resolve_skus(spec, 95425, 0.066, 'kaomi')
    _eq([p['val'] for p in plan], ['A'], '成本闸 20.00 留 / 20.01 剔')

    # F3 亏本硬闸：手写价 < 成本 → 中止
    spec = {'property': '档位', 'skus': [{'val': 'A', 'pno': '1', 'cost': 10, 'price': 9.99}]}
    try:
        D.resolve_skus(spec, 95425, 0.066, 'kaomi')
        _ok(False, '亏本硬闸 售价<进价 必须中止')
    except SystemExit:
        _ok(True, '亏本硬闸 售价<进价 中止')

    # F4 卡密类不得出现「下单填写」（文案侧由 deploy 保证，这里守住白名单不生成该句）
    wl = R.text_whitelist('剪映SVIP会员', ['天卡', '周卡'], '')
    _ok(not any('下单填写' in t for t in wl), '卡密类白名单不含「下单填写」', '（%r）' % wl)

    # F6 主图 SKU 展示规则：按目标 SKU 自身时长/面额最大值；单位混杂时失败关闭。
    item_skus = [
        {'skuId': 'a', 'propertyList': [{'propertyText': '时长', 'valueText': '1个月'}]},
        {'skuId': 'b', 'propertyList': [{'propertyText': '时长', 'valueText': '3个月'}]},
        {'skuId': 'c', 'propertyList': [{'propertyText': '时长', 'valueText': '15个月'}]},
    ]
    selected = R.select_sku_display(item_skus)
    _eq((selected['mode'], selected['labels'], selected['displayed_skus'][0]['sku_id']),
        ('highest', ['15个月'], 'c'), '主图默认只展示自身最大同单位时长档')
    all_selected = R.select_sku_display(item_skus, 'all')
    _eq((all_selected['mode'], all_selected['labels']),
        ('all', ['1个月', '3个月', '15个月']), '主图显式全档位展示')
    _ok(bool(all_selected.get('reminder')), '主图全档位展示必须生成提醒')
    prompt_high = R.build_prompt('优酷视频会员', ['15个月'], '手机号')
    prompt_all = R.build_prompt('优酷视频会员', ['1个月', '3个月', '15个月'], '手机号',
                                sku_display_mode='all')
    _ok('仅展示按目标商品自身时长/面额判定的最高档位' in prompt_high,
        '主图 prompt 锁定最高档模式')
    _ok('已显式选择展示目标商品全部 SKU 档位' in prompt_all,
        '主图 prompt 锁定全档模式')
    # 另一维度覆盖所有 SKU 时不可与时长混算；应选出时长最大值对应的 SKU。
    two_dim = [
        {'skuId': 'd', 'propertyList': [{'propertyText': '等级', 'valueText': 'VIP'},
                                        {'propertyText': '时长', 'valueText': '1个月'}]},
        {'skuId': 'e', 'propertyList': [{'propertyText': '等级', 'valueText': 'SVIP'},
                                        {'propertyText': '时长', 'valueText': '3个月'}]},
    ]
    _eq(R.select_sku_display(two_dim)['labels'], ['SVIP', '3个月'],
        '双维 SKU 按时长维度选档并保留完整规格组合')
    tied_two_dim = [
        {'skuId': 'j', 'propertyList': [{'propertyText': '等级', 'valueText': 'VIP'},
                                        {'propertyText': '时长', 'valueText': '终身卡'}]},
        {'skuId': 'k', 'propertyList': [{'propertyText': '等级', 'valueText': 'SVIP'},
                                        {'propertyText': '时长', 'valueText': '终身卡'}]},
    ]
    try:
        R.select_sku_display(tied_two_dim)
        _ok(False, '双维最高时长跨等级重复必须失败关闭')
    except R.SkuDisplayError:
        _ok(True, '双维最高时长跨等级重复必须失败关闭')
    # 面额只可在同单位比较，不能按数字大小跨元/积分比较。
    amounts = [
        {'skuId': 'f', 'propertyList': [{'propertyText': '面额', 'valueText': '10元'}]},
        {'skuId': 'g', 'propertyList': [{'propertyText': '面额', 'valueText': '50元'}]},
    ]
    _eq(R.select_sku_display(amounts)['labels'], ['50元'], '面额同单位按最大值选档')
    incomparable_cases = (
        ([{'propertyText': '时长', 'valueText': '30天'},
          {'propertyText': '时长', 'valueText': '1个月'}], '时长单位混杂必须失败关闭'),
        ([{'propertyText': '面额', 'valueText': '50元'},
          {'propertyText': '面额', 'valueText': '500积分'}], '面额单位混杂必须失败关闭'),
        ([{'propertyText': '档位', 'valueText': 'VIP'},
          {'propertyText': '档位', 'valueText': 'SVIP'}], '不可解析档位必须失败关闭'),
        ([{'propertyText': '档位', 'valueText': '首单体验'},
          {'propertyText': '档位', 'valueText': '长期套餐'}], '非规格文字必须失败关闭'),
    )
    for properties, label in incomparable_cases:
        try:
            R.select_sku_display([{'propertyList': [p]} for p in properties])
            _ok(False, label, '（%r）' % properties)
        except R.SkuDisplayError:
            _ok(True, label)
    tied = [
        {'skuId': 'h', 'propertyList': [{'propertyText': '时长', 'valueText': '12个月'}]},
        {'skuId': 'i', 'propertyList': [{'propertyText': '时长', 'valueText': '1年'}]},
    ]
    try:
        R.select_sku_display(tied)
        _ok(False, '跨单位同值也必须失败关闭')
    except R.SkuDisplayError:
        _ok(True, '跨单位同值也必须失败关闭')
    # 旧 replica manifest 缺新证据必须判红，不能沿用旧记录静默放行。
    old_manifest = R.MANIFEST_PATH
    try:
        with tempfile.TemporaryDirectory(prefix='main_image_manifest_golden_') as td:
            R.MANIFEST_PATH = Path(td) / 'manifest.json'
            R.write_manifest('g1', mode='replica', ref_pno='1', ref_acct='95425',
                             ref_url='https://example.invalid/ref.png', uploaded=True,
                             main_img_url='https://example.invalid/main.png',
                             whitelist_verified=True, whitelist=['商品'])
            ok, note = R.main_image_problem('g1', 'https://example.invalid/main.png')
            _ok(ok is False and 'SKU 展示模式' in note, '旧主图记录缺档位证据必须判红')
    finally:
        R.MANIFEST_PATH = old_manifest

    # G 参考图身份与预检：用临时素材库隔离测试，禁止实际网络与固定素材依赖。
    old_list, old_detail = R.LIST_JSON, R.DETAIL_JSON
    try:
        with tempfile.TemporaryDirectory(prefix='main_image_golden_') as td:
            list_path = Path(td) / 'list.json'
            detail_path = Path(td) / 'detail.json'
            list_path.write_text(json.dumps({'items': [
                {'source': '志远', 'pno': 'same', 'name': '志远商品', 'img': 'https://example.invalid/zy.png'},
                {'source': '商战', 'pno': 'same', 'name': '商战商品', 'img': 'https://example.invalid/qz.png'},
                {'source': '志远', 'pno': 'other', 'name': '其他商品', 'img': 'https://example.invalid/other.png'},
            ]}, ensure_ascii=False), encoding='utf-8')
            detail_path.write_text('{"items": []}', encoding='utf-8')
            R.LIST_JSON, R.DETAIL_JSON = list_path, detail_path
            _eq(R.resolve_reference('same', 95425, 'https://user.example/ref.png', validate=False)['ref_url'],
                'https://user.example/ref.png', '参考图 显式指定优先')
            got = R.resolve_reference('same', 95425, validate=False)
            _eq((got['ref_source_name'], got['ref_pno'], got['match']),
                ('志远', 'same', 'source+pno'), '参考图 source+pno 精确命中')
            _eq(R.resolve_reference('same', 96810, validate=False)['ref_url'],
                'https://example.invalid/qz.png', '参考图相同 pno 不跨来源')
            try:
                R.resolve_reference('missing', 95425, validate=False)
                _ok(False, '参考图缺图必须失败')
            except R.ReplicaRefMissing:
                _ok(True, '参考图缺图必须失败')
            try:
                R.resolve_reference('', 95425, validate=False)
                _ok(False, '参考图目标 pno 缺失必须失败')
            except R.ReplicaRefMissing:
                _ok(True, '参考图目标 pno 缺失必须失败')
            try:
                R.resolve_reference('same', 99999, validate=False)
                _ok(False, '参考图 acct 无来源映射必须失败')
            except R.ReplicaRefMissing:
                _ok(True, '参考图 acct 无来源映射必须失败')
    finally:
        R.LIST_JSON, R.DETAIL_JSON = old_list, old_detail

    # G2 图片读取预检：本地无效文件不能通过，确保 HTML 错误页不会冒充参考图。
    with tempfile.TemporaryDirectory(prefix='main_image_invalid_') as td:
        bad = Path(td) / 'not_image.bin'
        bad.write_bytes(b'<html>' + b'x' * 2048)
        try:
            R.resolve_reference('same', 95425, str(bad), validate=True)
            _ok(False, '参考图无效图片必须失败')
        except R.ReplicaRefMissing:
            _ok(True, '参考图无效图片必须失败')

    # F5 文案时效承诺词：必须删净（闲鱼按虚假宣传处理），且不能误伤履约方式描述
    from alds_kit.copy import find_time_promise, strip_time_promise
    for t in ('24小时自动发货，秒接单', '下单后5分钟内自动发货', '当日到账 无需等待', '极速发货'):
        left = find_time_promise(strip_time_promise(t)[0])
        _ok(not left, '文案删净时效承诺「%s」' % t[:14], '（残留 %r）' % left)
    for t in ('【自动发货】官方卡密 7天', '直充自己账号', '充值完成后默认已到账', '秒杀价 7元会员'):
        hit = find_time_promise(t)
        _ok(not hit, '文案不误伤「%s」' % t[:14], '（误判 %r）' % hit)
    # 清洗必须幂等：重复跑不继续损字（否则文案每轮返工都会短一截）
    once = strip_time_promise('当天发货 极速处理 客服在线')[0]
    _ok(strip_time_promise(once)[0] == once, '文案清洗幂等')


# ---------------------------------------------------------------- 主流程
def main():
    import deploy as D
    import replica_main_image as R

    bless = '--bless' in sys.argv
    cases = load_cases()
    print('golden 案例 %d 个（%s）' % (len(cases), GOLDEN))
    for fn, case in cases:
        print('\n-- %s --' % case['id'])
        note = case.get('note') or ''
        if note:
            print('   %s' % note)
        if case['kind'] == 'recharge':
            actual = run_recharge(case, D, R)
        else:
            actual = run_kaomi(case, D, R)
        if bless or not case.get('expect'):
            case['expect'] = dict(case.get('expect') or {}, **actual)
            if 'buyer_kind' in actual:
                case['expect']['buyer_kind'] = actual['buyer_kind']
            with io.open(os.path.join(GOLDEN, fn), 'w', encoding='utf-8', newline='') as f:
                json.dump(case, f, ensure_ascii=False, indent=2)
                f.write('\n')
            print('   📝 已写入 expect：%s' % fn)

    run_invariants(D, R)

    print('\n=== 通过 %d / 失败 %d' % (PASS[0], len(FAIL)))
    for x in FAIL:
        print('   ✗ %s' % x)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
