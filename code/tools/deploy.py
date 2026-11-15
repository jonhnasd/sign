# -*- coding: utf-8 -*-
"""统一上品入口（幂等 + 跑前快照 + 默认值内建 + 自动查货源）。
一条命令跑完：建SKU → 配货源 → ⑨登记 → ⑩标识直充 → 上架 → ⑪文案同步 → ⑬详情图 → ⑫自动改价 → 自检。

⚠️ ⑬ 详情图默认开启（2026-11-02 用户定）：上游详情是图片（或图文混合）时，自动把详情图
   上传到 agiso 媒体库并追加进宝贝图片（imgUrls/imgList），闲鱼描述放不了图片，只能挂这儿。
   要关掉写 "images_from_detail": false；上限 "images_max"（默认 9，闲鱼上限）。

⚠️ ⑫ 自动改价默认开启（2026-11-02 用户定）：逐 SKU 按售价利润率 6.6% 开自动改价，
   倍拍/成本口径不符（偏差>35%）的档只关不加；原「首单引流档跳过改价」已随 2026-11-09 取消首单而失效。
   要关掉本商品的自动改价，spec 里写 "autoprice": false。

🔴 无亏本 SKU（2026-11-09 用户定，推翻 2026-10-12「默认必设首单引流款」）：
   **不再自动追加「首单」档**，且任何 SKU 售价 < 进价一律中止（不静默改价）。
   「首单引流款 = 进价−0.30、ppt=1、库存10」这个选项已取消；旧的 first:true / FIRST_LOSS
   仅为兼容历史 spec 保留，一旦触发亏本会被硬闸拦下。

用法:
  python deploy.py spec.json --dry            # 只打印计划，不改任何东西
  python deploy.py spec.json --go             # 执行（各阶段幂等，已正确的会跳过）
  python deploy.py spec.json --go --force     # 强制重建 SKU

spec.json:
{
  "goods": "1089303794792",
  "kind": "kaomi",                # recharge | kaomi | single
  "property": "京东E卡",           # 单维度名（2-4 中文字符）
  # ★ 双/多维规格（2026-10-16 起支持）——闲鱼前台渲染为「先选维度1 → 再选维度2」的联动选择器：
  #   "properties": [{"name":"会员","values":["VIP","SVIP"]},
  #                  {"name":"时长","values":["7天","1个月","3个月","12个月"]}],
  #   skus 项改用 "vals":["VIP","7天"]（顺序严格对应 properties；笛卡尔积每格一条）
  #   ⚠️ 原「多维度下首单引流档无自然落点，须显式标 first:true」条款已废止
  #      （2026-11-09 起不再生成首单档、禁止亏本）；多维度规格本身仍照常用 vals。
  "additional": "……使用说明……",    # kaomi 必填；详情是文字/图片会被自动前置（图片需先 OCR 见 detail_ocr/）
  "detail_text": false,           # 可选：关掉「上游详情 → 使用说明」自动提取
  "allow_no_detail_text": true,   # 可选：详情是图片且未识别时也放行（默认会 --go 中止）
  "acct": 95425,                  # 缺省 = 志远（最便宜，默认源）
  "profit": 0.066,                # 缺省 0.066（售价=进价/0.934）—— 2026-11-09 用户定 6.6%
  "stock": 9999,                  # 缺省 9999，所有档统一（首单档已取消）
  # ⑫ 自动改价（默认开启，无需配置）：
  #   "autoprice": false,                     # 整个宝贝不开（倍拍类/成本口径不符时必须写）
  #   "autoprice_min": 6.6, "autoprice_max": 6.6,
  #   "autoprice_skip": ["首单"],              # 值里含这些关键字的档关闭自动改价
  "recharge_types": [1],          # recharge 可省略 → 自动查货源 rechargeTemplates
  "pno": 14999, "cost": 11.18, "price": 11.59,   # single 用
  "var_key": "account", "var_name": "手机号码",
  "title": "【自动充值】xxx 直充自己账号秒到",   # 可选：⑪ 同步商品标题（≤30字）
  "desc": "【xxx】\\n本店对接官方渠道自动直充…",  # 可选：⑪ 同步商品描述（多行用 \\n）
  # 周期制货源（每月1号充 / 31天充一次）—— 默认自动识别：
  #   "period": "每月1号",        # 手填（覆盖识别）
  #   "period_auto": false,      # 关自动识别
  #   "period_in_sku": false,    # 不把周期写进 SKU 名
  #   "period_sku": false,       # SKU 名放不下时也不加「说明」档
  "skus": [                       # multi 用；multi=倍拍数，固定档用 pno
     {"val":"5元","pno":4770,"cost":4.83},                              # 单维度：val
     {"vals":["VIP","7天"],"pno":15129,"cost":1.94},                    # 多维度：vals
     {"val":"10元","pno":4769,"cost":9.82,"price":10.18}   # 售价 ≥ 进价（NO_LOSS 硬闸）
  ]
}
"""
import json, os, sys, time, datetime, copy, math, re, ssl, uuid, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import agiso_direct as A
import alds_dict as D

TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# 🔴 2026-11-09 用户定：以后的 SKU 去掉「亏本」这个选项 —— 任何档售价不得低于进价。
NO_LOSS = True       # 硬闸：resolve_skus 末尾校验 price >= cost，违反即中止（不静默抬价）
FIRST_DEFAULT = False  # 不再自动追加「首单引流款」（原为 True，2026-10-12 旧规则已废）

# 以下三项仅为兼容历史 spec 保留：显式 first:true 会算出亏本价，随即被 NO_LOSS 硬闸拦下
FIRST_LOSS = 0.30    # 旧引流价 = 进货价 − 0.30（已停用）
FIRST_STOCK = 10     # 旧引流档库存（已停用）
MIN_PRICE = 0.01     # 闲鱼可售最低价
MULTI_QTY = 9999     # 商品级库存：单库存商品(quantity 非空)必须显式覆盖为多库存值，
                     # 否则 Edit 报 ITEM_ERROR_MULTI_INVENTORY_ITEM_CAN_NOT_PUBLISH
                     # （2026-10-16 实锤：quantity=1 的「单件」宝贝无法建成多 SKU）


TITLE_MAX_BYTES = 90  # 闲鱼标题上限 90「字节」——实测中文=3、ASCII=1.5
                      # （2026-10-16 实锤：91.5 被拒「title字节长度超过限制」）

# 自动改价（⑫）—— 2026-11-02 用户定：一条龙默认包含
# 🔴 2026-11-09 用户定：默认利润率统一 6.6%（原 3.5%~4.5% 薄利）
AUTO_MIN = 6.6        # 销售利润率下限（%）
AUTO_MAX = 6.6        # 销售利润率上限（%）
AUTO_SKIP = ["首单"]   # 兼容历史规格名保留；新上商品无首单档（2026-11-09 起）
AUTO_MAXDEV = 0.35    # 目标价与现价偏差上限（防倍拍/成本口径不符被误改；超了只关不加价）
# 🔴 SKU 级「不上」双闸（2026-11-03 用户定，收紧并改为 SKU 粒度）
LIMIT_BALANCE_MAX = 500   # 货源要求「账户余额 ≥500 元」→ 该档 SKU 不上（原 1000，11-03 收紧）
SKU_COST_MAX = 20         # 用户 2026-11-12 定：真实进价/成本 >20 元 → 该档不上；售价可超过20
SKU_PRICE_MAX = 150       # 独立限制：该档售价 > 150 元 → 不上（高客单纠纷/退款风险大）


def title_weight(s):
    """闲鱼标题长度权重：中文/全角 3，ASCII 1.5。"""
    return sum(3 if ord(c) > 127 else 1.5 for c in str(s or ""))


def _fix_multi_qty(payload):
    """把商品级 quantity 从单库存值改成多库存值（仅当商品声明了 quantity）。
    商品级 quantity 为空（原生多库存商品）则不动。"""
    if payload.get("quantity") is not None:
        payload["quantity"] = MULTI_QTY
    return payload


def _first_price(cost):
    """引流价 = 进货价 − 0.30，**向上取整到分**（严格保证亏损 ≤ 0.30）。

    下限 MIN_PRICE：进价 < 0.31 的极低价档（如 1 小时卡 0.269）按公式会算出负数，
    必须夹到闲鱼可售最低价 0.01，否则 Edit 被拒。夹紧后亏损 = 进价 − 0.01 < 0.30，仍合规。
    """
    p = math.ceil(round((float(cost) - FIRST_LOSS) * 100, 6)) / 100.0
    return max(p, MIN_PRICE)


def _dd(r):
    return (r or {}).get("data", {}).get("data") if isinstance(r, dict) else None

def _ok(r):
    return '"issuccess":true' in json.dumps(r, ensure_ascii=False).lower().replace(" ", "")


# ===== 上游详情 → 使用说明（2026-11-02 用户定：卡密类详情是文字就提取出来，放在使用说明上面）=====
_ENT = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
        "&#39;": "'", "&apos;": "'", "&emsp;": " ", "&ensp;": " ", "&middot;": "·"}
DETAIL_TEXT_MAX = 1200   # 上游文字上限：超出截断（阿奇索使用说明字段不宜过长）


