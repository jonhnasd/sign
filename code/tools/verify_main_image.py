#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""主图核验：有视觉能力时逐字核验，没有时输出「待人工」清单（绝不假装验过）。

背景
----
`onepipe_guard` ⑨b 要求主图逐字核验（商品名/档位/填写项/店铺名）。
2026-11-15 实测：**看不了图的 agent 无法完成这一关**，而它又极易被糊弄过去——
直接盖个章说「已核验」，比不做更危险。

本脚本的作用
------------
把「核验」拆成两半：
  ① 机器能验的：文件存在、尺寸合理、manifest 里的文案与 spec 是否一致、
     旧图是否残留、盖章记录是否过期 —— 这些不需要看图。
  ② 机器不能验的：图上**实际印了什么字** —— 必须人眼/多模态。

`--require-vision` 模式（默认）遇到 ② 时**不给通过**，只输出待人工清单，
退出码 3，明确表示「未完成」，不会污染 ⑨b 的通过状态。

用法
----
    python verify_main_image.py --gid 1100309381553
    python verify_main_image.py --gid 1100309381553 --vision-ok --notes "逐字核对通过"
    python verify_main_image.py --gid <id> --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 退出码语义（给 harness 判据用）
RC_OK = 0          # 机器项全过 + 人工已确认
RC_MACHINE_FAIL = 1  # 机器项就不合格
RC_NEED_HUMAN = 3    # 机器项全过，但需要看图，本 agent 没有视觉能力


MANIFEST = HERE / "_main_image_manifest.json"


def _load_manifest(gid):
    """主图记录由 replica_main_image 写在单一文件 `_main_image_manifest.json`，
    结构是 {gid: {...}}。字段实测（2026-11-15）：
    mode/ref_pno/ref_url/sku_display_mode/sku_labels/displayed_skus/
    product_name/account_label/whitelist/whitelist_verified/
    out_sha256/main_img_url/uploaded/verified_at/verified_note
    """
    if not MANIFEST.is_file():
        return None, MANIFEST
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return None, MANIFEST
    return (data.get(str(gid)) or None), MANIFEST


def check_machine(gid):
    """只做不需要看图就能判断的检查。"""
    rows = []
    man, path = _load_manifest(gid)

    if not man:
        rows.append(("manifest", False,
                     f"_main_image_manifest.json 里没有 {gid} 的记录",
                     "先跑 deploy.phase_main_image(gid, spec) 生成主图"))
        return rows, None
    rows.append(("manifest", True, f"记录存在（{path.name}）", ""))

    # ① 是否真的上传过
    if man.get("uploaded"):
        rows.append(("uploaded", True, "uploaded=true", ""))
    else:
        rows.append(("uploaded", False, "uploaded 不为真（未真正上传）",
                     "重跑 phase_main_image"))

    # ② 线上主图 URL 与 hash
    url = man.get("main_img_url")
    sha = man.get("out_sha256")
    if url and sha:
        rows.append(("image_evidence", True,
                     f"{url.rsplit('/', 1)[-1][:42]}… sha={sha[:10]}", ""))
    else:
        rows.append(("image_evidence", False, "缺 main_img_url 或 out_sha256",
                     "重生成以补证"))

    # ③ 档位展示证据（⑨b 硬要求）
    mode = man.get("sku_display_mode")
    labels = man.get("sku_labels") or []
    if mode and labels:
        rows.append(("sku_evidence", True, f"模式={mode} 展示={labels}", ""))
    else:
        rows.append(("sku_evidence", False,
                     "缺 sku_display_mode / sku_labels（旧记录）",
                     "重生成主图补证；旧记录不得静默放行"))

    # ④ 复刻归属证据
    if man.get("mode") == "replica" and man.get("ref_pno") and man.get("ref_url"):
        rows.append(("replica_ref", True,
                     f"复刻自 pno={man['ref_pno']}（{man.get('ref_source_name') or '?'}）", ""))
    else:
        rows.append(("replica_ref", False,
                     "复刻模式/参考图归属证据不全",
                     "确认走的是 replica 链路并记录 ref_pno+ref_url"))

    # ⑤ 白名单文案（⑨b 的核心：图上只允许出现白名单里的字）
    wl = man.get("whitelist") or []
    if wl and man.get("whitelist_verified"):
        rows.append(("whitelist", True,
                     f"{len(wl)} 条且已核验: {json.dumps(wl, ensure_ascii=False)[:88]}", ""))
    elif wl:
        rows.append(("whitelist", False, "白名单存在但 whitelist_verified 不为真",
                     "需要看图确认后再盖章"))
    else:
        rows.append(("whitelist", False, "缺白名单（无法判断图上该出现什么）",
                     "重生成主图以产出白名单"))

    # ⑥ 核验章是否已存在（存在≠正确，但能看出是否漏盖）
    if man.get("verified_at"):
        rows.append(("stamp", True,
                     f"已有核验章 {man['verified_at']}（{str(man.get('verified_note'))[:40]}…）",
                     ""))
    else:
        rows.append(("stamp", False, "未盖章（⑨b 未完成）",
                     "看图核验后用 --vision-ok 盖章"))

    return rows, man


