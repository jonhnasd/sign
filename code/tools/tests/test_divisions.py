# -*- coding: utf-8 -*-
"""省会地区模块回归（cn_divisions.py）。

数据来源已从「手写编码表」改为「闲鱼 GetDivision 接口」：
  POST /api/GoodsManage/GetDivision → 34 省 / 394 市 / 2814 区（嵌套树）

🔴 为什么要改：手写时我把 `130304` 标成「保定市新市区」，
   接口显示真实是「秦皇岛市北戴河区」。手写推断不可靠。

锁死：
  ① 缓存存在且结构完整（省/市/区三级）
  ② 省会判据正确（XX0100，直辖市取自身）
  ③ 抽出的编码三级自洽（省 XX0000 / 市 XX0100 / 区同省同市前缀）
  ④ 随机性 + 避开指定城市
  ⑤ 已知编码的真实名称对得上（防止再次张冠李戴）
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import cn_divisions as C

ok_n = 0
bad = []


def ck(name, got, want):
    global ok_n
    if got == want:
        ok_n += 1
        print("  ✓ %s" % name)
    else:
        bad.append("%s: got=%r want=%r" % (name, got, want))
        print("  ✗ %s   got=%r want=%r" % (name, got, want))


print("=== ① 地区树 ===")
tree = C.load_tree()
ck("省级节点数 >= 31", len(tree) >= 31, True)
flat = C._walk(tree)
ck("总节点数 > 2000", len(flat) > 2000, True)

print("\n=== ② 省会候选 ===")
caps = C.capitals(tree)
ck("省会区级候选 > 300", len(caps) > 300, True)
provs = {x[0][0] for x in caps}
ck("覆盖省级行政区 >= 31", len(provs) >= 31, True)

print("\n=== ③ 抽出的编码三级自洽 ===")
# 🔴 编码规律说明：市辖区第三段通常是 01~20，但**县/自治县不遵守**
#    （重庆 500238=巫溪县、500230=丰都县，第三段是 38/30）。
#    所以只校验「省 XX0000 / 市 XX0100 / 前两位一致 / 有第三段」，
#    不校验「区码第 3-4 位 == 市码第 3-4 位」—— 那会误判合法县份。
struct_bad = []
for _ in range(200):
    p = C.pick(tree=tree)
    dl = p["divisionIdList"]
    if len(dl) != 3:
        struct_bad.append("长度非3: %s" % dl)
        continue
    if not dl[0].endswith("0000"):
        struct_bad.append("省码非XX0000: %s" % dl)
    if not dl[1].endswith("0100"):
        struct_bad.append("市码非XX0100: %s" % dl)
    if dl[0][:2] != dl[1][:2] or dl[0][:2] != dl[2][:2]:
        struct_bad.append("三级前缀不一致: %s" % dl)
    if dl[2][4:] == "00":
        struct_bad.append("区码缺区级: %s" % dl)
    if dl[2] == dl[1]:
        struct_bad.append("区码等于市码: %s" % dl)
ck("200 次抽取全部结构合法", struct_bad[:3], [])

print("\n=== ④ 随机性 + 避开 ===")
picks = {tuple(C.pick(tree=tree)["divisionIdList"]) for _ in range(200)}
ck("200 次覆盖 > 20 个不同区", len(picks) > 20, True)
for _ in range(30):
    p = C.pick(avoid=["130304"], tree=tree)
    if "130304" in p["divisionIdList"]:
        bad.append("avoid 失效：抽到 130304")
        break
else:
    ok_n += 1
    print("  ✓ 避开 130304 生效")

print("\n=== ⑤ 已知编码名称对得上（防张冠李戴）===")
idx = {}


def _index(nodes):
    for n in nodes:
        idx[str(n.get("id"))] = n.get("shortName") or n.get("name")
        _index(n.get("children") or [])


_index(tree)
ck("130304 = 北戴河区（不是保定）", idx.get("130304"), "北戴河区")
ck("130300 = 秦皇岛市", idx.get("130300"), "秦皇岛市")
ck("130100 = 石家庄市", idx.get("130100"), "石家庄市")
ck("310115 = 浦东新区", idx.get("310115"), "浦东新区")
ck("610102 = 新城区", idx.get("610102"), "新城区")

print("\n=== ⑥ pick 返回结构 ===")
p = C.pick(tree=tree)
ck("divisionId 是 int", isinstance(p.get("divisionId"), int), True)
ck("divisionId == 列表末位", p["divisionId"], int(p["divisionIdList"][2]))
ck("有可读名", bool(p.get("name")), True)
ck("省市区字段齐全", all(p.get(k) for k in ("province", "city", "district")), True)

print()
if bad:
    print("=== 失败 %d / %d ===" % (len(bad), ok_n + len(bad)))
    for b in bad:
        print("   ", b)
    sys.exit(1)
print("=== 通过 %d / %d ✅ 省会地区（接口数据）已锁死 ===" % (ok_n, ok_n))