def html_to_text(html):
    """货源 goodsDetail（HTML）→ 纯文本。

    规则：`<img>` 一律剥掉（图片提不出文字）；块级标签 `<br>/</p>/</div>/</li>/</tr>/<h*>` 转换行；
    其余标签当空格；解常见实体；压缩空白与空行。
    实测（2026-11-02 志远卡密）：多数 `goodsDetail` 是纯文字兑换流程（多邻国/美图/百度网盘/全民K歌/古茗），
    少数是纯图（哈根达斯 21842），个别为空（小猿 24164）。
    """
    if not html:
        return ""
    s = re.sub(r"<\s*img[^>]*>", " ", str(html), flags=re.I)
    s = re.sub(r"<\s*(br|/p|/div|/li|/tr|/h[1-6])\s*/?\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    for k, v in _ENT.items():
        s = s.replace(k, v)
    s = re.sub(r"[ \t\u3000]+", " ", s)
    s = re.sub(r"\n[ \t]*", "\n", s)
    # 逐行去首尾空白 + 丢空行：使用说明里连续空行只会把字数翻倍，读起来还散
    lines = [ln.strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


DETAIL_IMG_DIR = os.path.join(HERE, "detail_imgs")   # 详情图片下载目录 detail_imgs/<pno>/1.png
DETAIL_OCR_DIR = os.path.join(HERE, "detail_ocr")    # 图片识别结果缓存 detail_ocr/<pno>.txt

_IMG_TAG_RE = re.compile(r"""<img[^>]*>""", re.I)
_IMG_SRC_RE = re.compile(r"""(?:data-src|data-original|src)\s*=\s*["']([^"']+)["']""", re.I)
_BG_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)


def detail_images(d):
    """货源详情 → 图片地址列表（去重保序，主图垫底，最多 12 张）。

    来源：`goodsDetail` 里 `<img src|data-src|data-original>`、CSS `url(...)`，外加主图 `imgUrl`。
    2026-11-02 用户定：详情是**图片**时也要读（由 Agent 多模态识别），不能只认文字。
    """
    d = d or {}
    html = str(d.get("goodsDetail") or "")
    out = []

    def _add(u):
        u = (u or "").strip().strip('"').strip("'")
        if u.startswith("//"):
            u = "https:" + u
        if u.lower().startswith(("http://", "https://")) and "base64" not in u.lower() and u not in out:
            out.append(u)

    for tag in _IMG_TAG_RE.findall(html):
        m = _IMG_SRC_RE.search(tag)
        if m:
            _add(m.group(1))
    for u in _BG_URL_RE.findall(html):
        _add(u)
    imgs = out[:11]
    _add(d.get("imgUrl"))
    return (imgs + [u for u in out[11:] if u not in imgs])[:12]


def ocr_text(pno):
    """详情**图片**的识别结果缓存：`detail_ocr/<pno>.txt`（由 goods_detail_text.py --ocr-file 写入）。"""
    if not pno:
        return ""
    p = os.path.join(DETAIL_OCR_DIR, "%s.txt" % pno)
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _apply_detail_text(spec, plan, acct):
    """卡密类：把上游详情（**文字 + 图片识别**）提取出来，前置到 alds「使用说明」(additional) 最前面。

    · 文字：`goodsDetail` → html_to_text()
    · 图片：`goodsDetail` 里的图 → 需先用 `goods_detail_text.py <pno> --fetch` 下载、Agent 识别、
      `--ocr-file` 写回 `detail_ocr/<pno>.txt`；本函数读到就一起拼进去
    · 图文都有 → 文字在前、图片识别在后（去重：前 40 字已含则不重复）
    · spec 已含同一段（前 40 字重合）→ 不重复拼
    · 逐档试 pno（最多 3 个），取第一个有内容的（卡密同款不同档 pno 可能不同）
    · 开关：`"detail_text": false` 关闭；其他 kind 想启用写 `"detail_text": true`
    """
    if spec.get("detail_text") is False:
        print("\n-- 使用说明（上游详情 文字/图片）--\n  已显式关闭（detail_text=false）")
        return {"status": "off"}
    cands = [(p.get("pno"), p.get("acct") or acct) for p in plan if p.get("pno")]
    if not cands and spec.get("pno"):
        cands = [(spec.get("pno"), acct)]
    # spec.detail_pno 置顶：同一商品各档常共用同一张详情图，但识别结果只缓存在其中一档的 pno 上，
    # 只试前 3 档会把「已识别的档」漏掉、误判成「未识别」而中止（11-02 哈根达斯实证）。
    if spec.get("detail_pno"):
        cands = [(pn, a) for pn, a in cands if str(pn) != str(spec["detail_pno"])]
        cands.insert(0, (spec["detail_pno"], acct))
    seen, uniq = set(), []
    for pno, a in cands:
        if pno and int(pno) not in seen:
            seen.add(int(pno))
            uniq.append((pno, a))

    print("\n-- 使用说明（上游详情 文字/图片）--")
    text, hit, _name_hit = "", None, ""
    need_ocr = None          # (pno, 图片数)：详情有图但没识别结果 → 需先 OCR
    # 买家填写字段的解析素材（rechargeTemplates = 下单表单；buyNotice/goodsDescribe = 说明原文）
    _tmpl, _notice = [], ""
    for pno, a in uniq[:3]:
        try:
            d = D.detail(pno, a) or {}
        except Exception as e:
            print("  pno=%s 详情读取失败：%s" % (pno, e))
            continue
        t = html_to_text(d.get("goodsDetail") or "")
        imgs = detail_images(d)
        o = ocr_text(pno)
        if not imgs and not o and not t:
            print("  pno=%s 详情为空 → 试下一个" % pno)
            continue
        if o and t and o[:40] not in t and t[:40] not in o:
            t = t + "\n\n" + o
        elif o and not t:
            t = o
        if t:
            text, hit = t, pno
            _name_hit = d.get("name") or ""
            _tmpl = d.get("rechargeTemplates") or []
            _notice = " ".join(str(d.get(k) or "") for k in ("buyNotice", "goodsDescribe"))
            print("  pno=%s 取到 %d 字（详情文字 %d 字 · 图片 %d 张%s）"
                  % (pno, len(t), len(html_to_text(d.get("goodsDetail") or "")), len(imgs),
                     "，已含图片识别结果" if o else ""))
            break
        if imgs and not need_ocr:
            need_ocr = (pno, len(imgs))
        print("  pno=%s 详情是纯图片 %d 张、尚无识别结果 → 试下一个" % (pno, len(imgs)))
    if not text:
        if need_ocr:
            pno, n = need_ocr
            print("  ❌ 详情是图片 %d 张但未识别（pno=%s）—— 使用说明必须据详情写，不能凭空编" % (n, pno))
            print("     先跑：python goods_detail_text.py %s --fetch" % pno)
            print("     我识别图里的文字后：python goods_detail_text.py %s --ocr-file <文本>" % pno)
            print("     确属无文字的纯装饰图 → spec 加 \"allow_no_detail_text\": true 放行")
            return {"status": "need_ocr", "pno": pno, "imgs": n}
        print("  上游详情无文字、无图片 → 使用说明只能用 spec 手写内容")
        return {"status": "empty"}

    spec["_detail_cache"] = {"pno": hit, "name": _name_hit, "text": text,
                             "recharge_templates": _tmpl, "notice": _notice}
    cur = (spec.get("additional") or "").strip()
    if cur and text[:40] in cur:
        print("  上游文字已包含在使用说明里，跳过拼接")
        return {"status": "ok", "pno": hit}
    if len(text) > DETAIL_TEXT_MAX:
        print("  ⚠️ 上游文字 %d 字超过上限 %d → 截断" % (len(text), DETAIL_TEXT_MAX))
        text = text[:DETAIL_TEXT_MAX].rstrip() + "…"
    spec["additional"] = (text + ("\n\n" + cur if cur else "")).strip()
    print("  已从 pno=%s 提取 %d 字上游说明，放在使用说明最前面%s"
          % (hit, len(text), ("（原说明 %d 字接在后面）" % len(cur)) if cur else ""))
    print("  -------- 合并后使用说明 --------")
    for ln in spec["additional"].splitlines():
        print("  | " + ln)
    print("  --------------------------------")
    return {"status": "ok", "pno": hit}


# ===== 据上游详情生成文案（2026-11-02 用户定：商品文案**部分**从详情里取）=====
_NAME_JUNK = ("稳定不掉线", "包售后", "售后无忧", "秒发", "秒到", "24小时", "24h",
              "自动发货", "官方充值", "支持批发", "量大优惠", "长期供应", "包退")

# 文案里的详情段：只摘「怎么用 / 有什么限制 / 多久有效」，不整段照搬（2026-11-02 用户定「部分取」）。
# 理由：详情原文常夹带标题碎片、营销水词、重复档位说明，整段进文案既冗长又像抄来的。
DESC_DETAIL_MAX = 260          # 详情摘录在描述里的字数上限（描述主体靠公式，详情只占约三分之一）
DESC_DETAIL_LINES = 16         # 最多摘几行（列表项短行多，字数才是主约束）
# 分节标题：一、xxx /（一）xxx /【xxx】/ 短冒号标题；数字列表项（1. xxx）不算节标题
# 分节标题：只认「一、xxx」/「（一）」/「【xxx】」这类**真结构**；
# 「✅产品规格：…」这种 KV 行不算节 —— 否则直充的规则型详情会被切成几十个假节。
_DETAIL_SEC_RE = re.compile(
    r"^(?:[一二三四五六七八九十]+\s*[、.．]\s*\S{0,14}"
    r"|[（(]\s*[一二三四五六七八九十]+\s*[）)]\s*\S{0,14}"
    r"|【[^】]{1,14}】)\s*$")
DETAIL_DROP_KW = ("稳定不掉线", "包售后", "售后无忧", "量大优惠", "支持批发", "长期供应",
                  "招代理", "一件代发", "全天在线", "客服微信", "加微信", "加QQ", "私聊",
                  "下单立减", "限时特价", "特价", "低价", "优惠价", "冲量", "刷单", "好评返")
# 与三段标准条款重复的主题（退款/售后/账号责任/时效）：我们已有标准版，详情再抄一遍只是啰嗦
_DETAIL_DROP_SEC = re.compile(
    r"^\s*[【\[（(]?\s*(?:商品资质|退款规则|退款说明|退款|售后|下单须知|购买须知|下单必读|账号责任|"
    r"充值时效|到账时效|发货时效|防骗|投诉|免责|电商对接|描述参考)")
# 货源方写给电商看的元信息 / 规则标题：整行没有产品信息量
_DETAIL_NOISE = re.compile(r"(?:电商对接|描述参考|下单必读|必读规则|以上规则|拍下即默认|拍下默认已知晓)")
_TIME_PROMISE = [
    (r"\d+\s*[-~至到]\s*\d+\s*分钟(?:内)?到账", ""),
    (r"\d+\s*分钟(?:内)?到账", ""),
    (r"\d+\s*小时(?:内)?到账", ""),
    (r"\d+\s*天(?:内)?到账", ""),
    (r"秒到账|秒到|秒充|立即到账|极速到账|马上到账", ""),
]
COPY_CLAUSE = {
    "kaomi": [
        ("【下单须知】", "虚拟商品，卡密发出后不支持退款！下单前请核对商品名称与面额，拍错不退不换。"
                        "未成年禁止下单，拍下默认已成年。"),
        ("【防骗提醒】", "本店无小号、无分店，不刷单、不做任务、不返利。没有闲鱼以外的联系方式，"
                        "任何引导脱离平台交易的都是骗子，切勿轻信！"),
        ("【售后说明】", "卡密默认已发送。若券码无法使用，请在确认收货前联系客服，并按客服要求提供录屏或截图证据；"
                        "未配合提交证据的，默认视为已正常交付。"),
    ],
    "recharge": [
        ("【下单须知】", "虚拟商品，充值完成后不支持退款！下单前仔细核对账号，买家填错账号造成损失自行承担。"
                        "未成年禁止下单，拍下默认已成年。"),
        ("【防骗提醒】", "本店无小号、无分店，不刷单、不做任务、不返利。没有闲鱼以外的联系方式，"
                        "任何引导脱离平台交易的都是骗子，切勿轻信！"),
        ("【售后说明】", "充值完成后默认已到账。若未到账，申请售后请配合客服提供录屏证据。"
                        "未配合提交上述证据的，默认视为已充值到账。"),
    ],
}


def clean_goods_name(name):
    """上游商品名 → 干净产品名：去【】标签、去售后/时效类水词、去分隔符。"""
    s = str(name or "")
    s = re.sub(r"【[^】]*】", " ", s)
    s = re.sub(r"「[^」]*」", " ", s)
    for w in _NAME_JUNK:
        s = s.replace(w, " ")
    s = re.sub(r"[｜|]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -—_")
    return s


def sanitize_promise(text):
    """去掉「N分钟到账 / 秒到 / 立即到账」这类**时间承诺**（2026-10-16 用户定：不承诺到账时间）。"""
    s = str(text or "")
    for pat, rep in _TIME_PROMISE:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return "\n".join(ln.strip() for ln in s.splitlines() if ln.strip())


def _norm(s):
    """比对用的归一化：去空白/标点/全角符号，只留文字数字。"""
    return re.sub(r"[\W_]+", "", str(s or "")).lower()


def _split_long_line(ln, cap=100):
    """超长行按「；。！？」拆句再拼回 ≤cap 的段。

    货源详情常把整段权益塞在一行（喜马拉雅 24105 的「核心权益」一条就 300+ 字），
    不拆的话要么整行放不下被丢、要么一行吃掉全部字数预算。
    """
    if len(ln) <= cap:
        return [ln]
    out, buf = [], ""
    for p in re.split(r"(?<=[；;。！!？?])", ln):
        p = p.strip()
        if not p:
            continue
        if buf and len(buf) + len(p) > cap:
            out.append(buf)
            buf = p
        else:
            buf += p
    if buf:
        out.append(buf)
    return out or [ln]


def _pick_by_value(lines, max_chars, max_lines):
    """无分节的规则型详情 → 挑「有信息量」的行，而不是从头截。

    优先级：`XX：yyy` 这类结构化短行（「充值账号：填…」「充值方式：…」）> 短行 > 长段落。
    实测（喜马拉雅 24105）：纯顺序截到 260 字时，预算被「核心权益」的 100 字大段吃光，
    反而把「充值账号/充值方式」挤掉了 —— 那才是买家真正要看的。
    第二轮严格按原序补齐、遇到放不下就停，保证列表编号不会中间跳号。
    """
    def score(ln):
        n = len(_norm(ln))
        kv = ("：" in ln) or (":" in ln)
        if kv and n <= 45:
            return 4
        if n <= 25:
            return 3
        if n <= 60:
            return 2
        return 1

    picked, used, got = [], 0, set()
    for i in sorted(range(len(lines)), key=lambda i: (-score(lines[i]), i)):
        if score(lines[i]) < 3:
            continue
        ln = lines[i]
        if len(picked) >= max_lines or used + len(ln) > max_chars:
            continue
        got.add(i)
        picked.append(i)
        used += len(ln)
    for i in range(len(lines)):
        if i in got:
            continue
        ln = lines[i]
        if len(picked) >= max_lines or used + len(ln) > max_chars:
            break
        got.add(i)
        picked.append(i)
        used += len(ln)
    return [lines[i] for i in sorted(picked)]


def pick_detail_parts(text, max_chars=DESC_DETAIL_MAX, max_lines=DESC_DETAIL_LINES):
    """详情原文 → 文案里可用的**要点片段**（不整段照搬）。

    2026-11-02 用户定：商品文案「部分」从详情里取。详情真正值钱的是
    「怎么兑换 / 有什么限制 / 多久有效 / 哪些门店可用」，营销水词与标题碎片照搬进文案
    又长又像抄。

    做法（三步）：
      ① 丢水词行 / 纯符号 / 过短碎片 / 重复行；
      ② 按「一、/（一）/<b>【】</b>/短冒号标题」**分节**，每节按均分额度取行 ——
         避免像简单截断那样只吃开头几行、把后面的使用限制全丢掉；
      ③ 剩余额度按原顺序回填，总字数 ≤ max_chars、行数 ≤ max_lines。
    全被过滤掉则返回 ""（调用方就当详情没提供文案素材）。
    """
    lines, seen = [], set()
    dropping = False        # 命中「重复主题标题」后，其下正文整段丢弃，避免列表项散落
    for raw in str(text or "").splitlines():
        # 行首的 ✅📋⏱📌 等装饰符号去掉（闲鱼详情不一定认，还会占篇幅）
        ln = re.sub(r"^[^\w\u4e00-\u9fa5【（(]+", "", str(raw)).strip()
        ln = re.sub(r"^[\s·•\-—*#>|]+", "", ln)
        ln = re.sub(r"[ \t]{2,}", " ", ln)
        # 先去掉「5分钟到账 / 秒到」这类时间承诺；删完只剩残句（「正常 请放心购买」）→ 整行丢
        cleaned = sanitize_promise(ln)
        if not cleaned:
            continue
        if cleaned != ln and len(_norm(cleaned)) < 8:
            continue
        ln = cleaned
        # 一行塞了几百字（「核心权益：…；…；…」）→ 按分句拆，否则单行就能吃掉整个预算
        for piece in _split_long_line(ln):
            if not piece:
                continue
            # 「XX：yyy」这种短标题行决定后面的正文要不要：退款规则/账号责任/到账时效/下单必读
            # 都是标准条款已覆盖的内容，连标题带正文一起丢（否则只剩标题被删、列表项散落）
            _is_head = bool(_DETAIL_SEC_RE.match(piece)) or (
                (("：" in piece) or (":" in piece)) and len(_norm(piece)) <= 20)
            if _is_head:
                dropping = bool(_DETAIL_DROP_SEC.match(piece)) or bool(
                    _DETAIL_NOISE.search(piece) and len(piece) <= 30)
                if dropping:
                    continue
            elif dropping:
                continue
            if _DETAIL_DROP_SEC.match(piece):
                continue        # 单行就带主题词（「商品资质：…」这类长句），同样不要
            if any(w in piece for w in DETAIL_DROP_KW):
                continue
            if _DETAIL_NOISE.search(piece) and len(piece) <= 30:
                continue
            if len(_norm(piece)) < 3 or re.fullmatch(r"[\W_]+", piece):
                continue
            # 「温馨提示：」这类空标题（短且以冒号结尾）没有信息量
            if len(_norm(piece)) <= 8 and piece.endswith(("：", ":")):
                continue
            k = _norm(piece)
            if k in seen:
                continue
            seen.add(k)
            lines.append(piece)

    sections = []                       # [(节标题 or "", [正文行])]
    for ln in lines:
        if _DETAIL_SEC_RE.match(ln) and len(_norm(ln)) <= 16:
            sections.append([ln, []])
        else:
            if not sections:
                sections.append(["", []])
            sections[-1][1].append(ln)
    # 正文被过滤光的节（只剩标题）→ 整节丢掉，别在文案里留一个空标题
    sections = [s for s in sections if s[1]]
    # 整节丢弃与标准条款重复的主题（退款规则/账号责任/下单必读…），其正文一并不要
    kept = []
    for head, body in sections:
        if head and _DETAIL_DROP_SEC.match(head):
            continue
        body = [ln for ln in body if not _DETAIL_DROP_SEC.match(ln)]
        if body:
            kept.append([head, body])
    sections = kept

    # 有真节结构（一、二、三… /（一）/【】）→ 按节取舍；
    # 没有（直充那种「✅产品规格：…」规则流水）→ 择优：结构化短行优先。
    if len([s for s in sections if s[0]]) < 2:
        return "\n".join(_pick_by_value(lines, max_chars, max_lines))

    # 按「节」整体取舍，节内一律连续保留 —— 逐行择优会把列表编号打乱
    # （实测：1.打开链接 落到「购买说明」下、编号 1/3/4/5/6 跳号），文案看起来就像坏了。
    def _size(i):
        head, body = sections[i]
        return len(head) + sum(len(ln) for ln in body)

    picked, used, nlines, done = [], 0, 0, set()

    def _emit(i):
        nonlocal used, nlines
        head, body = sections[i]
        done.add(i)
        if head and (used + len(head) > max_chars or nlines >= max_lines):
            return                      # 标题放不下 → 整节不要，别留「无标题的正文」
        got = []
        if head:
            got.append(head)
            used += len(head)
            nlines += 1
        for ln in body:
            if nlines >= max_lines or used + len(ln) > max_chars:
                break
            got.append(ln)
            used += len(ln)
            nlines += 1
        if got:
            picked.append((i, got))

    # 第一轮：按原序整节放下（放得下才整节收，保住该节的完整性）
    for i in range(len(sections)):
        head, body = sections[i]
        if used + _size(i) <= max_chars and nlines + len(body) + (1 if head else 0) <= max_lines:
            _emit(i)
    # 第二轮：放不下的长节，用剩余额度按行顺序截断（截在该节中间也比丢掉强）
    for i in range(len(sections)):
        if i not in done:
            _emit(i)
    return "\n".join(ln for _i, got in sorted(picked) for ln in got)


# ===== 充值周期标注（2026-11-03 用户定）=====
# 背景：一部分货源是「每月1号统一充」「31天充一次」这种**周期制**，不是下单即时到账。
# 周期有时写在货源标题里、有时只写在详情说明里 —— 买家看不到就会以为拍下马上到账，必然扯皮。
# 规则：
#   ① 标题必须带周期（字节优先级高于档位摘要）；
#   ② SKU 规格值尽量带上（`30天` → `30天·每月1号`）；
#   ③ SKU 值放不下（过长/不是时长档）→ 额外加一格「说明·…」专写周期，并在描述里提示别拍。
SKU_VAL_MAX = 24          # 单个 SKU 规格值字数上限（超了闲鱼前台显示不全，也容易被 Edit 拒）
_PERIOD_RULES = [
    (re.compile(r"每(?:个)?月\s*(\d{1,2})\s*[号日]"), "每月%s号"),
    (re.compile(r"(?:次月|下月|第2月)\s*(\d{1,2})\s*[号日]"), "每月%s号"),
    (re.compile(r"(\d{1,2})\s*[号日]\s*(?:统一|自动|开始|固定)?\s*(?:充值|到账|发放|续费)"), "每月%s号"),
    (re.compile(r"每\s*(\d{1,3})\s*天"), "每%s天"),
    (re.compile(r"(\d{1,3})\s*天\s*(?:自动)?\s*(?:充值|充|到账|发放|续费)\s*(?:一次|1\s*次|/次)"), "每%s天"),
    (re.compile(r"自然月"), "按自然月"),
    (re.compile(r"每(?:周|星期)"), "每周"),
    (re.compile(r"每(?:季度|90\s*天|3\s*个月)"), "每季度"),
]


def period_tag(*texts):
    """从货源名称/详情里识别「充值周期」，返回规范短标签（识别不到返回 ""）。

    只认**周期制**写法，不认有效期/到账时效：
      ✅「每月1号自动充值」「1号充值」「每31天充一次」「31天充值一次」「按自然月」
      ❌「30天有效期」「24小时内到账」「31天到账」—— 那是时效，标成周期会误导买家
    """
    for t in texts:
        s = str(t or "")
        if not s:
            continue
        for pat, fmt in _PERIOD_RULES:
            m = pat.search(s)
            if m:
                return (fmt % m.group(1)) if "%s" in fmt else fmt
    return ""


def detect_period(spec, item=None):
    """确定本商品的充值周期：spec.period（手填）> 上游商品名 > 上游详情正文 > spec 标题。

    `item`（现有宝贝）作为最后兜底：上次已写进 SKU 名的周期，这次详情接口取不到也要沿用，
    否则周期会时有时无、SKU 值来回改 → 每次跑都触发重建。
    """
    p = str(spec.get("period") or "").strip()
    if p:
        print("  周期   : %s（spec 手填）" % p)
        return p
    if spec.get("period_auto") is False:
        return ""
    c = spec.get("_detail_cache") or {}
    for src, key in (("上游商品名", c.get("name")), ("上游详情", c.get("text")),
                     ("spec 标题", spec.get("product") or spec.get("title"))):
        hit = period_tag(key)
        if hit:
            print("  周期   : %s（来自%s）" % (hit, src))
            return hit
    for s in ((item or {}).get("itemSkuList") or []):
        for pp in (s.get("propertyList") or []):
            v = str(pp.get("valueText") or "")
            tail = v.split("·")[-1].strip() if "·" in v else ""
            if tail and _PERIOD_TAG_RE.match(tail):
                print("  周期   : %s（沿用现有 SKU 名）" % tail)
                return tail
    return ""


_PERIOD_TIME_VAL = re.compile(r"^\d+(?:\.\d+)?\s*(?:天|日|个月|月|年|周)$")
# SKU 名里「·周期」后缀的合法形态（回捞用，防止把普通后缀误当周期）
_PERIOD_TAG_RE = re.compile(r"^(?:每月\d{1,2}号|每\d{1,3}天|按自然月|每周|每季度)$")


def apply_period_to_plan(spec, plan, period):
    """把周期写进 SKU 规格值（`30天` → `30天·每月1号`），返回 (成功档数, 放不下的档名)。

    只挂在时长维度值上（`30天`/`1个月`）；不是时长档就挂最后一维。
    放不下（加完超 SKU_VAL_MAX）→ 该档不改名，由调用方补一格「说明」SKU。
    """
    if not period or spec.get("period_in_sku") is False:
        return 0, []
    ndim = len(spec_props(spec))
    ok_n, bad = 0, []
    for p in plan:
        if p.get("note"):
            continue            # 说明档本身就是周期文字，不用再加
        vals = list(p.get("vals") or [p["val"]])
        idx = next((i for i, v in enumerate(vals) if _PERIOD_TIME_VAL.match(str(v))), ndim - 1)
        v = str(vals[idx])
        if period in v:
            ok_n += 1
            continue
        nv = "%s·%s" % (v, period)
        if len(nv) > SKU_VAL_MAX:
            bad.append(plan_disp(p))
            continue
        vals[idx] = nv
        p["vals"] = vals
        p["val"] = nv if ndim == 1 else SEP.join(vals)
        p["_period_in_sku"] = True
        ok_n += 1
    return ok_n, bad


# 说明档「类型」标签（2026-11-03 用户定：加说明档必须标明**是哪一类注意项**，
# 不能只写「说明」——买家看不出这条说明管的是什么，也分不清哪些档位受影响）。
NOTE_KIND = {
    "period": ("周期说明", "充值周期"),      # 每月1号充 / 31天充一次
    "valid": ("有效期说明", "有效期"),        # 卡券有效期、兑换截止
    "limit": ("限购说明", "限购"),            # 每账号/每单限购
    "region": ("地区说明", "地区限制"),        # 部分地区不可用（如青桔烟台）
}


def note_sku_val(kind, text):
    """说明档规格值 = 「类型说明·内容」；超 SKU_VAL_MAX 逐级降级（类型词优先保留）。"""
    label = NOTE_KIND.get(kind, ("说明", ""))[0]
    for cand in ("%s·%s" % (label, text), "%s·%s" % (label[:2], text),
                 "说明·%s" % text, text):
        if len(cand) <= SKU_VAL_MAX:
            return cand
    return ("说明·%s" % text)[:SKU_VAL_MAX]


# ===== 货源限制词自动标注（2026-11-13 用户定：「货源是一号一次或其他要求，请在sku上写清楚」）=====
# 只标注会影响买家选择或履约的要求；「限价」是卖家侧定价约束，🔴 完全不写入
# 档位名/描述/发货说明（买家文案三不写，2026-11-13 用户两次补充确认）。
_LIMIT_RULES = [
    (re.compile(r"一号.{0,3}一次|一号限制|一号一充"), "一号限一次",
     "同一账号仅可兑换/充值一次，请勿重复兑换"),
    (re.compile(r"限购|每[日天]限|每天限"), "限购",
     "按货源规则限购，请按需拍下"),
    (re.compile(r"仅限新用户|新用户专|新号"), "仅新用户",
     "该档仅限新用户使用"),
]
_LIMIT_PRICE_RE = re.compile(r"限价")
_limit_cache = {}


def limit_tag(pno, acct):
    """扫货源标题+详情的限制词 → (tag, 说明句)。

    各档独立判定；「限价」命中只打印、不产生任何买家可见标注。"""
    key = (str(acct), str(pno))
    if key in _limit_cache:
        return _limit_cache[key]
    tag, tip = None, None
    try:
        d = D.detail(pno, acct) or {}
        text = "%s %s" % (d.get("name") or "", d.get("goodsDetail") or "")
        if _LIMIT_PRICE_RE.search(text):
            print("  [限制] pno=%s 货源含「限价」→ 按规则不写入任何买家文案" % pno)
        for rx, tg, tp in _LIMIT_RULES:
            if rx.search(text):
                tag, tip = tg, tp
                break
    except Exception as e:
        print("  ⚠️ [限制] pno=%s 取详情失败：%s" % (pno, str(e)[:60]))
    _limit_cache[key] = (tag, tip)
    return tag, tip


def apply_limit_to_plan(spec, plan, acct):
    """把货源限制词写进对应档位值（`1天` → `1天·一号限一次`）。

    🔴 逐档独立标注，不把某档要求套到其他档；放不下（超 SKU_VAL_MAX）→
    复用 add_note_sku 的「限购说明」格（NOTE_KIND['limit']，2026-11-03 已有机制）。
    返回 [(val, tag, tip)]，供描述注入（inject_limit_notes）与 guard 核对。"""
    out, overflow = [], []
    for p in plan:
        if p.get("note"):
            continue            # 说明档本身就是限制文字，不再叠加
        tag, tip = limit_tag(p.get("pno"), p.get("acct") or acct)
        if not tag:
            continue
        vals = list(p.get("vals") or [p["val"]])
        if tag in vals[-1]:
            out.append((plan_disp(p), tag, tip))
            continue
        nv = "%s·%s" % (vals[-1], tag)
        if len(nv) > SKU_VAL_MAX:
            overflow.append((plan_disp(p), tag, tip))
            continue
        vals[-1] = nv
        p["vals"] = vals
        p["val"] = nv if len(spec_props(spec)) == 1 else SEP.join(vals)
        out.append((plan_disp(p), tag, tip))
        print("  [限制] %-8s → 档位标注 %s" % (tag, plan_disp(p)))
    if overflow:                 # 档名放不下 → 说明格兜底（复用现成机制）
        by_tag = {}
        for v, tag, tip in overflow:
            by_tag.setdefault(tag, {"tip": tip, "vals": []})["vals"].append(v)
        for tag, info in by_tag.items():
            add_note_sku(spec, plan, "limit",
                         "%s（%s）" % (tag, info["tip"]),
                         applies=info["vals"], desc_text=info["tip"])
            out.extend((v, tag, info["tip"]) for v in info["vals"])
        print("  [限制] %d 档档名放不下 → 已加「限购说明」格" % len(overflow))
    return out


def inject_limit_notes(spec, notes):
    """把限制说明行并进描述：有【使用说明】段就在段内插行，否则加【购买须知】段。

    🔴 只写履约限制（一号一次/限购等）；「限价」类信息永不进入描述。"""
    if not notes or spec.get("desc") is None:
        return
    desc = spec["desc"]
    add = ["· %s：%s" % (v, tip) for v, _tag, tip in notes
           if tip and tip[:10] not in desc]
    if not add:
        return
    block = "\n".join(add)
    m = re.search(r"【使用说明】\n(?:·[^\n]*\n?)*", desc)
    if m:
        seg = m.group(0).rstrip("\n")
        spec["desc"] = desc.replace(seg, seg + "\n" + block, 1)
    else:
        spec["desc"] = desc.rstrip("\n") + "\n\n【购买须知】\n" + block + "\n"
    print("  [限制] 已在描述补 %d 行限制说明" % len(add))


def add_note_sku(spec, plan, kind, text, applies=None, desc_text=None):
    """加一格「<类型>说明·…」专写注意事项（周期/有效期/限购/地区…）。

    价格取该宝贝最高档价、库存 1 → 排最后、一眼不像正常档，减少误拍；
    文案里再写一句「该档只是<类型>说明，请勿拍」，并点名受影响的档位。
    多维度商品不加（会污染维度值），只写标题与描述。
    """
    if len(spec_props(spec)) > 1:
        print("  ⚠️ 多维度商品无法插说明格（会污染维度值）→ 「%s」只写进标题与描述"
              % NOTE_KIND.get(kind, ("说明", ""))[1])
        return None
    if any(p.get("note") for p in plan):
        return None
    base = min([p for p in plan if p.get("pno")],
               key=lambda x: float(x.get("cost") or 0), default=None)
    if not base:
        return None
    top = max([float(p.get("price") or 0) for p in plan if not p.get("first")] + [1.0])
    val = note_sku_val(kind, text)
    note = {"val": val, "vals": [val], "pno": base["pno"], "mult": base.get("mult", 1),
            "cost": base.get("cost"), "price": round(top, 2), "ppt": 2,
            "first": False, "note": True, "kind": kind,
            "text": desc_text or text,
            "applies": list(applies or []), "acct": base.get("acct")}
    plan.append(note)
    print("  → %s 写不进 SKU 名，已加一格说明：%s（类型=%s｜价 %.2f｜库存 1｜不参与改价）"
          % (NOTE_KIND.get(kind, ("说明", ""))[1], val,
             NOTE_KIND.get(kind, ("说明", ""))[0], note["price"]))
    if applies:
        print("     受影响档位：%s" % "、".join(applies))
    return note


def add_period_note_sku(spec, plan, period, applies=None):
    """SKU 格里写不下周期 → 额外加一格「周期说明·…」（2026-11-03 用户定）。

    `applies` = 哪些档位放不下（写进说明档并在描述里点名），买家才知道是哪一类档要注意。
    """
    if not period or spec.get("period_sku") is False:
        return None
    return add_note_sku(spec, plan, "period", "%s充1次" % period, applies=applies,
                        desc_text="%s统一充值 1 次" % period)


def _copy_title(name, plan, kaomi, period="", sku_mode="highest"):
    """标题 = 【标签】+ 产品名 + 周期 + 档位摘要 + 承诺词；按 90 字节上限逐级降级。

    🔴 2026-11-15（用户定）：档位摘要默认只写**在售档位中的最高档**，与主图 `highest` 同口径；
       显式 `sku_mode="all"` 才铺全部在售档位。plan 已过成本闸，故「在售」= plan。
    """
    tag = "【官方卡密】" if kaomi else "【自动充值】"
    sign = "自动发货" if kaomi else "直充自己账号"
    vals = []
    for p in plan:
        if p.get("first") or p.get("note"):
            continue
        v = str(p.get("val") or "")
        if period and ("·" + period) in v:
            v = v.split("·" + period)[0]        # SKU 名里的周期后缀不重复进标题
        if v and v not in vals:
            vals.append(v)
    # 最高档模式：只保留同单位可比较的最大档；全档模式：按档位从小到大排序。
    # 无法唯一比较时退回原顺序（宁可不动，不写错档）。
    if len(vals) > 1:
        try:
            from replica_main_image import _tier_measure
            scored = []
            for v in vals:
                m = _tier_measure(v)
                if m:
                    scored.append((m[0], m[1], m[2], v))
            comparable = (scored and len({s[0] for s in scored}) == 1
                          and len({s[1] for s in scored}) == 1)
            if str(sku_mode or "highest").lower() == "highest":
                if comparable:
                    best = max(s[2] for s in scored)
                    top = [s[3] for s in scored if s[2] == best]
                    if len(top) == 1:
                        vals = top
                    else:
                        print("  [⑪] 最高档位并列（%s）→ 标题改用全档，避免写错档" % "/".join(top))
                elif scored and len(vals) > 1:
                    print("  [⑪] 档位单位混杂，标题保留全档，避免跨单位换算")
            elif comparable:
                vals = [s[3] for s in sorted(scored, key=lambda x: x[2])]
        except Exception as e:
            print("  [⑪] 档位排序/最高档判定失败（%s）→ 保持原顺序" % e)
    # 档位摘要：多档时剥掉公共后缀（如「代金券」），压成「50元/100元」省字节
    # ⚠️ 公共后缀可能吃掉单位（100元代金券 vs 50元代金券 → "元代金券"），单位须留下
    _UNIT = "元个天周月年币点份张"
    suf = ""
    if len(vals) > 1:
        suf = vals[0]
        for v in vals[1:]:
            while suf and not v.endswith(suf):
                suf = suf[1:]
        # 公共后缀不能以数字开头：100元代金券 vs 50元代金券 会算出「0元代金券」，
        # 剥掉就变成 10 / 5 —— 数字必须留在档位值里
        while suf and suf[0].isdigit():
            suf = suf[1:]
        if len(suf) <= 1:
            suf = ""
    core = []
    # 单位要整段留下：suf='元代金券' 取前导单位段 '元'；suf='个月' 取 '个月'（两者都是单位字）。
    # 旧实现只追加 suf[0]，把「1个月/3个月/12个月」压成「1个/3个/12个」，单位错成「个」。
    unit_prefix = ""
    for ch in suf:
        if ch in _UNIT:
            unit_prefix += ch
        else:
            break
    for v in vals:
        c0 = v[:-len(suf)] if (suf and len(v) > len(suf)) else v
        if unit_prefix and not c0.endswith(unit_prefix):
            c0 += unit_prefix
        core.append(c0)
    short = "/".join(core[:4]) if len(core) <= 4 else ("%s等%d档" % (core[0], len(core)))
    pg = (" " + period) if period else ""
    # 先保「信息层级」再保名字长度：带标签+周期+档位的短名，优于无标签的长名。
    builders = [
        lambda nm: "%s%s%s %s %s" % (tag, nm, pg, short, sign),
        lambda nm: "%s%s%s %s" % (tag, nm, pg, short),
        lambda nm: "%s%s%s %s" % (tag, nm, pg, sign),
        lambda nm: "%s%s%s" % (tag, nm, pg),
        lambda nm: "%s %s%s" % (nm, short, pg),
        lambda nm: "%s%s" % (nm, pg),
        lambda nm: "%s %s" % (nm, short),
        lambda nm: "%s %s" % (nm, sign),
    ]
    for build in builders:
        for nlen in (22, 18, 14, 12):
            c = re.sub(r"\s+", " ", build(name[:nlen])).strip()
            if title_weight(c) <= TITLE_MAX_BYTES:
                return _no_time(c)
    return _no_time((tag + name[:22])[:30])


def _no_time(text):
    """出站前最后一道：删掉到账/发货时效承诺（口径唯一来源 alds_kit.copy）。

    为什么放在出站口而不是各段生成处：文案有 5 段来源（模板 / 上游详情 / 售后条款 /
    档位对照 / 话题），任何一段都可能带上「24小时自动发货」。在生成处各拦一次 =
    五份规则，必然漏一段；在出站口拦一次，漏不掉。
    """
    try:
        from alds_kit.copy import strip_time_promise
        return strip_time_promise(text)[0]
    except Exception:
        return text          # 清洗模块异常不能挡住上品，宁可带着风险上，也要在日志里留痕
    

def sanitize_buyer_copy(text, plan=None, acct=None):
    """Remove supplier-only identifiers and website references from buyer-facing copy."""
    s = str(text or "")
    # Strip labeled source IDs without touching ordinary tier/price numbers.
    s = re.sub(r"[（(\[【]?\s*(?:货源|供应商|上游)\s*(?:商品)?\s*(?:编号|ID|商品号)\s*[:：#]?\s*[A-Za-z0-9_-]+\s*[）)\]】]?", "", s, flags=re.I)
    # Supplier links/domains must never be exposed in listing copy.
    s = re.sub(r"https?://\S+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}\S*|\b[A-Za-z0-9.-]+\.(?:cn|com|net|top|cc|io)\b", "", s, flags=re.I)
    # Remove explicit vendor/source labels, not product/brand names in normal prose.
    vendors = ("志远", "商战", "思券", "星芒", "省省", "追梦", "千城", "qqkami", "zy.kkam", "sqqy88", "xmang")
    for vendor in vendors:
        s = re.sub(r"(?:货源|供应商|上游|网站|渠道)(?:名称)?\s*[:：是为来自于-]*\s*" + re.escape(vendor), "", s, flags=re.I)
        s = re.sub(re.escape(vendor) + r"\s*(?:货源|供应商|网站|渠道)", "", s, flags=re.I)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return _no_time(s.strip())


def resolve_spec_buyer_field(spec):
    """买家填写文案里的「具体标识」：手机号 / 微博昵称 / 华为账号 / 比心ID …

    🔴 2026-11-14 补：按阿奇索 ID 上 SKU 的流程，spec 里通常没有 `buyer_field`
    （用户只给商品 ID），于是描述【填写内容】只能写「按页面提示填写」——
    比原来的「充值账号」更含糊，等于把买家该填什么又丢了一次。
    这里统一从货源 detail 现场解析：spec 显式给了就用，否则用缓存的
    `rechargeTemplates` + 说明原文走 `replica_main_image.resolve_buyer_field`（同一份词典）。
    解析不出（卡密 / 原文没写填什么）→ 返回空串，描述走「按页面提示填写」，不猜。
    """
    if "_buyer_field_resolved" in spec:
        return spec["_buyer_field_resolved"]
    cur = str(spec.get("buyer_field") or "").strip()
    if cur:
        spec["_buyer_field_resolved"] = cur
        return cur
    val = ""
    if spec.get("kind", "recharge") not in ("kaomi", "kaomi_multi"):
        c = spec.get("_detail_cache") or {}
        try:
            import replica_main_image as R
            bf = R.resolve_buyer_field(c.get("recharge_templates") or [],
                                       c.get("text") or "", c.get("notice") or "")
        except Exception as e:
            bf = {"field": "", "fallback": True, "evidence": "解析失败：%s" % e}
        if not bf.get("fallback"):
            val = str(bf.get("field") or "").strip()
            print("  买家填写 : %s（%s）" % (val, bf.get("evidence", "")))
        else:
            print("  买家填写 : ⚠️ 未解析出具体标识（%s）→ 描述写「按页面提示填写」，不猜"
                  % bf.get("evidence", ""))
    if val:
        spec["buyer_field"] = val
    spec["_buyer_field_resolved"] = val
    return val


def _copy_desc(name, detail_text, plan, kaomi, period="", applies=None, buyer_field=""):
    """描述：**版式沿用老文案**，只有【使用说明】一段取自详情（且只取要点）。

    2026-11-02 用户定：
      · 详情「部分取」——只有【使用说明】段来自上游详情（`pick_detail_parts`，≤260 字）；
      · 「其他的还是要根据之前的文案进行编写」——段落结构照旧：
        【产品名 · 官方卡密/官方直充】→ 本店一句 → 【填写内容】→ 【发货方式】
        → 【使用说明】→ 【档位对照】→ 三段标准条款 → 话题。
    详情摘完为空 → 整段不写，不留空标题。

    2026-11-14（165 事故）：【填写内容】不许再写死「充值账号」——那是阿奇索字段名，
    买家会当成要填会员 ID。`buyer_field` 传具体标识（手机号/微博昵称/华为账号），
    没传就写「按页面提示填写」，不编具体项。
    """
    body = pick_detail_parts(detail_text)
    L = []
    L.append("【%s · %s】" % (name, "官方卡密" if kaomi else "官方直充"))
    L.append("本店为官方卡密自动发货，付款后系统自动发码，无需人工值守。" if kaomi
             else "本店对接官方渠道自动充值，下单后系统自动提交，无需人工值守。")
    L.append("")
    if kaomi:
        L.append("【填写内容】无需填写账号，付款后在订单详情或闲鱼消息中查看卡密。")
        L.append("【发货方式】付款后系统自动发卡密 → 按下方说明兑换 → 权益到账即用")
    else:
        if buyer_field:
            L.append("【填写内容】%s——下单时填写%s，请务必核对无误。"
                     % (buyer_field, buyer_field))
            L.append("【充值方式】下单准确填写%s → 系统自动提交直充 → 权益到账后即可使用"
                     % buyer_field)
        else:
            L.append("【填写内容】下单时按页面提示填写充值所需信息（一般为账号绑定的手机号或账号），"
                     "请务必核对无误。")
            L.append("【充值方式】下单准确填写充值信息 → 系统自动提交直充 → 权益到账后即可使用")
    if period:
        L.append("")
        L.append("【充值周期】本商品为周期制：%s统一充值 1 次，不是下单即刻到账，请按周期等待。"
                 % period)
        # 有些档的名称里塞不下周期（多维度 / 名太长）→ 这里点名，别让买家以为只有部分档是周期制
        if applies and not any(p.get("note") for p in plan):
            show = "、".join(str(x) for x in applies[:3])
            if len(applies) > 3:
                show += " 等 %d 档" % len(applies)
            L.append("（注：%s的档位名称里未标注周期，同样按上面周期执行，不影响使用。）" % show)
    if body:
        L.append("")
        L.append("【使用说明】")
        L.append(body)
        # 详情被截断/过滤（只取了部分）→ 明说还有更多条款，避免买家以为条款就这些
        if len(body) < len(str(detail_text or "")) * 0.9:
            L.append("（以上为主要说明，完整条款见卡密内说明）")
    rows = [p for p in plan if not p.get("first") and not p.get("note")]
    if rows:
        L.append("")
        L.append("【档位对照】")
        for p in rows:
            L.append("%s —— %.2f 元" % (plan_disp(p), float(p.get("price") or 0)))
    _notes = [p for p in plan if p.get("note")]
    if _notes:
        n = _notes[0]
        kind = n.get("kind") or "period"
        label, what = NOTE_KIND.get(kind, ("说明", "说明"))
        real = [plan_disp(p) for p in plan if not p.get("first") and not p.get("note")]
        ex = "、".join(real[:3]) if real else "前面带具体规格的档位"
        L.append("")
        L.append("【%s】最后一档「%s」是「%s」类档位的说明：%s，不是可购买档位，"
                 "请勿拍；正常下单请选 %s 这类实际档位。"
                 % (label, plan_disp(n), what,
                    n.get("text") or ("%s统一充值 1 次" % period), ex))
        ap = [str(x) for x in (n.get("applies") or [])]
        if ap:
            show = "、".join(ap[:3]) + (" 等 %d 档" % len(ap) if len(ap) > 3 else "")
            L.append("（%s的名称里放不下周期，同样按上面的%s执行，不影响使用。）"
                     % (show, what))
    for head, txt in COPY_CLAUSE["kaomi" if kaomi else "recharge"]:
        L.append("")
        L.append(head)
        L.append(txt)
    L.append("")
    L.append("#%s #%s %s" % ("官方卡密" if kaomi else "官方直充",
                             "自动发货" if kaomi else "自动充值",
                             ("#" + name.replace(" ", "")) if name else ""))
    return _no_time("\n".join(L).strip())


def auto_copy(spec, plan, acct):
    """按上游详情补全 title/desc（**只补 spec 没给的那一项**，不会覆盖手写文案）。

    · 素材 = `_apply_detail_text` 缓存的详情（文字或图片识别结果）
    · 开关：`"copy_from_detail": false` 关闭；`"title"`/`"desc"` 显式给出则以 spec 为准
    · 详情为空 → 不生成（保留 spec，避免凭空编）
    """
    if spec.get("copy_from_detail") is False:
        print("\n-- 文案（据上游详情）--\n  spec.copy_from_detail=false → 不用详情生成")
        return None
    c = spec.get("_detail_cache") or {}
    text = (c.get("text") or "").strip()
    if not text:
        print("\n-- 文案（据上游详情）--\n  无详情素材 → 沿用 spec 手写文案")
        return None
    kind = spec.get("kind", "recharge")
    kaomi = kind in ("kaomi", "kaomi_multi")
    name = clean_goods_name(c.get("name") or spec.get("product") or "")
    # 上游名常把某一档的面额写进去（「古茗10元代金券」），会把单档误当整品 → 去掉「数字+单位」留产品名
    for v in sorted({str(p.get("val") or "") for p in plan}, key=len, reverse=True):
        if v and name.endswith(v):
            core = re.sub(r"^\s*\d+(?:\.\d+)?\s*[元个天周月年币点份张]?", "", v)
            if core and core != v:
                name = name[: -len(v)] + core
                break
    else:
        # 另一种写法：「哈根达斯代金券100元」= 产品名 + 面额后缀（多档时可被当成整品名）
        # 仅当后缀数字确实是某个档位值的前缀才剥，避免把「5元」这种误删。
        m = re.search(r"(\d+(?:\.\d+)?)\s*([元个天周月年币点份张])$", name)
        if m and any(str(p.get("val") or "").startswith(m.group(1)) for p in plan):
            name = name[: m.start()].strip()
    print("\n-- 文案（据上游详情 pno=%s）--" % c.get("pno"))
    print("  产品名 : %s" % name)
    period = spec.get("_period") or ""
    if period:
        print("  周期   : %s（%s）" % (period, spec.get("_period_where") or "已标注"))
    if not (spec.get("title") or "").strip():
        spec["title"] = _copy_title(name, plan, kaomi, period,
                                    spec.get("title_sku_mode") or "highest")
        print("  标题   : %s（%.1f/%d 字节）"
              % (spec["title"], title_weight(spec["title"]), TITLE_MAX_BYTES))
    else:
        print("  标题   : spec 已提供，保留")
    if spec.get("desc") is None:
        parts = pick_detail_parts(text)
        spec["desc"] = _copy_desc(name, text, plan, kaomi, period,
                                  applies=spec.get("_period_applies") or [],
                                  buyer_field=resolve_spec_buyer_field(spec))
        print("  描述   : 已据详情生成 %d 字（详情原文 %d 字 → 摘录 %d 字 + 档位对照 + 三段条款）"
              % (len(spec["desc"]), len(text), len(parts)))
        if not parts:
            print("           ⚠️ 详情摘不出可用要点，商品说明段留空（未整段照搬）")
    else:
        print("  描述   : spec 已提供，保留")
    # Buyer-facing copy may never expose supplier IDs, names, or websites.
    if spec.get("title"):
        spec["title"] = sanitize_buyer_copy(spec["title"], plan, acct)
    if spec.get("desc") is not None:
        spec["desc"] = sanitize_buyer_copy(spec["desc"], plan, acct)
    print("  -------- 生成结果 --------")
    if spec.get("desc"):
        for ln in str(spec["desc"]).splitlines():
            print("  | " + ln)
    print("  --------------------------")
    spec["_copy_name"] = name   # 供⑫后描述价回填复用，避免重算名称口径漂移
    return spec



# 「起充」与「起购」两种写法都要认 —— 2026-10-18 志远 9162 名称写「1面值--5份起购」。
# 「份」是计价单位（1 份 = 1 元面值），与 multiple 同义；「元」是金额。两者都归一到起充额。
_START_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:元|份)?\s*起(?:充|购)")


