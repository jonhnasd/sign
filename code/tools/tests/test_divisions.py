# -*- coding: utf-8 -*-
"""省会地区编码表回归（cn_divisions.py）。

用户 2026-11-15 定：「新建宝贝的地区要随机选省会城市，不要只有一个城市」

这里锁死三件事：
  ① 编码结构合法（3 级、省 XX0000、市 XX0100、区同省前缀）
  ② 覆盖全部 31 个省级行政区，无重复
  ③ 随机抽取确实会变，且能避开指定城市
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


print("=== ① 编码结构合法 ===")
struct_bad = []
for prov, pname, city, cname, dist, dname in C.CAPITALS:
    errs = []
    if not (len(prov) == 6 and len(city) == 6 and len(dist) == 6):
        errs.append("长度非6")
    if not prov.endswith("0000"):
        errs.append("省码非XX0000")
    if not city.endswith("0100"):
        errs.append("市码非XX0100（省会规律）")
    if city[:2] != prov[:2] or dist[:2] != prov[:2]:
        errs.append("省市县前缀不一致")
    if dist[2:4] != city[2:4]:
        errs.append("区码前4位与市码不符")
    if dist[4:] == "00":
        errs.append("区码缺区级")
    if errs:
        struct_bad.append("%s(%s): %s" % (pname, "/".join([prov, city, dist]), "、".join(errs)))
ck("31 条全部结构合法", struct_bad, [])

print("\n=== ② 覆盖 31 省，无重复 ===")
ck("条目数 = 31", len(C.CAPITALS), 31)
provs = [t[0] for t in C.CAPITALS]
ck("省级码无重复", len(set(provs)), len(provs))
dists = [t[4] for t in C.CAPITALS]
ck("区级码无重复", len(set(dists)), len(dists))

print("\n=== ③ 随机性 ===")
picks = set()
for _ in range(200):
    p = C.pick()
    picks.add(tuple(p["divisionIdList"]))
ck("200 次抽取覆盖 >10 个城市", len(picks) > 10, True)

print("\n=== ④ 避开指定城市 ===")
for _ in range(30):
    p = C.pick(avoid=["130304"])
    if "130304" in p["divisionIdList"]:
        bad.append("avoid 失效：抽到了 130304")
        break
else:
    ok_n += 1
    print("  ✓ 避开 130304 生效（30 次均未命中）")

print("\n=== ⑤ pick 返回结构完整 ===")
p = C.pick()
ck("有 divisionId", isinstance(p.get("divisionId"), int), True)
ck("divisionIdList 3 级", len(p.get("divisionIdList") or []), 3)
ck("divisionId == 列表末位", p["divisionId"], int(p["divisionIdList"][2]))
ck("有可读名", bool(p.get("name")), True)

print("\n=== ⑥ 展示名不重复省市（直辖市）===")
names = [n for _, n in C.all_divisions()]
ck("无「北京市北京市」式重复", [n for n in names if n.count("市") > 1 and "区" not in n], [])

print()
if bad:
    print("=== 失败 %d / %d ===" % (len(bad), ok_n + len(bad)))
    for b in bad:
        print("   ", b)
    sys.exit(1)
print("=== 通过 %d / %d ✅ 省会地区表已锁死 ===" % (ok_n, ok_n))
