# -*- coding: utf-8 -*-
"""易店文案库 · 离线生成器（不碰线上）。

按形态（链接直充 / 共享号）生成【标题 store_name + 描述 store_info + 发货消息 cdk_txt】，
带 90 字节标题闸门与禁用词自检。

用法:
  python yd_copy_templates.py --form link_direct --product "WPS超级会员" --tier 1天 \
      --tiers "1天:1天,3天:3天,周卡:7天" --features "PDF转换,翻译" --random-items "翻译页数、AI次数随机"

输出:
  --json   输出机器可读（直接喂 POST /adminapi/product/product/{gid}）
  默认     人读预览
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "yd_copy_templates.json")

BYTE_LIMIT = 90


def byte_weight(s):
    return sum(3 if ord(c) > 0x2E80 else 1.5 for c in s)


def load():
    with open(TPL, encoding="utf-8") as f:
        return json.load(f)


def build_tiers(spec):
    """'1天:1天,周卡:7天' → [(名, 时长文案), ...]"""
    out = []
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, dur = part.split(":", 1)
        else:
            name = dur = part
        out.append((name.strip(), dur.strip()))
    return out


def render(form_cfg, args):
    tiers = build_tiers(args.tiers or (args.tier and args.tier + ":" + args.tier))
    features = args.features or ""
    speed = args.speed or ""
    tier_list = "、".join(t[1] for t in tiers) or (args.tier or "")
    tier_rows = "\n".join("%s —— %s" % (n, d) for n, d in tiers)
    if not tier_rows:
        tier_rows = "%s —— %s" % (args.tier or "", args.tier or "")
    hours = "24"
    m = re.search(r"(\d+)\s*天", args.tier or "")
    if m:
        hours = str(int(m.group(1)) * 24)

    tmpl = args.title_template or form_cfg["title_templates"][0]
    title = (tmpl
             .replace("{product}", args.product)
             .replace("{tier}", args.tier or "")
             .replace("{tiers}", "3天7天")
             .replace("{features}", features)
             .replace("{speed}", speed))

    lines = [title, ""]
    for name, body in form_cfg["desc_sections"]:
        lines.append("【%s】" % name)
        lines.append(body
                     .replace("{product}", args.product)
                     .replace("{tier}", args.tier or "")
                     .replace("{tier_count}", str(len(tiers)))
                     .replace("{tier_list}", tier_list)
                     .replace("{tier_rows}", tier_rows)
                     .replace("{features}", features)
                     .replace("{hours}", hours)
                     .replace("{random_items}", args.random_items or "部分功能次数随机"))
        lines.append("")
    desc = "\n".join(lines).rstrip()

    tags = list(form_cfg["tags"])
    if args.tags_extra:
        tags += [t for t in args.tags_extra.split(",") if t]
    tags = [t if t.startswith("#") else "#" + t for t in tags]
    desc += "\n\n" + " ".join(tags)

    cdk = (form_cfg["cdk_txt"]
           .replace("{product}", args.product)
           .replace("{用户名称}", "{用户名称}")
           .replace("{卡号}", "{卡号}")
           .replace("{卡密}", "{卡密}")
           .replace("{订单编号}", "{订单编号}"))
    return title, desc, cdk, tags


def selfcheck(title, desc, tpl):
    problems = []
    bw = byte_weight(title)
    if bw > BYTE_LIMIT:
        problems.append("标题超限 %.1f 字节（上限 %d）" % (bw, BYTE_LIMIT))
    emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
    for name, text in (("标题", title), ("描述", desc)):
        if "**" in text:
            problems.append("%s 含 ** 粗体标记（闲鱼过滤）" % name)
        if emoji.search(text):
            problems.append("%s 含 emoji（闲鱼过滤）" % name)
        for bad in tpl["global_forbidden"]["desc" if name == "描述" else "title"]:
            if bad in ("**",):
                continue
            if bad in text:
                problems.append("%s 含禁用项「%s」" % (name, bad))
    # 只拦「具体时长」的到账承诺（如 1-3分钟到账 / 2小时到账）；
    # 「秒发 / 秒到」是发货速度营销词，不算承诺到账时间（对标爆款标题就带「直充秒到」）
    for m in re.finditer(r"\d+\s*[-~到至]?\s*\d*\s*(分钟|小时|工作日|天)\s*(内)?\s*到账", desc):
        problems.append("描述疑似承诺到账时间「%s」" % m.group(0))
    return bw, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", required=True, choices=["link_direct", "shared_account"])
    ap.add_argument("--product", required=True)
    ap.add_argument("--tier", default="")
    ap.add_argument("--tiers", default="", help="名:时长,名:时长")
    ap.add_argument("--features", default="")
    ap.add_argument("--speed", default="")
    ap.add_argument("--random-items", default="")
    ap.add_argument("--tags-extra", default="")
    ap.add_argument("--title-template", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    tpl = load()
    cfg = tpl["forms"][a.form]
    title, desc, cdk, tags = render(cfg, a)
    bw, problems = selfcheck(title, desc, tpl)

    if a.json:
        print(json.dumps({
            "form": a.form,
            "card_type": cfg["card_types"],
            "store_name": title,
            "store_info": desc,
            "cdk_txt": cdk,
            "cdk_start_name": cfg["cdk_start_name"],
            "xm_cdkname": cfg["card_types"][0],
            "cdk_send_num": 1,
            "title_bytes": bw,
            "selfcheck": problems or ["OK"],
        }, ensure_ascii=False, indent=1))
        return

    print("=" * 62)
    print("形态：%s（%s）  卡种候选：%s" % (cfg["label"], a.form, " / ".join(cfg["card_types"])))
    print("标题字节：%.1f / %d  %s" % (bw, BYTE_LIMIT, "OK" if bw <= BYTE_LIMIT else "✗超限"))
    print("=" * 62)
    print("\n【store_name 标题】\n" + title)
    print("\n【store_info 描述】\n" + desc)
    print("\n【cdk_txt 发货消息】\n" + cdk)
    print("\n【自检】")
    if problems:
        for p in problems:
            print("  ✗ " + p)
    else:
        print("  ✓ 无禁用项 / 无 emoji / 无 ** / 未超字节")


if __name__ == "__main__":
    main()