def name_start_amount(name):
    """从货源**名称**解析「X元起充」声明的起充金额；解析不到返回 None。

    2026-10-18 晋江实证：接口 minQuantity 与名称会互相打架 ——
    17302 名称写「30元起充」但 minQuantity=10，10/20 元档挂上去看着名实不符。
    规则：**两者取严**（name 声明 > minQuantity），mult 必须 ≥ 名称声明的起充额。
      · 「1元-30元起充」 → 30（正则天然只吃紧跟「起充」的数字）
      · 「1元-5元起充」  → 5
    """
    m = _START_RE.search(name or "")
    try:
        return float(m.group(1)) if m else None
    except Exception:
        return None


# 货源描述里的「余额门槛」：平台账户余额大于5000 / 余额不低于1000 …
_LB_TEXT_RE = re.compile(r"(?:账户)?余额\s*(?:大于|不低于|不得低于|须大于|需大于|≥|>=|超过)\s*([0-9]+(?:\.[0-9]+)?)")


def limit_balance_of(detail):
    """货源要求的「最低账户余额」：接口 limitBalance 与描述文字**取严**（谁大听谁的）。"""
    lb = 0.0
    try:
        lb = float((detail or {}).get("limitBalance") or 0)
    except Exception:
        lb = 0.0
    txt = " ".join(str((detail or {}).get(k) or "")
                   for k in ("goodsDescribe", "notice", "info", "name"))
    for m in _LB_TEXT_RE.finditer(txt):
        try:
            lb = max(lb, float(m.group(1)))
        except Exception:
            pass
    return lb