def human_checklist(man, gid):
    """看图才能确认的项，逐条列出来交给人工。"""
    items = [
        "商品名是否与标题一致（逐字，含错别字）",
        "档位行是否与在售档位一致（多档/单档、单位对不对）",
        "买家填写项是否与 account_label 一致（手机号/平台账号/剪映号…）",
        "店铺名是否正确",
        "是否残留「立即到账」「官方正品」「限时」等不可承诺字样",
        "是否残留供应商水印/竞品名/货源编号/域名",
    ]
    man = man or {}
    wl = man.get("whitelist") or []
    if wl:
        items.append("图上是否**只**出现这些字（白名单）: "
                     + " ｜ ".join(str(x) for x in wl))
    if man.get("product_name"):
        items.append(f"商品名逐字核对: {man['product_name']}")
    if man.get("account_label"):
        items.append(f"填写句核对: 下单填写{man['account_label']}")
    return items


def main():
    ap = argparse.ArgumentParser(description="主图核验（区分机器项与需看图项）")
    ap.add_argument("--gid", required=True, help="线上商品 ID")
    ap.add_argument("--vision-ok", action="store_true",
                    help="本 agent 有视觉能力且已逐字核对")
    ap.add_argument("--notes", default="", help="人工核验备注")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows, man = check_machine(args.gid)
    machine_ok = all(r[1] for r in rows)
    checklist = human_checklist(man, args.gid)

    if args.json:
        print(json.dumps({
            "gid": args.gid,
            "machine_ok": machine_ok,
            "machine": [{"name": n, "ok": o, "detail": d, "fix": f}
                        for n, o, d, f in rows],
            "needs_vision": not args.vision_ok,
            "human_checklist": checklist,
            "verdict": ("machine_fail" if not machine_ok else
                        ("ok" if args.vision_ok else "need_human")),
        }, ensure_ascii=False, indent=2))
        return (RC_MACHINE_FAIL if not machine_ok else
                (RC_OK if args.vision_ok else RC_NEED_HUMAN))

    print("=" * 66)
    print(f" 主图核验 · 商品 {args.gid}")
    print("=" * 66)
    print("\n【机器可验项】")
    for n, o, d, f in rows:
        print(f" {'✓' if o else '✗'} {n:<14} {d}")
        if not o and f:
            print(f"     └─ 怎么修: {f}")

    print("\n【必须看图才能验的项】")
    for i, c in enumerate(checklist, 1):
        print(f" {i}. {c}")

    print("=" * 66)
    if not machine_ok:
        print(" 结论：机器项不合格，先修再谈看图 ✗")
        print("=" * 66)
        return RC_MACHINE_FAIL
    if not args.vision_ok:
        print(" 结论：⚠ 未完成核验（需要视觉能力）")
        print(" 本 agent 看不了图，⑨b 不得盖章。把上面清单交人工或多模态确认后，")
        print(" 再用 --vision-ok --notes \"<核对结论>\" 重跑本命令。")
        print("=" * 66)
        return RC_NEED_HUMAN
    print(f" 结论：机器项通过 + 人工已核对 ✓{('  ' + args.notes) if args.notes else ''}")
    print("=" * 66)
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