def prefilter_spec_costs(spec, acct):
    """在 resolve_skus 定价前剔除成本>¥20 的档，并保留淘汰清单。

    成本必须来自 spec.cost 或真实货源详情；无法核实即中止，不允许以未知成本进入上架流程。
    """
    rows = spec.get("skus") or []
    if not rows:
        return spec, []
    # 🔴 2026-11-12：允许单个 spec 用 "sku_cost_max" 显式豁免成本上限，不改全局默认。
    cap = float(spec.get("sku_cost_max", SKU_COST_MAX))
    out = copy.deepcopy(spec)
    kept, dropped = [], []
    for s in rows:
        pno = s.get("pno")
        a = int(s.get("acct") or acct)
        cost = s.get("cost")
        if cost is None and pno:
            cost = D.cost(pno, a)
        if cost is None:
            raise SystemExit("档 %s 无法核实真实成本，按成本上限规则中止；请补 cost 或核实货源。" % (s.get("val") or s.get("vals") or pno or "?"))
        cost = float(cost)
        s2 = copy.deepcopy(s)
        s2["cost"] = cost
        if cost > cap:
            tag = s.get("val") or "|".join(str(v) for v in (s.get("vals") or [])) or str(pno or "?")
            dropped.append((str(tag), "成本 %.2f>%.2f" % (cost, cap)))
            print("  %-22s ❌ 不上（%s 元）" % (tag, dropped[-1][1]))
        else:
            kept.append(s2)
    out["skus"] = kept
    return out, dropped


def prefilter_spec_suspended(spec, acct):
    """🔴 2026-11-13 停售前置闸：剔除 isAllowPurchase=false 的货源档（避免上架后发不出货）。

    与 prefilter_spec_costs 同理，在定价前剔除。整件依赖方已在主流程处理「全剔光→中止」。
    未知可售态（取数失败/字段缺失）保守保留，不阻断。
    """
    rows = spec.get("skus") or []
    if not rows:
        return spec, []
    out = copy.deepcopy(spec)
    kept, dropped = [], []
    for s in rows:
        pno = s.get("pno")
        a = int(s.get("acct") or acct)
        if pno and A.supplier_allowed(a, pno) is False:
            tag = s.get("val") or "|".join(str(v) for v in (s.get("vals") or [])) or str(pno or "?")
            dropped.append((str(tag), "货源暂停销售 isAllowPurchase=false"))
            print("  %-22s ❌ 不上（%s）" % (tag, dropped[-1][1]))
        else:
            kept.append(s)
    out["skus"] = kept
    return out, dropped


def filter_plan_limits(plan, acct, cost_max=None, price_max=None, spec=None, profit=None):
    """SKU 级不上架闸门：成本>20、货源余额门槛≥500、售价>150 分别独立判定。

    2026-11-12 用户明确：¥20 限制对象是货源成本，不是售价；售价可以超过 ¥20。
    另保留既有 ¥150 售价上限和货源余额门槛规则。

    货源余额门槛取接口 limitBalance 与描述文字（goodsDescribe/notice/info/name）中的较大值。
    命中任一条件只剔该 SKU，其余档照常上；全被剔光才整件不上。
    2026-11-12：cost_max / price_max 可由单个 spec 显式覆盖（不改全局默认）。
    返回 (保留的 plan, [(档位, 原因, 货源名)])。
    """
    cost_max = SKU_COST_MAX if cost_max is None else float(cost_max)
    price_max = SKU_PRICE_MAX if price_max is None else float(price_max)
    print("\n-- SKU 上限校验（成本>%g 元 / 货源余额门槛≥%d 元 / 售价>%g 元 → 该档不上）--"
          % (cost_max, LIMIT_BALANCE_MAX, price_max))
    kept, dropped, cache = [], [], {}
    for p in plan:
        pno = p.get("pno")
        tag = "%s(%s)" % (p.get("val") or "", pno or "-")
        try:
            price = float(p.get("price") or 0)
        except Exception:
            price = 0.0
        lb, nm = 0.0, ""
        if pno:
            a = int(p.get("acct") or acct)
            k = (str(pno), a)
            if k not in cache:
                cache[k] = D.detail(pno, a) or {}
            lb = limit_balance_of(cache[k])
            nm = cache[k].get("name") or ""
        why = []
        try:
            cost = float(p.get("cost")) if p.get("cost") is not None else None
        except Exception:
            cost = None
        if cost is not None and cost > cost_max:
            why.append("成本 %.2f>%g" % (cost, cost_max))
        if lb >= LIMIT_BALANCE_MAX:
            why.append("货源门槛余额≥%.0f" % lb)
        if price > price_max:
            why.append("售价 %.2f>%g" % (price, price_max))
        if why:
            # 🔴 2026-11-15 用户定：「货源网站有余额限制换货源，没有就不上的不上」
            #    余额门槛命中时**先换源**（其他站点同档同产品线、无门槛、成本合格），
            #    换到就替换本档的 pno/acct/cost 继续上；换不到才剔除。
            #    成本/售价超闸不换源（换源救不了成本），直接剔。
            switched = False
            if any(w.startswith("货源门槛余额") for w in why):
                try:
                    import sourcing as _SRC
                    _spec = spec or {}
                    _val = p.get("val") or "|".join(p.get("vals") or [])
                    _kw = str(_spec.get("keyword") or "").strip() or \
                        str(_spec.get("name") or "").strip() or _val
                    _pf = profit if profit is not None else _spec.get("profit", D.DEFAULT_PROFIT)
                    _best, _cands = _SRC.find_alternate_source(
                        _val, _kw, int(p.get("acct") or acct),
                        ref_title=str(_spec.get("ref_title") or ""),
                        want_kind={"recharge": 1, "kaomi": 2}.get(str(_spec.get("kind") or "")),
                        cost_max=cost_max)
                    if _best:
                        print("  %-22s 🔄 换源 → %s pno=%s 成本=%.2f（原源有余额门槛 %.0f）"
                              % (tag, _SRC.acct_label(_best["acct"]),
                                 _best["pno"], float(_best["cost"]), lb))
                        p["switched_from"] = "%s pno=%s" % (nm or ("acct=%s" % a), pno)
                        p["pno"] = _best["pno"]
                        p["acct"] = _best["acct"]
                        p["cost"] = _best["cost"]
                        # 换源后成本变了 → 按同一利润率重算售价，避免利润率漂移
                        try:
                            _newc = float(_best["cost"])
                            p["price"] = round(_newc / (1.0 - float(_pf)), 2)
                            print("  %-22s    售价重算 %.2f → %.2f（成本 %.2f / 利润率 %.1f%%）"
                                  % ("", price, p["price"], _newc, float(_pf) * 100))
                        except Exception:
                            p["price"] = price
                        kept.append(p)
                        switched = True
                    else:
                        _hint = "；".join(
                            "%s:%s" % (_SRC.acct_label(c["acct"]), c["skip"])
                            for c in _cands[:3] if c.get("skip")) or "其他站点无同档同产品线货源"
                        print("  %-22s ⚠️ 换源失败 → %s" % (tag, _hint))
                except Exception as _e:
                    print("  %-22s ⚠️ 换源异常：%s" % (tag, str(_e)[:80]))
            if not switched:
                print("  %-22s ❌ 不上（%s）" % (tag, "；".join(why)))
                dropped.append((tag, "；".join(why), nm))
        else:
            cost_text = "未知" if cost is None else "%.2f" % cost
            print("  %-22s 成本=%-8s 门槛余额=%-6s 售价=%-8.2f ✅" %
                  (tag, cost_text, ("%.0f" % lb) if lb else "0", price))
            kept.append(p)
    if dropped:
        print("  ⚠️ 剔除 %d 档，其余 %d 档照常上" % (len(dropped), len(kept)))
        for tag, w, nm in dropped:
            print("     · %s → %s%s" % (tag, w, ("｜" + str(nm)[:36]) if nm else ""))
    return kept, dropped


def check_balance(plan, acct):
    """🔴 余额闸 —— 2026-10-18 加：余额不足 → 下单必失败（买家付了钱发不出货）。

    每档需求量 = max(本档进价, 货源 limitBalance)：
      · 进价 = 至少要能跑成一单；
      · limitBalance = 货源方的硬门槛（志远 goodsDescribe 常写「平台账户余额大于5000」，
        如美图设计室 21956-21959 全是 5000）。
    同平台取最大需求。返回 [(acct, 余额, 需求)] 供 --go 中止。
    """
    print("\n-- 货源余额校验 --")
    _dc = {}
    need = {}
    for p in plan:
        a = int(p.get("acct") or acct)
        cost = float(p.get("cost") or 0)
        lb = 0.0
        pno = p.get("pno")
        if pno:
            k = (str(pno), a)
            if k not in _dc:
                _dc[k] = D.detail(pno, a) or {}
            try:
                lb = limit_balance_of(_dc[k])
            except Exception:
                lb = 0.0
        need[a] = max(need.get(a, 0.0), cost, lb)
    bad = []
    for a, n in need.items():
        bal = D.balance(a)
        if bal is None:
            print("  %-14s 余额读取失败 ⚠️ 请人工确认（需≥%.2f）" % (D.ACCT_PLATFORM.get(a, a), n))
            continue
        ok = float(bal) >= n
        print("  %-14s 余额=%-10s 需≥%-9.2f %s" % (D.ACCT_PLATFORM.get(a, a), bal, n, "✅" if ok else "❌ 不足"))
        if not ok:
            bad.append((a, bal, n))
    if bad:
        print("  ❌ 余额不足 → 买家付款后无法下单发货，千万别上架。")
        for a, bal, n in bad:
            print("     · %s：当前 %s，至少需 %.2f（差额 %.2f）"
                  % (D.ACCT_PLATFORM.get(a, a), bal, n, n - float(bal)))
    return bad


def check_bounds(plan, acct):
    """🔴 起购区间（最低起充）校验 —— 2026-10-18 用户定：**每次上品必查**。

    货源按「份数」计价（1 份 = 1 元面值），SKU 的 multiple 就是份数；
    multiple < minQuantity → 货源判「低于起充」→ 订单不发货（买家付了钱拿不到货）。
    返回越界档列表；--go 模式下越界即中止、不写任何配置。

    2026-10-18 增补「名实相符」交叉校验：同时解析货源名里的「X元起充」，
    与 mult 比对（取严）。原因：17302 名称写 30 元起充、接口写 10，10/20 元档
    挂上去名实不符 —— 供应商若真按名称校验就是「付钱不发货」。
    """
    print("\n-- 起购区间（最低起充）校验 --")
    bad = []
    for p in plan:
        pno = p.get("pno")
        if not pno:
            continue
        a = int(p.get("acct") or acct)
        mult = int(p.get("mult") or 1)
        if a not in D.VERIFIABLE_ACCTS:
            # 2026-11-12 澄清：这里缺的只是「起购区间 min/max」数据；
            # 余额另由 check_balance → D.balance() 自动校验（思券走手机通道，已可读）。
            print("  %-16s pno=%-6s multiple=%-4s ⚠️ 平台 %s 无起购区间数据，跳过起购校验"
                  % (plan_disp(p), pno, mult, D.ACCT_PLATFORM.get(a, a)))
            continue
        d = D.detail(pno, a) or {}
        mn, mx = d.get("minQuantity"), d.get("maxQuantity")
        nm = name_start_amount(d.get("name"))
        if mn is None or mx is None:
            if nm is not None and mult < nm:
                print("  %-16s pno=%-6s multiple=%-4s ❌ 货源名写明「%g元起充」，本档不足"
                      % (plan_disp(p), pno, mult, nm))
                bad.append((p, nm, nm))
            else:
                print("  %-16s pno=%-6s multiple=%-4s ⚠️ 货源未返回起购区间，请人工确认"
                      % (plan_disp(p), pno, mult))
            continue
        # 名实相符：接口区间 + 名称声明，两者取严
        if nm is not None and nm < float(mn):
            nm = float(mn)          # 名称比接口还松 → 以接口为准（不可能更松）
        floor = max(float(mn), nm) if nm is not None else float(mn)
        ok = floor <= mult <= float(mx)
        why = ""
        if not ok and nm is not None and mult < nm <= float(mx):
            why = "（名实不符：接口 min=%s，但货源名写「%g元起充」）" % (mn, nm)
        print("  %-16s pno=%-6s multiple=%-4s 区间[%s~%s]%s %s"
              % (plan_disp(p), pno, mult, mn, mx,
                 ("，名称起充%g" % nm) if nm is not None else "", "✅" if ok else "❌ 越界" + why))
        if not ok:
            bad.append((p, floor, mx))
    if bad:
        print("  ❌ %d 档份数不在货源起充区间内 → 下单必被货源拒（不发货）。" % len(bad))
        for p, mn, mx in bad:
            print("     · %s：multiple=%s，须落在 [%s~%s]" % (plan_disp(p), p.get("mult"), mn, mx))
    return bad


# ===== 多维度（多规格属性）支持 —— 2026-10-16 新增 =====
# 单维度（旧）：spec["property"]="档位" + sku 项 {"val":"VIP7天"}   ← 完全兼容，行为不变
# 双/多维    ：spec["properties"]=[{"name":"会员","values":["VIP","SVIP"]},
#                                 {"name":"时长","values":["7天","1个月","3个月","12个月"]}]
#             + sku 项 {"vals":["VIP","7天"], ...}（顺序对应 properties，笛卡尔积各格一条）
# 双维度下闲鱼前台即为「先选会员 → 再选时长」的联动选择器。
SEP = "\x01"   # 组合键分隔符（仅内部使用，不展示）


def sku_key(s):
    """SKU 唯一键 = propertyList 全部 valueText 用 SEP 连接。
    单维度时 == 原 valueText（向后兼容）；多维度时 = 各维值组合键。"""
    return SEP.join(str(pp.get("valueText") or "") for pp in (s.get("propertyList") or []))


def spec_props(spec):
    """规格维度定义 → [(维度名, 声明值列表 or None)]。
    多维度走 spec["properties"]；单维度（旧）走 spec["property"]，值由 skus 推导（None）。"""
    ps = spec.get("properties")
    if ps:
        return [(str(p.get("name") or ""), list(p.get("values") or [])) for p in ps]
    return [(str(spec.get("property") or ""), None)]


def plan_disp(p):
    """plan 项展示名：单维度 = 原值；多维度 = '值1|值2'。"""
    vals = p.get("vals")
    return "|".join(str(v) for v in vals) if vals else p["val"]


def plan_prop_list(p, props):
    """按 plan 的 vals 与维度定义生成该 SKU 的 propertyList。"""
    vals = p.get("vals") or [p["val"]]
    return [{"propertyText": n, "valueText": str(v)} for (n, _), v in zip(props, vals)]


def plan_sale_properties(spec, plan, props):
    """生成 saleProperties。单维度沿用旧行为（values = 各档 val）；
    多维度用声明的 values（按声明顺序，只保留 plan 里实际出现的值）。"""
    if len(props) == 1 and props[0][1] is None:
        return [{"name": props[0][0], "values": [p["val"] for p in plan]}]
    out = []
    for i, (name, decl) in enumerate(props):
        used = []
        for p in plan:
            v = str((p.get("vals") or [p["val"]])[i])
            if v not in used:
                used.append(v)
        vals = [v for v in decl if v in used] if decl else used
        out.append({"name": name, "values": vals or used})
    return out


def snapshot(gid, item, tag="before"):
    """跑前全量快照：item + 商品级 alds + 每个 SKU 级 alds。"""
    d = os.path.join(HERE, "snapshots", "%s_%s_%s" % (gid, TS, tag))
    os.makedirs(d, exist_ok=True)
    json.dump(item, open(os.path.join(d, "item.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(A.get_goods_alds(gid), open(os.path.join(d, "goods_alds.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for s in (item.get("itemSkuList") or []):
        sid = str(s.get("skuId") or s.get("id"))
        json.dump(A.get_sku_alds(gid, sid),
                  open(os.path.join(d, "sku_alds_%s.json" % sid), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    return d


def resolve_skus(spec, acct, profit, kind):
    """补齐每档 cost/price/ppt。ppt 规则：低于进价→1(不同步)，否则→2；卡密类恒=2。

    🔴 2026-11-09 用户定：**不再自动追加「首单引流款」**（旧 2026-10-12 规则已废），
    且末尾有 NO_LOSS 硬闸，任何 price < cost 的档直接中止，不静默改价。
    FIRST_LOSS / first:true 仅为兼容历史 spec 保留，触发即被硬闸拦下。
    """
    cap = float(spec.get("sku_cost_max", SKU_COST_MAX))
    plan = []
    props = spec_props(spec)
    ndim = len(props)
    for s in spec.get("skus") or []:
        vals = s.get("vals")
        vals = [str(v) for v in vals] if vals else [str(s["val"])]
        if len(vals) != ndim:
            raise SystemExit("档 %s 的 vals 数=%d，与维度数=%d 不符（多维度须用 vals 数组）"
                             % ("|".join(vals), len(vals), ndim))
        key = SEP.join(vals)
        a = s.get("acct") or acct          # 档级货源账号（混源：志远 95425 / 商战 96810）
        cost = s.get("cost")
        if cost is None and s.get("pno"):
            cost = D.cost(s["pno"], a)
        if cost is None:
            raise SystemExit("档 %s 无法核实真实成本，按成本上限规则中止；请补 cost 或核实货源。" % key)
        cost = float(cost)
        # 成本筛选必须先于定价和 NO_LOSS，避免超成本档误触发整批亏本中止。
        if cost > cap:
            print("  %-22s ❌ 不上（成本 %.2f>%.2f 元）" % ("%s(%s)" % (key, s.get("pno") or "-"), cost, cap))
            continue
        price = s.get("price")
        if price is None:
            if cost is None:
                raise SystemExit("档 %s 缺 cost/price，且无法从货源取价" % "|".join(vals))
            if s.get("first"):
                price = _first_price(cost)   # 引流档定价口径
            else:
                price = round(float(cost) / (1 - profit), 2)
        price = round(float(price), 2)
        ppt = s.get("ppt", 1 if (cost is not None and price < float(cost)) else 2)
        plan.append({"val": key, "vals": vals, "pno": s.get("pno"), "mult": s.get("mult", 1),
                     "cost": cost, "price": price, "ppt": ppt, "first": s.get("first", False),
                     "acct": a})
    # —— 旧「默认自动追加首单引流档」已停用（2026-11-09 用户定：去掉亏本选项）——
    #    仅当 spec 显式写 "first": true 时才走这段兼容分支，且结果会被下方 NO_LOSS 硬闸拦下。
    if (spec.get("first", FIRST_DEFAULT) and kind in ("recharge", "kaomi") and ndim == 1
            and plan and not any(p["first"] for p in plan)):
        cands = [p for p in plan if p.get("cost") is not None and p.get("pno")]
        if cands:
            base = min(cands, key=lambda x: float(x["cost"]))
            lp = _first_price(base["cost"])
            plan.append({"val": "首单" + base["val"], "vals": ["首单" + base["val"]],
                         "pno": base["pno"], "mult": base["mult"],
                         "cost": base["cost"], "price": lp,
                         "ppt": 1 if lp < float(base["cost"]) else 2, "first": True,
                         "acct": base.get("acct") or acct})

    # 🔴 无亏本硬闸（2026-11-09 用户定）：任何 SKU 售价 < 进价 → 中止，不静默抬价。
    #    涵盖手写低价、first:true 自动引流价、以及未来任何新定价分支。
    if NO_LOSS:
        bad = [p for p in plan if p.get("cost") is not None
               and float(p["price"]) < float(p["cost"])]
        if bad:
            raise SystemExit(
                "SKU 不得亏本（2026-11-09 用户定，已取消首单引流款选项）：\n  "
                + "\n  ".join("%s 进价=%s 售价=%s" %
                              (plan_disp(p), p["cost"], p["price"]) for p in bad)
                + "\n请把 price 抬到 ≥ 进价，或删掉该档 / spec 里的 first:true。")
    # —— 多维度：重排 plan，使各维度的值按 spec 声明顺序「首次出现」 ——
    # 闲鱼按 SKU 首次出现顺序排列 saleProperties 里的维度值（2026-10-16 UC 实证：
    # 超级线无「7天」时，「7天」会被排到「12个月」之后）。各线档位不一致时必须
    # **交错**排列，才能让前台选择器里的值顺序与 spec 声明一致。
    if ndim > 1 and plan:
        _rank = []
        for _i, (_n, _vs) in enumerate(props):
            _rank.append({str(v): j for j, v in enumerate(_vs or [])})

        def _lex(p):
            return tuple(_rank[i].get(str(v), 900) for i, v in enumerate(p.get("vals") or []))

        def _fa(rows, i):
            """第 i 维的「首次出现」顺序。"""
            out, seen = [], set()
            for r in rows:
                v = str((r.get("vals") or [])[i])
                if v not in seen:
                    seen.add(v)
                    out.append(v)
            return out

        def _score(rows):
            """与 spec 声明顺序的前缀吻合长度之和，越大越接近期望。"""
            s = 0
            for i in range(ndim):
                fa = _fa(rows, i)
                want = [str(v) for v in (props[i][1] or []) if str(v) in set(fa)]
                n = 0
                for a, b in zip(fa, want):
                    if a != b:
                        break
                    n += 1
                s += n
            return s

        # 候选A：按（各维声明序）字典序 —— 档位完全对齐时的最优解
        cand_a = sorted(plan, key=_lex)
        # 候选B：贪心，用「新引入值的最大声明序」当键 —— 各线档位不齐时交错
        _rest, _out, _seen = list(plan), [], set()
        while _rest:
            def _key(p):
                new = [str(v) for v in (p.get("vals") or []) if str(v) not in _seen]
                rk = [_rank[i].get(str(v), 900) for i, v in enumerate(p.get("vals") or [])
                      if str(v) not in _seen]
                return (max(rk) if rk else 999, min(rk) if rk else 999)
            _pick = min(_rest, key=_key)
            _out.append(_pick)
            _rest.remove(_pick)
            _seen.update(str(v) for v in (_pick.get("vals") or []))
        plan = cand_a if _score(cand_a) >= _score(_out) else _out
    return plan


def already_built(item, plan):
    sl = item.get("itemSkuList") or []
    if len(sl) != len(plan):
        return False
    m = {}
    for s in sl:
        m[sku_key(s)] = s
    for p in plan:
        if p["val"] not in m:
            return False
        if abs(float(m[p["val"]].get("price") or -1) - p["price"]) > 0.001:
            return False
    return True


def sku_ok(cur, kind, acct, pno, ppt, mult=None, additional=None):
    if not cur:
        return False
    if int(cur.get("supplierAccountId") or 0) != int(acct):
        return False
    if str(cur.get("supplierProductNo")) != str(pno):
        return False
    if cur.get("spType") != 6 or cur.get("sendTypeOption") != 28 or cur.get("enableSendByTiqu") is not True:
        return False
    if cur.get("platformPriceType") != ppt:
        return False
    if mult is not None and int(cur.get("multiple") or 0) != int(mult):
        return False
    if kind in ("kaomi", "kaomi_multi"):
        if cur.get("productType") != 2 or (cur.get("supplierParamJson") not in ("", None)):
            return False
        # 使用说明（含上游提取的文字）改了也要重写，否则「已正确跳过」会漏掉文案更新
        if additional is not None and (cur.get("additional") or "").strip() != additional.strip():
            return False
    else:
        if not cur.get("supplierParamJson"):
            return False
        # 🔴 直充必须带买家填写项占位符（attach）；缺失→下单收不到账号→发不出货。
        # 否则 sku_ok 会误判「已正确」跳过保存，留下没有 attach 的档（15231 实测踩坑）。
        # 🔴 2026-11-13 二补：attach 还必须每项带非空 value（{$充值账号}）——
        # golden 模板带的 attach 没有 value 字段时照样发不出货（高途 1098716682922 实测踩坑）。
        _att = cur.get("attach") or []
        if not _att or not all(str(a.get("value") or "").strip() for a in _att):
            return False
    return True


# ================= 阶段 =================
def phase_build(gid, spec, plan, item, force):
    """建/改 SKU。**关键：档位集合不变时只改价/库存并保留 skuId**（避免 agiso 重排 skuId
    把已配 alds 打回孤儿配置）。只有档位集合变化才全量重建，此时随后必须重配 alds。"""
    props = spec_props(spec)
    dim_label = "/".join(n for n, _ in props)
    stock = spec.get("stock", D.DEFAULT_STOCK)

    def want_qty(p):
        """首单（引流）档库存固定 FIRST_STOCK(=10)；周期说明档 1 个；其余档用 spec["stock"]。"""
        if p.get("note"):
            return 1
        return FIRST_STOCK if p.get("first") else stock

    cur = item.get("itemSkuList") or []
    cur_by_val = {sku_key(s): s for s in cur}
    want_vals = [p["val"] for p in plan]
    same_set = (len(cur) == len(plan) and set(cur_by_val) == set(want_vals))
    sale_props = plan_sale_properties(spec, plan, props)

    if same_set and not force:
        need = any(abs(float(cur_by_val[p["val"]].get("price") or -1) - p["price"]) > 0.001
                   or cur_by_val[p["val"]].get("quantity") != want_qty(p) for p in plan)
        if not need:
            print("  [build] SKU 与价格已一致，跳过")
            return item
        newlist = []
        for p in plan:
            s = dict(cur_by_val[p["val"]])
            s["price"] = p["price"]; s["quantity"] = want_qty(p)
            s["propertyList"] = plan_prop_list(p, props)
            newlist.append(s)
        payload = _fix_multi_qty(dict(item))
        payload["saleProperties"] = sale_props
        payload["itemSkuList"] = newlist
        r = A.edit_item(payload)
        if not _ok(r):
            print("  ❌ [build] 改价失败（skuId 未变、配置安全）：%s" % json.dumps(r, ensure_ascii=False)[:170])
            return None
        print("  [build] 已改价/库存，保留 skuId %s" % [s.get("skuId") for s in newlist])
        time.sleep(1.2)
        return _dd(A.get_item(gid))

    # 档位集合变化（或 --force）→ 全量重建；skuId 会重排，随后必须重配 alds
    payload = _fix_multi_qty(dict(item))
    payload["saleProperties"] = sale_props
    payload["itemSkuList"] = []
    for i, p in enumerate(plan):
        payload["itemSkuList"].append({
            "skuId": i + 1, "price": p["price"], "quantity": want_qty(p), "outerId": "",
            "propertyList": plan_prop_list(p, props),
        })
    print("  [build] 档位变化 → 全量重建(%d SKU, 维度=%s, 库存=首单%s/其余%s)..."
          % (len(plan), dim_label, FIRST_STOCK, stock))
    r = A.edit_item(payload)
    back = _dd(A.get_item(gid))
    new_val2sid = {sku_key(s): str(s.get("skuId")) for s in (back or {}).get("itemSkuList") or []}
    old2sid = {k: str(v.get("skuId")) for k, v in cur_by_val.items()}
    reshuffled = new_val2sid != old2sid
    if not _ok(r):
        print("  ⚠️ [build] Edit 返回非成功：%s" % json.dumps(r, ensure_ascii=False)[:170])
    print("  [build] 重建完成，skuId%s变化：%s" % ("已" if reshuffled else "未",
          {str(k).replace(SEP, "|"): v for k, v in new_val2sid.items()}))
    time.sleep(1.2)
    return back


def phase_alds(gid, spec, plan, kind):
    tpl = D.golden(kind)["sku_level"]
    acct = spec.get("acct", D.DEFAULT_ACCT)
    dim_label = "/".join(n for n, _ in spec_props(spec))
    buyer_additional = spec.get("additional")
    if buyer_additional is not None:
        buyer_additional = sanitize_buyer_copy(buyer_additional, plan, acct)
        spec["additional"] = buyer_additional
    done = 0
    for p in plan:
        a = p.get("acct") or acct          # 档级货源账号优先（混源）
        cur = _dd(A.get_sku_alds(gid, p["sid"]))
        if sku_ok(cur, kind, a, p["pno"], p["ppt"],
                  p.get("mult") if kind not in ("kaomi", "kaomi_multi") else None,
                  additional=spec.get("additional")):
            print("    %-14s 已正确，跳过" % plan_disp(p))
            continue
        cfg = D.build_sku_cfg(kind, tpl, a, sku_id=p["sid"],
                              spec_name="%s:%s;" % (dim_label, plan_disp(p)),
                              pno=p["pno"], multiple=1 if kind in ("kaomi", "kaomi_multi") else p["mult"],
                              platform_price_type=p["ppt"], goods_id=gid,
                              var_key=spec.get("var_key"), var_name=spec.get("var_name"),
                              additional=spec.get("additional"))
        r = A.save_sku_alds(cfg)
        back = _dd(A.get_sku_alds(gid, p["sid"]))
        ok = sku_ok(back, kind, a, p["pno"], p["ppt"],
                    p.get("mult") if kind not in ("kaomi", "kaomi_multi") else None,
                    additional=spec.get("additional"))
        print("    %-14s pno=%-6s acc=%-6s ppt=%s %s" % (plan_disp(p), p["pno"], a, p["ppt"], "✅" if ok else "❌ %s" % str(r)[:90]))
        done += 1
    return done


def phase_alds_single(gid, spec, kind):
    acct = spec.get("acct", D.DEFAULT_ACCT)
    pno = spec["pno"]
    d = D.detail(pno, acct) or {}
    vk, vn, vd = D.param_from_detail(d)
    vk = spec.get("var_key", vk); vn = spec.get("var_name", vn)
    tpl = D.golden(kind)["goods_level"]
    cfg = dict(tpl)
    cfg.pop("createTime", None); cfg.pop("modifyTime", None)
    cfg.update(D.INVARIANT_GOODS)
    cfg["goodsId"] = str(gid); cfg["defineSku"] = False
    cfg["supplierAccountId"] = int(acct); cfg["supplierProductNo"] = str(pno)
    cfg["supplierParamJson"] = json.dumps({vk: "{$充值账号}"}, ensure_ascii=False)
    cfg["attach"] = [{"name": vk, "key": vk, "type": "text", "title": vn,
                      "desc": vd, "vali": "all", "tip": "", "value": "{$充值账号}", "required": True}]
    cfg["multiple"] = 1
    cfg["idNo"] = 0
    r = A.save_goods_alds(cfg)
    print("  [alds-单品] 商品级配货源 acc=%s pno=%s 参数=%s/%s → %s" % (acct, pno, vk, vn, _ok(r)))
    return cfg


def _ensure_vnr(gid):
    """补开「描述不符全额退」服务保障（afterSalesData.supportVnrPolicy=true）。

    ⑩ OpenRecharge 的**前置条件**：未开通会报
    「商品ID【xxx】该商品未承诺"描述不符全额退"服务保障」（failCount=1 / uncheckIdList=[gid]）。
    判据：全店 ⑩ 成功商品该值均为 true（2026-10-12 青桔街兔电单车 1092341696931 实锤）。
    做法：读 GetItemInfo → 只在 afterSalesData 置 supportVnrPolicy=true → 整体 Edit 回传
    （其余字段含原 skuId 原样，实测**不重建 SKU**）。
    """
    item = _dd(A.get_item(gid)) or {}
    if (item.get("afterSalesData") or {}).get("supportVnrPolicy"):
        return True
    e = _fix_multi_qty(copy.deepcopy(item))
    e.setdefault("afterSalesData", {})
    e["afterSalesData"]["supportVnrPolicy"] = True
    A.edit_item(e)
    time.sleep(2.0)
    c = _dd(A.get_item(gid)) or {}
    ok = bool((c.get("afterSalesData") or {}).get("supportVnrPolicy"))
    print("  [⑩] 补开「描述不符全额退」服务保障 → %s" % ok)
    return ok


def phase_910(gid, spec, kind):
    acct = spec.get("acct", D.DEFAULT_ACCT)
    golden = D.golden(kind)
    # ⑨ 登记已付款后发货
    cur = _dd(A.get_goods_alds(gid)) or {}
    if cur.get("defineSku") is (kind not in ("single", "single_recharge")) and \
       cur.get("autoSend") is True and (cur.get("idNo") or 0) != 0 and cur.get("sendTypeOption") == 28:
        print("  [⑨] 商品级已登记启用，跳过")
    else:
        A.add_goods([str(gid)])
        time.sleep(0.8)
        rec = _dd(A.get_goods_alds(gid)) or {}
        sister = _dd(A.get_goods_alds(golden["ref_goods"])) or {}
        payload = D.build_goods_cfg(kind, sister, gid, rec.get("idNo"))
        r = A.save_goods_alds(payload)
        print("  [⑨] AddGoods + 克隆%s 商品级(idNo=%s) → %s" % (golden["ref_goods"], rec.get("idNo"), _ok(r)))
        time.sleep(0.6)
    # ⑩ 标识直充（卡密类跳过）
    if kind in ("kaomi", "kaomi_multi"):
        print("  [⑩] 卡密类 → 跳过标识直充")
        return
    rows = (_dd(A.search_goods("", 1, 100)) or {}).get("items") or []
    cur = next((x for x in rows if str(x.get("goodsId")) == str(gid)), {})
    if cur.get("apiRechargeOnOff") is True:
        print("  [⑩] 已开通(apiRechargeOnOff=true)，跳过 OpenRecharge")
        return
    types = spec.get("recharge_types")
    if not types:
        fs = (spec.get("skus") or [{}])[0]
        first_pno = spec.get("pno") or fs.get("pno")
        d = D.detail(first_pno, fs.get("acct") or acct) or {}
        types, note = D.recharge_types_from_detail(d)
        print("  [⑩] 货源 pno=%s 参数推断：%s → %s" % (first_pno, note, types))
        if not types:
            ex = (cur.get("setting") or {}).get("rechargeAccountTypes")
            if ex:
                types = ex
                print("  [⑩] 货源参数为通用名 → 沿用现有直充类型 %s" % types)
            else:
                print("  ⚠️ [⑩] 货源参数为通用名且无现有配置，跳过 ⑩；"
                      "请在 spec 显式给 recharge_types 后重跑（禁止默认勾[4]）")
                return
    r = A.open_recharge([str(gid)], types)
    print("  [⑩] OpenRecharge %s → %s" % (types, json.dumps(r, ensure_ascii=False)[:200]))
    rd = (((r or {}).get("data") or {}).get("data") or {}) if isinstance(r, dict) else {}
    if (rd.get("failCount") or 0) > 0 and "描述不符全额退" in (rd.get("errMsg") or ""):
        print("  [⑩] 该宝贝未开通「描述不符全额退」→ 自动补开并重试 OpenRecharge")
        if _ensure_vnr(gid):
            r = A.open_recharge([str(gid)], types)
            print("  [⑩] 重试 → %s" % json.dumps(r, ensure_ascii=False)[:200])
    time.sleep(1.2)
    rows2 = (_dd(A.search_goods("", 1, 100)) or {}).get("items") or []
    cur2 = next((x for x in rows2 if str(x.get("goodsId")) == str(gid)), {})
    print("  [⑩] 复检 apiRechargeOnOff=%s" % cur2.get("apiRechargeOnOff"))


def phase_online(gid):
    A.save_goods_setting(gid, True, True)
    A.update_item_status(gid, True)
    time.sleep(2.0)
    st = None
    for x in (_dd(A.search_goods("", 1, 100)) or {}).get("items") or []:
        if str(x.get("goodsId")) == str(gid):
            st = x
    print("  [上架] 已提交(自动擦亮+售完上架+上架)；status=%s (0/-2 均为『已上架』) apiRechargeOnOff=%s"
          % (st.get("status") if st else "?", st.get("apiRechargeOnOff") if st else "?"))


def phase_copy(gid, spec):
    """⑪ 标题/描述文案同步（spec 提供 title/desc 才执行）。

    只改 title/desc 两个字段，其余（含 itemSkuList 的原 skuId）原样回传 →
    不会触发 SKU 重建。改完回读校验：标题/描述是否写入 + skuId 是否未重排。
    实测（2026-10-11，look直播 1087463121476）：Edit 可写回闲鱼前台，skuId 不变。
    """
    # Final write-boundary sanitation: no caller may bypass buyer-copy filtering.
    acct = spec.get("acct")
    plan = spec.get("skus") or []
    new_title = sanitize_buyer_copy((spec.get("title") or "").strip(), plan, acct)
    new_desc = sanitize_buyer_copy(spec.get("desc"), plan, acct) if spec.get("desc") is not None else None
    if new_title != (spec.get("title") or "").strip():
        print("  ⚠️ [⑪] 标题已自动移除内部货源信息")
    if new_desc is not None and new_desc != str(spec.get("desc") or "").strip():
        print("  ⚠️ [⑪] 描述已自动移除内部货源信息")
    spec["title"] = new_title
    if new_desc is not None:
        spec["desc"] = new_desc
    has_desc = new_desc is not None
    if not new_title and not has_desc:
        return None
    item = _dd(A.get_item(gid))
    if not item:
        print("  ⚠️ [⑪] 读商品失败，跳过文案同步")
        return None
    old_title = item.get("title") or ""
    old_skus = [s.get("skuId") for s in (item.get("itemSkuList") or [])]

    if new_title:
        w = title_weight(new_title)
        if w > TITLE_MAX_BYTES:
            print("  ❌ [⑪] 标题超长（%.1f > %d 字节，中文3/ASCII1.5），"
                  "跳过文案同步避免整条 Edit 被拒：%s" % (w, TITLE_MAX_BYTES, new_title))
            return None
        print("  [⑪] 标题字节权重 %.1f/%d" % (w, TITLE_MAX_BYTES))

    e = _fix_multi_qty(copy.deepcopy(item))
    if new_title:
        e["title"] = new_title
    if has_desc:
        e["desc"] = spec.get("desc")

    if ((not new_title or new_title == old_title)
            and (not has_desc or (spec.get("desc") or "").strip() == (item.get("desc") or "").strip())):
        print("  [⑪] 文案无变化，跳过")
        return None

    snapshot(gid, item, "copy_before")
    r = A.edit_item(e)
    print("  [⑪] 标题/描述同步 → %s | 标题 %d字 → %d字"
          % (_ok(r), len(old_title), len(e.get("title") or "")))
    time.sleep(2.0)
    c = _dd(A.get_item(gid)) or {}
    ct = c.get("title") or ""
    cskus = [s.get("skuId") for s in (c.get("itemSkuList") or [])]
    title_same = (ct == (e.get("title") or ""))
    desc_same = (not has_desc) or ((c.get("desc") or "").strip() == (spec.get("desc") or "").strip())
    sku_same = (cskus == old_skus)
    print("  [⑪] 回读 title=%s" % ct)
    print("  [⑪] 标题一致=%s | 描述一致=%s | SKU未重排=%s" % (title_same, desc_same, sku_same))
    if not title_same:
        print("  ⚠️ [⑪] 标题未生效（可能被平台审核/超长截断），请检查")
    if not sku_same:
        print("  ⚠️ [⑪] skuId 发生变化！请重跑配货源：python deploy.py <spec> --go")
    return None


# ===== ⑬ 上游详情图 → 宝贝图片（2026-11-02 用户定）=====
MEDIA_UPLOAD = "/api/GoodsManage/MediaUpload"   # multipart 字段名必须是 files（file/media/img 都报「上传文件数量错误」）
IMAGE_MAX = 9                                   # 闲鱼宝贝图片上限
IMAGE_ADDED = os.path.join(HERE, "detail_imgs", "added.json")   # {pno: {gid: [源图URL]}} 去重


def _detail_pno(spec, plan):
    """详情来源 pno：优先 _apply_detail_text 命中的那个，否则 spec.detail_pno / 首档 pno。"""
    c = spec.get("_detail_cache") or {}
    if c.get("pno"):
        return str(c.get("pno"))
    if spec.get("detail_pno"):
        return str(spec.get("detail_pno"))
    for p in plan or []:
        if p.get("pno"):
            return str(p.get("pno"))
    return str(spec.get("pno") or "") or None


def _img_opener():
    """下载货源图：绕本机 http_proxy，跳过证书校验（货源图床证书链本机不可信）。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                       urllib.request.HTTPSHandler(context=ctx))


def img_size(raw):
    """只读图片头拿 (宽, 高)，不依赖 PIL。失败返回 None。"""
    try:
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
            return (w, h)
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return (int.from_bytes(raw[6:8], "little"), int.from_bytes(raw[8:10], "little"))
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return None
        if raw[:2] == b"\xff\xd8":
            i = 2
            while i < len(raw) - 9:
                if raw[i] != 0xFF:
                    i += 1
                    continue
                m = raw[i + 1]
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    return (int.from_bytes(raw[i + 7:i + 9], "big"),
                            int.from_bytes(raw[i + 5:i + 7], "big"))
                i += 2 + int.from_bytes(raw[i + 2:i + 4], "big")
    except Exception:
        pass
    return None


def upload_media(raw, name="detail.png"):
    """图片 → agiso 媒体库。返回 (可写进 imgUrls 的 URL, imageId)。

    实测（2026-11-02）：接口只认 `files` 字段；返回 ossKey，拼成 oss 直链后写进 imgUrls，
    保存时后端会**自动转存到闲鱼 CDN**（回读变成 img.alicdn.com），所以不用自己传闲鱼。

    🔴 2026-11-14 模块化：实现收口到 `alds_kit.media.upload_media`（与主图上传同一份），
    旧签名保留，⑬ 详情图调用方不用改。
    """
    from alds_kit.media import upload_media as _up
    return _up(raw, name)


def _added_load():
    try:
        return json.load(open(IMAGE_ADDED, encoding="utf-8"))
    except Exception:
        return {}


def _added_save(db):
    os.makedirs(os.path.dirname(IMAGE_ADDED), exist_ok=True)
    json.dump(db, open(IMAGE_ADDED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def phase_images(gid, spec, plan, dry=False):
    """⑬ 详情是图片（或图文混合）时，把详情图追加到宝贝图片，买家在商品页就能看到。

    为什么走这里：闲鱼「描述」是纯文本，图片只能挂在宝贝图片（imgUrls）。
    做法：详情图 → agiso MediaUpload（字段 files）→ 拿到 oss 直链 → 追加进 imgUrls/imgList
    → Edit 只改图片字段（不动 SKU/标题/描述）→ 回读确认张数。保存时后端自动转存闲鱼 CDN。

    开关：`"images_from_detail": false` 关闭；`"images_max": 9` 改上限（闲鱼最多 9）。
    幂等：`detail_imgs/added.json` 记下「该 pno 的这些源图已给该 gid 加过」，重跑不会重复加。
    """
    if spec.get("images_from_detail") is False:
        print("\n-- 详情图（⑬）--\n  已显式关闭（images_from_detail=false）")
        return None
    if spec.get("detail_text") is False:
        print("\n-- 详情图（⑬）--\n  detail_text=false，按同一开关跳过")
        return None
    pno = _detail_pno(spec, plan)
    if not pno:
        print("\n-- 详情图（⑬）--\n  无可用货源号，跳过")
        return None

    print("\n-- 详情图（⑬ 上游详情图 → 宝贝图片）--")
    acct = spec.get("acct") or next((p.get("acct") for p in plan if p.get("acct")), None)
    # 详情来源可能分散在不同档：主详情 pno 是文字、另一档 pno 才有图 → 逐个试，取第一个有图的
    cands, seen = [], set()
    for x in [_detail_pno(spec, plan), spec.get("detail_pno")] + [p.get("pno") for p in (plan or [])]:
        if x and str(x) not in seen:
            seen.add(str(x))
            cands.append(str(x))
    src, pno_hit = [], None
    for x in cands[:6]:
        try:
            d = D.detail(x, acct) or {}
        except Exception as e:
            print("  pno=%s 详情读取失败：%s" % (x, e))
            continue
        s = detail_images(d)
        if s:
            src, pno_hit = s, x
            print("  pno=%s 详情图 %d 张" % (x, len(s)))
            break
    if not src:
        print("  详情无图片（试过 pno=%s），跳过" % ",".join(cands[:6]))
        return None
    pno = pno_hit

    item = _dd(A.get_item(gid)) or {}
    if not item:
        print("  ⚠️ 读商品失败，跳过")
        return None
    cur = list(item.get("imgUrls") or [])
    cap = int(spec.get("images_max") or IMAGE_MAX)
    room = max(0, cap - len(cur))
    if room <= 0:
        print("  宝贝图片已 %d 张（上限 %d），无需追加" % (len(cur), cap))
        return None

    db = _added_load()
    done = set((db.get(pno) or {}).get(str(gid)) or [])
    todo = [u for u in src if u not in done][:room]
    if not todo:
        print("  这些详情图已加过（%d 张已记录），跳过" % len(done))
        return None
    print("  现有 %d 张 → 追加 %d 张（上限 %d）" % (len(cur), len(todo), cap))
    if dry:
        print("  [dry] 未上传、未改动；--go 时才真正上传并写回宝贝图片")
        return None

    op = _img_opener()
    new_urls, added = [], []
    for u in todo:
        try:
            raw = op.open(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
        except Exception as e:
            print("  ⚠️ 下载失败，跳过：%s（%s）" % (u[-40:], e))
            continue
        if len(raw) > 10 * 1024 * 1024:
            print("  ⚠️ 超过 10MB，跳过：%s" % u[-40:])
            continue
        try:
            url, _iid = upload_media(raw, "detail_%s_%d%s" % (pno, len(new_urls) + 1,
                                                              os.path.splitext(u.split("?")[0])[1] or ".png"))
        except Exception as e:
            print("  ⚠️ 上传失败，跳过：%s（%s）" % (u[-40:], e))
            continue
        print("    上传 OK %d KB → %s" % (len(raw) // 1024, url.rsplit("/", 1)[-1]))
        sz = img_size(raw)
        if sz and sz[1]:
            ratio = sz[0] / float(sz[1])
            if not (0.75 <= ratio <= 3.0):
                print("      ⚠️ 尺寸 %dx%d（宽高比 %.2f）超出闲鱼建议 3:1~1:1.34，"
                      "前台可能被裁切" % (sz[0], sz[1], ratio))
        new_urls.append(url)
        added.append(u)
    if not new_urls:
        print("  没有成功上传的图，跳过写回")
        return None

    e = _fix_multi_qty(copy.deepcopy(item))
    e["imgUrls"] = cur + new_urls
    if "imgList" in e:
        e["imgList"] = [x for x in (e.get("imgList") or []) if x] + [{"imgUrl": u} for u in new_urls]
    snapshot(gid, item, "images_before")
    r = A.edit_item(e)
    print("  [⑬] 写回 → %s" % _ok(r))
    time.sleep(3)
    c = _dd(A.get_item(gid)) or {}
    got = c.get("imgUrls") or []
    print("  [⑬] 回读图片 %d 张（原 %d）%s" % (len(got), len(cur), "✅" if len(got) > len(cur) else "⚠️ 未增加"))
    for u in got:
        print("       %s" % u)
    if len(got) > len(cur):
        db.setdefault(pno, {})
        db[pno][str(gid)] = sorted(set(done) | set(added))
        _added_save(db)
        print("  [⑬] 已记录去重清单 detail_imgs/added.json")
    return None


def main_image_target(spec):
    """返回主图参考图使用的 (pno, acct)，支持档级货源账号。"""
    skus = spec.get("skus") or []
    pno = str(spec.get("pno") or ((skus[0] or {}).get("pno")) or "")
    acct = spec.get("acct") or D.DEFAULT_ACCT
    matching = next((x for x in skus if str((x or {}).get("pno") or "") == pno), None)
    if matching and (matching or {}).get("acct"):
        acct = matching["acct"]
    return pno, acct


def preflight_main_image(spec, plan=None):
    """在线写入前核验参考图与目标 SKU 档位，失败必须发生在首个写操作前。"""
    mode = str(spec.get("main_image") or "keep").strip().lower()
    if mode != "replica":
        return None
    pno, acct = main_image_target(spec)
    if not pno:
        raise RuntimeError("主图复刻缺少 pno，不能开始任何线上写操作")
    from alds_kit.main_image import preflight_reference
    import replica_main_image as R
    sku_mode = str(spec.get("main_image_sku_mode") or "highest").strip().lower()
    planned = []
    props = spec_props(spec)
    for sku in (plan or []):
        planned.append({"skuId": str(sku.get("sid") or sku.get("pno") or sku.get("val") or ""),
                        "propertyList": plan_prop_list(sku, props)})
    if not planned:
        raise RuntimeError("主图复刻没有可用于预检的目标 SKU 计划；拒绝在线写入")
    selection = R.select_sku_display(planned, sku_mode)
    ref = preflight_reference(pno, acct, str(spec.get("main_ref") or ""))
    if selection:
        print("  主图 SKU 预检：%s ｜ %s" % (sku_mode, selection["selection_evidence"]))
        if selection.get("reminder"):
            print("  %s" % selection["reminder"])
    return ref


def phase_main_image(gid, spec):
    """⑭ 主图（2026-11-14 新增；默认 keep，旧 spec 行为完全不变）。

    spec.main_image：
      replica → 复刻式重做（新建链路用；ID 链路可显式指定来修错图）
      keep    → 保留现有主图（缺省）。ID 链路默认走这里，主图自备并留证
      skip    → 完全不碰图片

    为什么放进 deploy：主图能力此前只存在于 create_from_pno，任何不经过它的入口
    （按阿奇索 ID 上 SKU、存量返工、老商品补图）都没有主图能力 —— 同一个错误
    修在建品链路，ID 链路看不见（2026-11-14 用户提出）。现在两条链走同一段代码。
    """
    mode = str(spec.get("main_image") or "keep").strip().lower()
    print("\n-- 主图（⑭）--")
    item = _dd(A.get_item(gid)) or {}
    urls = list(item.get("imgUrls") or [])
    head = urls[0] if urls else ""
    if mode == "skip":
        print("  main_image=skip → 不碰图片（当前 %d 张）" % len(urls))
        return
    if mode == "keep":
        print("  main_image=keep → 保留现有主图：%s ｜ 共 %d 张"
              % (head.rsplit("/", 1)[-1] if head else "无", len(urls)))
        return
    if mode != "replica":
        print("  ⚠️ 未知 main_image=%r，按 keep 处理（不动图）" % mode)
        return
    from alds_kit.main_image import ensure_main_image
    pno, acct = main_image_target(spec)
    if not pno:
        raise RuntimeError("spec 没有 pno，无法确定参考图货源")
    title = str(spec.get("title") or item.get("title") or item.get("goodsName") or "")
    # 🔴 只走能力层统一入口：重做 + 清模板残留图是同一件事，不许在编排器里再拼一遍
    cdn, _act = ensure_main_image(gid, "replica", title, pno, acct, dry=False,
                                  cli_ref=str(spec.get("main_ref") or ""),
                                  label_override=str(spec.get("account_label") or ""),
                                  template_url=str(spec.get("template_img_url") or ""),
                                  sku_display_mode=str(spec.get("main_image_sku_mode") or "highest"))
    if not cdn:
        raise RuntimeError("主图复刻未产生线上主图 URL")


def phase_autoprice(gid, spec):
    """⑫ 自动改价：给新上的宝贝逐 SKU 打开自动改价（默认售价利润率 3.5%~4.5%）。

    实测机制（2026-11-02）：
      接口 POST /api/AldsInfo/SaveGoodsAldsChangePrice
      body {defineSku:true, goodsId, changePriceSettingList:[{goodsId, skuId,
             autoChangePrice, autoChangePriceSettingJson}]}
      ⚠️ 必须是 `autoChangePriceSettingJson`（**字符串**、Key 首字母大写）；传对象或小写 Key
         会被后端静默重置成 Income=0 / 90% / 110%。
      setting = {"Income":"<元>","MinIncome":"87.5%","MaxIncome":"112.5%",
                 "DecimalHandling":0,"DecimalValue":"2"}
      Income 是**绝对金额**，Min/Max 是相对 Income 的百分比。
      售价口径利润率 r → Income = 成本 × r/(1-r)，r 取区间中值，区间自然落回 [min,max]。
    实际改价由阿奇索定时任务执行（约 5 分钟一轮），只在价格跑出区间时才动手；
    日志内嵌在每个 SKU 的「改价日志」里，无需开关。

    spec 可覆盖：
      "autoprice": false                 → 整个宝贝不开（倍拍类／成本口径不符的商品必须写）
      "autoprice_min": 3.5 / "autoprice_max": 4.5
      "autoprice_skip": ["首单","体验"]   → 值里含这些关键字的档一律关闭自动改价
    """
    if spec.get("autoprice") is False:
        print("  [⑫] spec.autoprice=false，跳过自动改价")
        return {}
    lo = float(spec.get("autoprice_min", AUTO_MIN))
    hi = float(spec.get("autoprice_max", AUTO_MAX))
    skips = list(spec.get("autoprice_skip") or AUTO_SKIP)
    if spec.get("_period_note"):
        skips = skips + ["说明"]      # 周期说明档不参与改价（价高、本就不为卖）

    item = _dd(A.get_item(gid)) or {}
    live = {str(s.get("skuId")): s.get("price") for s in (item.get("itemSkuList") or [])}
    if not live:
        print("  [⑫] 无在架 SKU（单品/未上架），跳过自动改价")
        return {}

    r = A._post("/api/UnAldsInfo/LoadAutoChangePriceList",
                {"page": 1, "pageSize": 100, "goodsId": gid})
    rows = ((_dd(r) or {}).get("changePriceList") or [])
    rows = [x for x in rows if str(x.get("skuId")) in live]
    # 刚建完 SKU 时服务端成本可能还没同步 → 最多重试 3 次（各 3s）
    for _i in range(3):
        if rows and all(float(x.get("productCost") or 0) > 0.0005 for x in rows):
            break
        if not rows:
            break
        print("  [⑫] 成本未同步齐，等待重读（%d/3）…" % (_i + 1))
        time.sleep(3.0)
        r = A._post("/api/UnAldsInfo/LoadAutoChangePriceList",
                    {"page": 1, "pageSize": 100, "goodsId": gid})
        rows = [x for x in ((_dd(r) or {}).get("changePriceList") or [])
                if str(x.get("skuId")) in live]
    if not rows:
        print("  [⑫] 改价表无在架 SKU 记录，跳过（服务端未同步？稍后可单独跑 autoprice_set.py）")
        return {}

    mid = (lo + hi) / 200.0
    ratio = mid / (1 - mid)
    rel_lo = lo / (mid * 100) * 100
    rel_hi = hi / (mid * 100) * 100
    print("  [⑫] 目标利润率 %.1f%%~%.1f%%｜期望利润=成本×%.5f｜容忍区间 %.2f%%~%.2f%%｜跳过关键字=%s"
          % (lo, hi, ratio, rel_lo, rel_hi, "/".join(skips)))

    items, skip_n, dev_n = [], 0, 0
    price_map = {}   # skuId -> 最终用于描述回填的价（开启档=目标价，关闭档=线上当前价）
    for x in rows:
        name = str(x.get("specName") or "")
        cost = float(x.get("productCost") or 0)
        sid = x["skuId"]
        cur = float(live.get(str(sid)) or 0)
        price_map[sid] = cur   # 默认=线上当前价；开启档下面覆盖为目标价
        if any(s in name for s in skips):
            items.append({"goodsId": gid, "skuId": sid, "autoChangePrice": False})
            skip_n += 1
            print("     %-24s 关闭（引流/例外档，不参与改价）" % name[:24])
            continue
        if cost <= 0.0005:
            items.append({"goodsId": gid, "skuId": sid, "autoChangePrice": False})
            skip_n += 1
            print("     %-24s 关闭（成本为 0/未登记）" % name[:24])
            continue
        inc = round(cost * ratio, 4)
        target = round(cost + inc, 2)
        # 🔴 2026-11-03：自动改价不许把售价顶过 SKU_PRICE_MAX（独立的「>150 不上」规则；¥20 只限制成本）
        if target > SKU_PRICE_MAX:
            items.append({"goodsId": gid, "skuId": sid, "autoChangePrice": False})
            skip_n += 1
            print("     %-24s 关闭（目标价 %s 超上限 %d 元，保持现价 %s）"
                  % (name[:24], target, SKU_PRICE_MAX, cur))
            continue
        if cur > 0 and abs(target - cur) / cur > AUTO_MAXDEV:
            items.append({"goodsId": gid, "skuId": sid, "autoChangePrice": False})
            dev_n += 1
            print("     %-24s 关闭（偏差 %.0f%%：现价 %s → 目标 %s，疑似倍拍/成本口径不符）"
                  % (name[:24], abs(target - cur) / cur * 100, cur, target))
            continue
        st = {"Income": "%.4f" % inc, "MinIncome": "%.1f%%" % rel_lo,
              "MaxIncome": "%.1f%%" % rel_hi, "DecimalHandling": 0, "DecimalValue": "2"}
        items.append({"goodsId": gid, "skuId": sid, "autoChangePrice": True,
                      "autoChangePriceSettingJson": json.dumps(st, ensure_ascii=False)})
        price_map[sid] = target
        print("     %-24s 开启 cost=%-9s 现价=%-8s → 期望 %s（利润率 %.2f%%）"
              % (name[:24], cost, cur, target, (target - cost) / target * 100 if target else 0))

    if not items:
        print("  [⑫] 无可提交项")
        return None
    r = A._post("/api/AldsInfo/SaveGoodsAldsChangePrice",
                {"defineSku": True, "goodsId": gid, "changePriceSettingList": items})
    d1 = (r or {}).get("data") or {}
    d2 = d1.get("data") or {}
    ok = d1.get("isSuccess")
    msg = d2.get("errMsgList") or d1.get("errMsgList") or []
    print("  [⑫] 保存=%s%s" % (ok, ("  | " + "; ".join(str(m) for m in msg)) if msg else ""))
    if msg:
        print("  ⚠️ [⑫] 服务端有拒绝项（多为「状态-2 非上架无需改价」→ 商品还没真正上架，"
              "页面刷新后单独跑 autoprice_set.py <gid> --go 补上）")
    time.sleep(1.5)
    r2 = A._post("/api/UnAldsInfo/LoadAutoChangePriceList",
                 {"page": 1, "pageSize": 100, "goodsId": gid})
    rows2 = [x for x in ((_dd(r2) or {}).get("changePriceList") or [])
             if str(x.get("skuId")) in live]
    on = [x for x in rows2 if x.get("autoChangePrice")]
    print("  [⑫] 回读 在架SKU=%d｜已开启=%d｜关闭=%d（引流/例外 %d，偏差保护 %d）"
          % (len(rows2), len(on), len(rows2) - len(on), skip_n, dev_n))
    if dev_n and not on:
        print("  ⚠️ [⑫] 全部档都被偏差保护关掉 → 该宝贝多为「倍拍」或多份计价（成本按份、售价按面额），"
              "自动改价不适用；如需静默，spec 里写 \"autoprice\": false")
    return price_map


def _align_desc_price(gid, spec, plan, price_map):
    """⑫ 自动改价后，用线上真实售价回填描述【档位对照】，根除 ⑦ 对照价不符。

    根因：⑪ 描述价用的是本地 D.cost 核算价 plan["price"]，⑫ 实付价用的是服务端
    productCost 核算价，两成本源不同一 → 图文价格不符。这里在 ⑫ 之后，用线上
    真实 SKU 价（最权威，⑦ 即以此为准）回填描述档位对照价，并同步重算 plan 价。
    优先用线上实时 get_item 的 SKU 价；缺失时回退 ⑫ 算出的 target 价。
    """
    if spec.get("desc") is None:
        return
    price_map = price_map or {}
    item = _dd(A.get_item(gid)) or {}
    live = {}
    for s in (item.get("itemSkuList") or []):
        sid = str(s.get("skuId") or s.get("id") or "")
        val = str(s.get("skuName") or s.get("skuKey") or "")
        try:
            p = float(s.get("price") or 0)
        except (TypeError, ValueError):
            p = 0
        if sid:
            live[sid] = p
        if val:
            live[val] = p
    changed = False
    for pp in plan:
        newp = None
        sid = pp.get("sid")
        if sid and sid in live and live[sid] > 0:
            newp = live[sid]
        elif pp.get("val") in live and live[pp["val"]] > 0:
            newp = live[pp["val"]]
        elif sid and sid in price_map and price_map[sid] > 0:
            newp = price_map[sid]
        if newp and abs(newp - float(pp.get("price") or 0)) > 0.011:
            pp["price"] = round(newp, 2)
            changed = True
    if not changed:
        return
    c = spec.get("_detail_cache") or {}
    text = (c.get("text") or "").strip()
    if not text:
        return
    kind = spec.get("kind", "recharge")
    kaomi = kind in ("kaomi", "kaomi_multi")
    name = spec.get("_copy_name") or clean_goods_name(c.get("name") or spec.get("product") or "")
    period = spec.get("_period") or ""
    applies = spec.get("_period_applies") or []
    new_desc = _copy_desc(name, text, plan, kaomi, period, applies=applies,
                          buyer_field=resolve_spec_buyer_field(spec))
    if new_desc and new_desc != spec.get("desc"):
        spec["desc"] = new_desc
        print("\n-- 文案（⑪ 价对齐回填，对齐线上实付价）--")
        phase_copy(gid, spec)


def phase_verify(gid):
    try:
        from agiso_audit import audit_goods
    except Exception as e:
        print("  [自检] 跳过（audit 导入失败：%s）" % e)
        return 0
    return audit_goods(gid)


# ================= 主流程 =================
def main():
    args = sys.argv[1:]
    mode = "--dry"
    force = False
    spec_path = None
    for a in args:
        if a in ("--dry", "--go"):
            mode = a
        elif a == "--force":
            force = True
        elif a.endswith(".json"):
            spec_path = a
    if not spec_path:
        print(__doc__); return
    spec = json.load(open(spec_path, encoding="utf-8"))
    # 维度名必须 2-4 个字符，否则闲鱼报
    # PLAYBOY_ERRORCODE_ITEM_SKU_PROPERTY_KEY_NAME_LENGTH_ILLEGAL（2026-10-16 实锤）
    for _pn, _ in spec_props(spec):
        if not (2 <= len(_pn) <= 4):
            print("❌ 维度名必须 2-4 个字符（当前 %r 共 %d 字）→ 闲鱼会拒建 SKU。" % (_pn, len(_pn)))
            print("   例：'京东E卡'/'档位'/'时长'/'面额'/'会员'。请改 spec 后重跑。")
            return
    gid = str(spec["goods"])
    kind = spec.get("kind", "recharge")
    acct = spec.get("acct", D.DEFAULT_ACCT)
    profit = spec.get("profit", D.DEFAULT_PROFIT)

    print("=" * 74)
    print("deploy %s | kind=%s | acct=%s(%s) | 模式=%s%s"
          % (spec_path, kind, acct, D.ACCT_PLATFORM.get(acct), mode, " | FORCE" if force else ""))
    print("=" * 74)

    item = _dd(A.get_item(gid))
    if not item:
        print("❌ 读商品失败（商品不存在/token失效/网络）"); return
    print("商品：%s | 现有SKU=%d | status=%s"
          % (str(item.get("title") or item.get("goodsName") or "")[:36],
             len(item.get("itemSkuList") or []), item.get("status")))

    # 🔴 一条龙前置硬闸（2026-11-12 建）：类型错配 / 文案缺失 / 主图未重制 三类静默坑。
    # 旧自检只查配置内部自洽，这三类错都能报「真问题=[] ✅」，故在此独立设闸。
    try:
        import onepipe_guard as _G
        _fatal, _warn = _G.preflight(spec, item, acct, kind, mode)
        if _fatal and mode == "--go" and not spec.get("allow_guard_bypass"):
            print("❌ 前置硬闸未通过，--go 已中止（未做任何改动）。修正 spec 后重跑。")
            return
    except Exception as _ge:
        print("  ⚠️ [前置硬闸] 模块异常，已跳过（不影响原流程）：%s" % str(_ge)[:120])

    # 🔴 2026-11-12：spec 级上限覆盖（"sku_cost_max"/"sku_price_max"），不写则沿用全局默认。
    _cap = float(spec.get("sku_cost_max", SKU_COST_MAX))
    _pmax = float(spec.get("sku_price_max", SKU_PRICE_MAX))
    _cost_dropped = []
    _susp_dropped = []
    # 🔴 2026-11-14 resolve 收口：只给商品 ID + 货源编号时，自动补同产品线全档。
    #    ID 链路以前必须手列 skus，漏一档就少一档，且无从知道漏了；现在由 supplier 一次算全。
    #    默认关闭（opt-in），旧 spec 行为完全不变；显式写进 skus 的档位优先，价/成本不被覆盖。
    if spec.get("auto_family") and kind not in ("single", "single_recharge"):
        _fpno = str(spec.get("pno")
                    or ((spec.get("skus") or [{}])[0] or {}).get("pno") or "")
        if not _fpno:
            print("  ⚠️ auto_family 已开但 spec 里没有 pno，无法补档，按原 skus 继续")
        else:
            try:
                from alds_kit import supplier as _S
                _new, _meta = _S.build_skus(acct, _fpno, spec.get("skus"))
                print("  auto_family：pno=%s 同线 %d 档 → 补齐后 %d 档（其中显式指定 %d 档）"
                      % (_fpno, _meta["family_count"], len(_new), _meta["explicit_count"]))
                spec = dict(spec, skus=_new)
            except Exception as _e:
                print("  ⚠️ auto_family 补档失败，按原 skus 继续：%s" % str(_e)[:120])
    if kind in ("single", "single_recharge"):
        _single_cost = spec.get("cost")
        if _single_cost is None:
            _single_cost = D.cost(spec["pno"], acct)
        if _single_cost is None:
            raise SystemExit("单品无法核实真实成本，按成本上限规则中止。")
        spec["cost"] = float(_single_cost)
        if spec["cost"] > _cap:
            print("❌ 单品成本 %.2f>%.2f 元，不发布；未做任何改动。" % (spec["cost"], _cap))
            return
        if A.supplier_allowed(acct, spec["pno"]) is False:
            print("❌ 单品货源 pno=%s 已暂停销售（isAllowPurchase=false），不发布；未做任何改动。" % spec["pno"])
            return
    else:
        spec, _cost_dropped = prefilter_spec_costs(spec, acct)
        spec, _susp_dropped = prefilter_spec_suspended(spec, acct)
    plan = resolve_skus(spec, acct, profit, kind)
    # 🔴 成本已在定价前预筛；此处再独立筛货源余额门槛≥500、售价>150，并复核成本。
    # （¥20 限进价，售价可超过¥20。过滤必须在 auto_copy 前，避免淘汰档进入标题/文案/图片）
    plan, _limit_dropped = (filter_plan_limits(plan, acct, cost_max=_cap, price_max=_pmax,
                                               spec=spec, profit=profit)
                            if plan else (plan, []))
    _dropped = _cost_dropped + _susp_dropped + _limit_dropped
    if _dropped and not plan and kind not in ("single", "single_recharge"):
        print("\n❌ 全部档位都命中上限规则（成本>%g 元 / 货源门槛余额≥%d 元 / 售价>%g 元），整件不上 —— 未做任何改动。"
              % (_cap, LIMIT_BALANCE_MAX, _pmax))
        print("   需换用门槛更低、单价更低的货源，或这个商品就不上。")
        return
    _props = spec_props(spec)
    if len(_props) > 1:
        print("\n-- 维度（多规格属性）--")
        for n, vs in _props:
            print("  %s : %s" % (n, " / ".join(vs) if vs else "(由 skus 推导)"))
    print("\n-- 计划 --")
    for p in plan:
        print("  %-16s pno=%-6s acc=%-6s 进价=%-8s 售价=%-8s ppt=%s%s"
              % (plan_disp(p), p["pno"], p.get("acct") or acct, p["cost"], p["price"], p["ppt"],
                 " [引流]" if p["first"] else ""))
    if not plan and kind not in ("single", "single_recharge"):
        print("  ⚠️ spec.skus 为空")

    # 卡密 / 直充 / 单品：使用说明与文案**都**按上游详情写（2026-11-02 用户定「卡密和直充类都一样」）
    if spec.get("detail_text") is not False:
        dst = _apply_detail_text(spec, plan, acct) or {}
        if dst.get("status") == "need_ocr" and not spec.get("allow_no_detail_text"):
            print("\n❌ 使用说明校验：详情是图片但未识别，已中止 —— 未做任何改动。")
            print("   使用说明必须据上游详情写（文字或图片识别），不能凭空编。")
            if mode == "--go":
                return
            print("   [dry] 仅预演，未真正中止；--go 时这里会直接退出。")

    # 🔴 2026-11-03 用户定：周期制货源（每月1号充 / 31天充一次）必须在标题和 SKU 上标清楚。
    #    SKU 名写不下 → 额外加一格「说明·…」专写周期。此步必须在 auto_copy 之前，
    #    这样标题/描述能一并带上周期，且档位摘要不会重复写一遍。
    period = detect_period(spec, item)
    spec["_period"] = period
    if period:
        _okn, _bad = apply_period_to_plan(spec, plan, period)
        spec["_period_applies"] = list(_bad or [])
        if spec.get("period_in_sku") is False:
            spec["_period_where"] = "按配置不写 SKU 名（只进标题/描述）"
        elif _bad:
            _note = add_period_note_sku(spec, plan, period, applies=_bad)
            spec["_period_note"] = _note["val"] if _note else ""
            spec["_period_where"] = ("SKU 名放不下 → 已加周期说明档" if _note
                                     else "SKU 名放不下 → 只写标题/描述")
            print("  ⚠️ 这些档的 SKU 名放不下周期：%s" % "、".join(_bad))
        elif _okn:
            spec["_period_where"] = "已写进 SKU 名"
            print("  SKU 名已带周期：%d 档（如 %s）" % (_okn, plan_disp(plan[0])))
        else:
            spec["_period_where"] = "无可用档位"
        spec["_period_in_sku"] = bool(_okn and not _bad)
        print("  最终 SKU：%s" % " / ".join(plan_disp(p) for p in plan))

    # 🔴 2026-11-13 用户定：货源限制要求（一号一次/限购/仅新用户…）逐档写进档位名；
    #    放不下 → 「限购说明」格兜底；「限价」永不写入买家文案。此步同样必须在
    #    auto_copy 之前，让标题/描述/档位摘要统一用新档名（避免 SKU 重排后失配）。
    spec["_limit_notes"] = apply_limit_to_plan(spec, plan, acct)
    if spec["_limit_notes"]:
        print("  最终 SKU：%s" % " / ".join(plan_disp(p) for p in plan))

    if spec.get("detail_text") is not False:
        # 文案：spec 没给的 title/desc，从同一份详情自动生成
        auto_copy(spec, plan, acct)
    # 限制说明行并入描述（auto_copy 之后：无论 desc 是 spec 手写还是自动生成；
    # detail_text=false 时 spec.desc 仍可能手写存在，同样注入）
    inject_limit_notes(spec, spec.get("_limit_notes") or [])

    print("\n-- 货源余额 --")
    for a in dict.fromkeys([p.get("acct") or acct for p in plan] or [acct]):
        print("  %-14s = %s" % (D.ACCT_PLATFORM.get(a), D.balance(a)))

    bad_bounds = check_bounds(plan, acct)
    if bad_bounds and mode == "--go":
        print("\n❌ 起购区间（最低起充）校验未通过，已中止 —— 未做任何改动。")
        print("   请改 spec 里对应档的 `mult`（份数）或换用起充更低的货源 pno 后重跑。")
        return

    bad_bal = check_balance(plan, acct)
    if bad_bal and mode == "--go":
        print("\n❌ 货源余额不足，已中止 —— 未做任何改动。")
        print("   余额不足时上架＝买家付款后发不出货（比不卖更严重）。")
        print("   请先给对应平台充值，再重跑同一条命令（幂等，会接着做）。")
        return

    if spec.get("title") or spec.get("desc") is not None:
        print("\n-- 文案（⑪）--")
        print("  新标题 : %s" % (spec.get("title") or "(不改)"))
        if spec.get("desc") is not None:
            print("  新描述 : %d 字" % len(spec.get("desc") or ""))
        print("  规则   : 只改 title/desc，其余原样回传（SKU 不会重建）")

    print("\n-- 自动改价（⑫）--")
    if spec.get("autoprice") is False:
        print("  spec.autoprice=false → 本次不开自动改价")
    else:
        _lo = float(spec.get("autoprice_min", AUTO_MIN))
        _hi = float(spec.get("autoprice_max", AUTO_MAX))
        _sk = spec.get("autoprice_skip") or AUTO_SKIP
        _mid = (_lo + _hi) / 200.0
        print("  利润率 %.1f%%~%.1f%%｜跳过关键字=%s｜偏差保护 >%.0f%%"
              % (_lo, _hi, "/".join(_sk), AUTO_MAXDEV * 100))
        for p in plan:
            disp = plan_disp(p)
            if any(s in disp for s in _sk):
                print("    %-22s 不参与（引流/例外档）" % disp[:22])
            else:
                _inc = round(float(p["cost"]) * (_mid / (1 - _mid)), 4)
                print("    %-22s 开启 → 期望利润 %.4f（目标价 %.2f）" % (disp[:22], _inc, float(p["cost"]) + _inc))

    if mode == "--dry":
        try:
            ref = preflight_main_image(spec, plan)
            if ref:
                print("  [dry] 主图参考图预检通过：%s" % ref.get("evidence"))
        except Exception as e:
            print("  [dry] 主图参考图预检失败：%s" % e)
        try:
            phase_images(gid, spec, plan, dry=True)
        except Exception as e:
            print("\n-- 详情图（⑬）--\n  [dry] 预演失败（不影响正式跑）：%s" % e)
        print("\n[dry] 未做任何改动。加 --go 执行。")
        return

    # 🔴 replica 的参考图预检必须早于任何线上写操作；keep/skip 完全不触碰参考图。
    if str(spec.get("main_image") or "keep").strip().lower() == "replica":
        try:
            _ref = preflight_main_image(spec, plan)
            print("\n-- 主图参考图预检（写入前）--")
            print("  ✅ %s" % _ref.get("evidence"))
            print("  参考图：%s" % str(_ref.get("ref_url"))[:160])
        except Exception as e:
            print("\n❌ 主图参考图预检失败，已中止 —— 未做任何改动。%s" % e)
            raise SystemExit(2)

    snap = snapshot(gid, item, "before")
    print("\n跑前快照 → %s" % os.path.relpath(snap, os.path.dirname(HERE)))

    if kind in ("single", "single_recharge"):
        price = spec.get("price") or round(float(spec.get("cost") or D.cost(spec["pno"], acct)) / (1 - profit), 2)
        it2 = (item); it2["reservePrice"] = round(float(price), 2)
        A.edit_item(it2)
        print("  [build-单品] 售价 → %s" % it2["reservePrice"])
        time.sleep(1.0)
        phase_alds_single(gid, spec, kind)
    else:
        item = phase_build(gid, spec, plan, item, force)
        if item is None:
            print("❌ build 阶段失败，已中止（未继续写配置）")
            return
        # 回读真实 skuId 映射
        real = {sku_key(s): str(s.get("skuId") or s.get("id"))
                for s in (item.get("itemSkuList") or [])}
        for p in plan:
            p["sid"] = real.get(p["val"])
        miss = [plan_disp(p) for p in plan if not p.get("sid")]
        if miss:
            print("❌ 回读缺失档位：%s" % miss); return
        phase_alds(gid, spec, plan, kind)

    # replica 主图必须在所有后续线上写入（直充标识、文案、详情图、自动改价）前完成。
    # 主图失败直接抛出并停止；keep/skip 是无副作用路径，维持原行为。
    phase_main_image(gid, spec)
    phase_910(gid, spec, kind)
    phase_online(gid)
    phase_copy(gid, spec)
    try:
        phase_images(gid, spec, plan)
    except Exception as e:
        print("  ⚠️ [⑬] 详情图处理失败，跳过（不影响已完成的 SKU/货源/文案）：%s" % e)
    print("\n-- 自动改价（⑫）--")
    _pm = phase_autoprice(gid, spec)
    # 🔴 ⑫ 后对齐描述价与线上实付价，根除 ⑦ 对照价不符（图文价格一致）
    _align_desc_price(gid, spec, plan, _pm)

    print("\n-- 自检 --")
    bad = phase_verify(gid)
    print("\n=== deploy 完成 | 自检真问题=%s %s ===" % (bad, "✅" if not bad else "❌ 需处理"))

    # 🔴 一条龙完成清单（2026-11-12 建）：11 项逐项打勾，杜绝「自检真问题=[]」假绿。
    # 旧自检不知道 spec.kind、不查描述、不查主图，三类坑都漏报过。
    try:
        import onepipe_guard as _G
        _rows, _missing = _G.postcheck(gid, spec, kind)
        if _missing:
            print("\n  ⚠️ 一条龙尚有 %d 项未完成：%s" % (len(_missing), "、".join(_missing)))
            print("     补主图链路：download_main_refs.py → gen_main_prompts.py → kuaipao_gen.py → upload_main_images.py --go")
    except Exception as _ge:
        print("  ⚠️ [完成清单] 模块异常，已跳过：%s" % str(_ge)[:120])

    if bad:
        print("  ⚠️ 若因 SKU 重建导致货源丢失，可用跑前快照回滚：")
        print("     python restore_from_snapshot.py %s %s --go" % (os.path.relpath(snap, HERE), gid))

    # 🔴 2026-11-13：上品完成后顺带全量体检「在线商品中货源已暂停销售」的 SKU，库存置 0，
    # 避免买家付款后货源发不出货。token 失效时扫描会安全中止（不误动、不误报）。
    # （dry 模式已在上方 2260 行 return，此处仅在 --go 执行，天然不误置 0）
    try:
        import scan_suspended_skus as _SS
        print("\n-- 暂停销售 SKU 巡检（置0）--")
        _SS.scan(auto=True)
    except Exception as _se:
        print("  ⚠️ [暂停销售巡检] 异常已跳过：%s" % str(_se)[:120])

    # 快照 after
    json.dump(A.get_item(gid), open(os.path.join(HERE, "snapshots", "%s_%s_after_item.json" % (gid, TS)),
                                    "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
