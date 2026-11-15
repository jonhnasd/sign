# -*- coding: utf-8 -*-
"""复刻式生图（固定实现）—— 闲鱼主图的唯一默认生图方案。

依据：Obsidian [[闲鱼主图范式库]] §七·八（2026-11-13 用户拍板定为默认方案）
      2026-11-14 用户要求「固定下来」，故落地为代码入口，不再允许建品链路
      静默退回「通用会员卡片 + 模型画文字」的纯文生图模板。

核心约束：
  1. 必须有参考图，走图生图（kuaipao_gen.py --ref），不是纯文生图。
  2. 参考图优先级：① 调用方/用户当前任务指定 → ② 固定素材库中该 pno 的货源商品图
     → ③ 取不到则抛 ReplicaRefMissing，停止生图，不静默回退。
  3. Prompt 按七段骨架生成；删除清单只写类别、不引禁词原文（否则被 prompt_guard 拦截）。
  4. 档位必须来自目标商品自身 SKU（线上回读），不照抄参考商品的旧档位。
  5. 出图后须按「文字白名单」逐字核验；本模块负责打印白名单，核验由人/视觉完成。

生成记录（manifest，2026-11-14 加）：
  每次真正上传主图后写 `_main_image_manifest.json`，记录 mode=replica、参考图 pno/来源/URL、
  自身 SKU 档位、买家字段、文字白名单、prompt/图片 sha256、线上主图 URL。
  `onepipe_guard.py` 的「⑨b 主图方案合规」读这份记录验收 —— 没有记录、非复刻式、
  缺参考图、未逐字核验、线上主图与记录不一致，一律不算完成。
  ⚠️ `whitelist_verified` 默认 False，必须人工/视觉逐字核验后显式标注，不许自动写 True。

用法（自检，不调 API、不写线上）：
  python replica_main_image.py --self-test --pno 1425 --source 志远 --sku 3个月,1个月
核验后标注（guard 变绿的唯一途径）：
  python replica_main_image.py --mark-verified --gid 1097971051544 --note "白名单五项逐字全中"
查看记录：
  python replica_main_image.py --show --gid 1097971051544
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

# 🔴 2026-11-15：素材目录走 paths.py（换机器设 DSH_VAULT 即可）
try:
    from paths import CFG as _CFG
except Exception:
    _CFG = None
ASSETS_DIR = Path((_CFG.assets_dir if _CFG else None) or
                  r"C:\Users\Administrator\Desktop\obisidian\obisidian\货源素材")
LIST_JSON = ASSETS_DIR / "货源商品清单.json"
DETAIL_JSON = ASSETS_DIR / "货源素材_详情.json"

ACCT_SOURCE = {95425: "志远", 99569: "思券", 96810: "商战"}

# ---------------------------------------------------------------- 买家填写字段解析
# 🔴 2026-11-14（优酷 165 事故）：popup_fields[0].title 常是**通用参数名**（充值账号/充值链接/
# 验证码），它只是阿奇索的字段名，不携带「买家该填什么」的信息。直接印到主图上会让买家填错
# （优酷账号 = 手机号，填会员昵称就充不进去、且不售后）。所以必须先回到货源原文解析出具体标识。
# 词典未命中 → 回落原字段名，不猜。
# 顺序即优先级。手机号排第一：货源常写「XX账号绑定手机号」，最终要填的仍是手机号。
# 条目只取「2261 条货源详情里真实出现过的说法」（2026-11-14 全量统计后确定），不凭印象添加。
BUYER_FIELD_RULES = [
    (r"手机号码|手机号|绑定手机|手机", "手机号"),
    (r"微博昵称", "微博昵称"),
    (r"微信号", "微信号"),
    (r"QQ\s*(?:号|号码|账号|帐号)", "QQ号"),
    (r"抖音\s*号", "抖音号"),
    (r"快手\s*(?:ID|id|号)", "快手号"),
    (r"剪映\s*小组\s*ID", "剪映小组ID"),
    (r"剪映.{0,3}(?:账号|帐号|号)", "剪映号"),
    (r"哔哩哔哩|B\s*站|bilibili", "B站账号"),
    (r"小红书\s*号", "小红书号"),
    (r"邮箱", "邮箱"),
    (r"游戏\s*角色\s*ID|角色\s*ID|Player\s*ID", "游戏角色ID"),
    (r"UID|用户\s*ID|账号\s*ID", "账号ID"),
    (r"链接|网址|URL|url", "链接"),
]

# 平台账号（2026-11-14 用户指出「还有让填写平台账号的」后新增）：
# 货源直接写「华为账号」「小米账号」「比心ID」「晋江客户号」「剪映小组ID」这类**平台专属账号**，
# 它们不是手机号、也不带通用后缀，上面的词典一条都命中不了 → 会回落成「充值账号」而印错。
# 这里不维护平台白名单（会随时间腐化），而是从原文里把平台名剥出来：平台名本来就在货源原文里。
_PLAT_TAIL_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{1,9})\s*(账号|帐号|客户号|ID|id)")
# 剥平台名时要剪掉的前缀修饰词（长的在前，避免「已」先吃掉「已注册」）
_PLAT_MODS = ("需要充值", "已注册", "可直接", "需要", "填写", "充值", "下单", "输入", "提供",
              "仅限", "限定", "支持", "推荐", "个人", "绑定", "已有", "自己的", "自己",
              "官方", "平台", "会员", "独享", "共享", "专属", "升级", "当前", "全新",
              "该", "本", "您", "你", "我", "请", "务必", "直接", "的", "需", "已", "新")
# 剥完仍落在这些词上的，说明不是一个能写的平台名，宁可回落让人工核
_PLAT_STOP = {"充值", "账号", "帐号", "会员", "平台", "绑定", "个人", "官方", "独享", "共享",
              "游戏", "权益", "服务", "订单", "买家", "卖家", "本店", "商家", "用户", "号码"}
# 剥出的名字里含这些词的，是指令/说明而不是平台名
_PLAT_JUNK = ("参照", "调整", "修改", "查看", "点击", "注意", "确认", "输入", "填写", "说明",
              "示例", "图示", "提示", "以下", "上方", "下方", "如上", "如下", "详情", "规则")

# 通用参数名（不含具体标识），命中说明「不能直接当文案」
GENERIC_FIELD_RE = re.compile(r"^(?:充值)?(?:账号|帐号|链接|验证码|号码|ID)$")
# 货源原文里「XX：yyy」形式的填写说明行（只取冒号**后面**的值，避免整行误判）
_LABEL_VALUE_RE = re.compile(r"(?:充值|填写|下单|输入|提供)?(?:账号|帐号|链接|号码)\s*[:：]\s*(.+)")
_TAG_RE = re.compile(r"<[^>]+>")


def _plain_lines(*texts):
    """把 HTML 片段拆成短行：<br> 转换行、去标签、去装饰符号。

    这一步是必须的：intro_html 里整段用 <br> 连接，不拆开就会把「支持设备：手机/平板」
    当成填写说明命中「手机」，答案对但依据错（2026-11-14 165 复现）。
    """
    out = []
    for t in texts:
        s = str(t or "")
        s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", s)
        s = _TAG_RE.sub(" ", s)
        for ln in s.splitlines():
            ln = ln.strip().strip("✅📋⚠️📌•·-— ")
            if ln:
                out.append(ln)
    return out


def _ids_in(text):
    """按优先级取出文里所有能识别的填写标识（去重保序）。"""
    out = []
    for pat, disp in BUYER_FIELD_RULES:
        if re.search(pat, text) and disp not in out:
            out.append(disp)
    return out


def _platform_account(text):
    """从「…XX账号 / XX ID / XX客户号」里剥出平台专属账号，如「华为账号」「比心ID」「晋江客户号」。

    平台名来自货源原文本身，不靠白名单。剥不干净就返回 None（回落让人工核，不硬猜）。
    """
    for m in _PLAT_TAIL_RE.finditer(text):
        # URL / 英文串里的 "rightID""APPID" 不是平台账号
        pre = text[m.start() - 1] if m.start() > 0 else ""
        if pre and (pre.isascii() and (pre.isalnum() or pre in "/.?:=-_")):
            continue
        head, tail = m.group(1), m.group(2)
        if any(x in head for x in ("手机", "号码", "链接", "邮箱", "密码", "验证码")):
            continue            # 已经由上面的词典覆盖，不是平台账号
        head = re.split(r"[的、,，/／和或\s]+", head)[-1]   # 「已有醒图VIP的醒图」→「醒图」
        changed = True
        while changed:
            changed = False
            for mod in _PLAT_MODS:
                if head.startswith(mod) and len(head) >= len(mod):
                    head, changed = head[len(mod):], True
                    break
        head = re.sub(r"(?:绑定|关联|的)$", "", head)     # 「剪映绑定账号」→「剪映」
        if not (2 <= len(head) <= 8) or head in _PLAT_STOP:
            continue
        if any(x in head for x in _PLAT_JUNK):
            continue            # 「参照配图调整」「说明示例」这类是指令，不是平台名
        if head.isascii() and not (head.isupper() and 2 <= len(head) <= 4):
            continue            # 纯英文只收 YY / TT 这类全大写短名
        return head + ("ID" if tail.lower() == "id" else tail)
    return None


def resolve_buyer_field(popup_fields, *texts):
    """把货源字段名解析成**买家真正要填的标识**。

    返回 dict：field / evidence / fallback / kind。
    优先级：货源原文「账号：xxx」的**值部分** > popup_fields 的 tip/placeholder。
    （2026-11-14 教训：popup 是阿奇索字段名「充值账号」，它本身不含任何信息，
      原文才写清「填写优酷绑定手机号即可」，所以原文必须排在字段名之前。）

    三类结果：
      kind=标识     手机号 / QQ号 / 微博昵称…（含「A或B」，如 QQ号/绑定手机号）
      kind=平台账号 华为账号 / 小米账号 / 比心ID / 晋江客户号 / 剪映小组ID / 游戏角色ID
      kind=回落     词典与平台名都未命中 → 用原字段名，调用方必须打人工核对警告
    """
    popup = []
    if isinstance(popup_fields, str):
        try:
            popup_fields = ast.literal_eval(popup_fields)
        except (ValueError, SyntaxError):
            popup_fields = []
    for f in (popup_fields or []):
        if isinstance(f, dict):
            for k in ("tip", "placeholder", "title", "name"):
                v = str(f.get(k) or "").strip()
                if v and v not in popup:
                    popup.append(v)

    raw = popup[0] if popup else ""
    # 字段名分两类：具体名（手机号/APPID/剪映ID）> 通用名（充值账号/请输入账号）。
    # 密码、验证码这类不是买家「填给商家」的标识，直接排除。
    specific, generic = [], []
    for v in popup:
        if any(x in v for x in ("密码", "验证码")):
            continue
        bare = re.sub(r"^(?:请输入|请填写|请输入您的|输入)", "", v).strip()
        (generic if (GENERIC_FIELD_RE.match(bare) or bare in ("账号", "帐号")) else specific).append(v)
    bare_of = lambda v: re.sub(r"^(?:请输入您的|请输入|请填写|请提供|输入|填写)", "", v).strip()
    if len({("或".join(_ids_in(bare_of(v))) or bare_of(v)) for v in specific}) >= 2:
        return {"field": raw or "充值账号",
                "evidence": "有多个必填字段（%s），需人工确认买家该填哪个" % " / ".join(specific),
                "fallback": True, "kind": "回落"}

    # 原文说明行：只取冒号后的值，避免「支持设备：手机/平板」这类误命中
    values = []
    for ln in _plain_lines(*texts):
        m = _LABEL_VALUE_RE.search(ln)
        if m:
            values.append(m.group(1).strip())

    for cand in values + specific + generic:
        ids = _ids_in(cand)
        if ids:
            return {"field": "或".join(ids[:2]),
                    "evidence": "原文「%s」→ %s" % (cand[:40], "、".join(ids[:2])),
                    "fallback": False, "kind": "标识"}
        plat = _platform_account(cand)
        if plat:
            return {"field": plat,
                    "evidence": "原文「%s」→ 平台账号「%s」" % (cand[:40], plat),
                    "fallback": False, "kind": "平台账号"}

    # 都没命中：先看字段名本身是不是已经够具体（「11位手机号」「请输入您的手机号码」）
    bare = re.sub(r"^(?:请输入您的|请输入|请填写|请提供|输入|填写)", "", raw).strip()
    ids = _ids_in(bare)
    if ids:
        return {"field": "或".join(ids[:2]), "evidence": "字段名「%s」即具体标识" % raw,
                "fallback": False, "kind": "标识"}
    plat = _platform_account(bare)
    if plat:
        return {"field": plat, "evidence": "字段名「%s」→ 平台账号「%s」" % (raw, plat),
                "fallback": False, "kind": "平台账号"}

    # 仍不命中：回落原字段名（调用方必须打人工核对警告，不猜）
    return {"field": bare or raw or "充值账号",
            "evidence": "未命中具体标识，回落字段名「%s」" % (bare or raw or "充值账号"),
            "fallback": True, "kind": "回落"}



class ReplicaRefMissing(RuntimeError):
    """复刻式生图缺少参考图：按规范必须停止，不得回退纯文生图。"""


def source_of(acct):
    try:
        return ACCT_SOURCE.get(int(acct), "")
    except (TypeError, ValueError):
        return ""


def _items(path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("items") or []
    except (OSError, ValueError):
        return []


def lookup_supplier(pno, source=""):
    """只读固定素材库，取货源商品图与买家填写字段名。不抓线上、不取进价库存。

    ``source + pno`` 是货源身份的联合键；调用方传入 source 时，缺少来源字段
    或来源不一致的记录都不能算命中，避免同编号跨货源串图。
    """
    pno = str(pno)
    source = str(source or "").strip()
    hit = next((x for x in _items(LIST_JSON)
                if str(x.get("pno")) == pno
                and (not source or str(x.get("source") or "").strip() == source)), None)
    det = next((x for x in _items(DETAIL_JSON)
                if str(x.get("pno")) == pno
                and (not source or str(x.get("source") or "").strip() == source)), None)
    identity = hit or det or {}

    img = ""
    for rec in (hit, det):
        if rec and rec.get("img"):
            img = str(rec["img"])
            break

    # popup_fields 在详情库里可能是 Python repr 字符串，也可能是 list
    pf = (det or {}).get("popup_fields")
    if isinstance(pf, str):
        try:
            pf = ast.literal_eval(pf)
        except (ValueError, SyntaxError):
            pf = []
    account_label = ""
    if isinstance(pf, list):
        for f in pf:
            if isinstance(f, dict):
                account_label = f.get("title") or f.get("name") or f.get("tip") or ""
                if account_label:
                    break

    # 解析「买家真正要填什么」：字段名 + 货源原文说明行一起判断
    _bf = resolve_buyer_field(
        pf,
        (det or {}).get("intro_html", ""),
        (det or {}).get("notice_html", ""),
        (hit or {}).get("short_desc", ""),
    )

    return {
        "found": bool(hit or det),
        "name": identity.get("name", ""),
        "form": identity.get("form", ""),
        "img": img,
        "source": source,
        "pno": pno,
        "identity_source": str(identity.get("source") or ""),
        "identity_pno": str(identity.get("pno") or ""),
        "identity_verified": bool(identity and str(identity.get("pno")) == pno
                                  and (not source or str(identity.get("source") or "").strip() == source)),
        "account_label": str(account_label),
        # 🔴 买家可见文案必须用 buyer_field（具体标识/平台账号），account_label 只是字段名
        "buyer_field": _bf["field"],
        "buyer_evidence": _bf["evidence"],
        "buyer_fallback": _bf["fallback"],
        "buyer_kind": _bf["kind"],
    }


def _valid_image_bytes(raw):
    """只接受能识别的常见图片头，避免 HTML 错误页被当成参考图。"""
    return (len(raw) >= 1024 and
            (raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:2] == b"\xff\xd8"
             or raw[:4] == b"RIFF" or raw[:4].lower() == b"<svg"))


def download_ref(src, dest):
    """参考图落地为本地文件（本地路径直拷 / URL 直连下载，绕过系统代理）。"""
    if src and os.path.exists(str(src)):
        raw = Path(str(src)).read_bytes()
        if not _valid_image_bytes(raw):
            raise ReplicaRefMissing("本地参考图不是有效图片（%d 字节）" % len(raw))
        Path(dest).write_bytes(raw)
        return dest
    if not src or not str(src).startswith(("http://", "https://")):
        raise ReplicaRefMissing("未取得可用的参考图 URL/本地路径")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(str(src), headers={"User-Agent": "Mozilla/5.0"})
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
    with opener.open(req, timeout=45) as r:
        raw = r.read()
    if not _valid_image_bytes(raw):
        raise ReplicaRefMissing("参考图下载内容不是有效图片（%d 字节）" % len(raw))
    Path(dest).write_bytes(raw)
    return dest


def resolve_reference(pno, acct, cli_ref="", *, validate=True):
    """解析复刻参考图，并返回可写入 manifest 的完整归属证据。

    优先使用调用方显式参考图；否则必须按当前 ``acct -> source`` 与 ``pno``
    精确命中固定素材库。供应商图缺失、来源不明、pno 不一致或图片不可读取，
    一律抛 ``ReplicaRefMissing``，禁止回退到无参考图生图。
    """
    pno = str(pno or "").strip()
    if not pno:
        raise ReplicaRefMissing("目标商品缺少 pno，无法确定参考图归属")
    source = source_of(acct)
    if cli_ref:
        src = str(cli_ref).strip()
        result = {
            "ref_url": src,
            "ref_source": "cli",
            "ref_acct": str(acct),
            "ref_source_name": source,
            "ref_pno": pno,
            "match": "explicit",
            "evidence": "调用方显式指定参考图；已按文件/下载内容预检",
        }
    else:
        if not source:
            raise ReplicaRefMissing("acct=%s 无法映射货源 source，禁止猜测参考图归属" % acct)
        info = lookup_supplier(pno, source)
        if (not info.get("found") or not info.get("identity_verified")
                or str(info.get("identity_pno") or "") != pno
                or str(info.get("identity_source") or "").strip() != source):
            raise ReplicaRefMissing("固定素材库未精确命中 source=%s,pno=%s" % (source, pno))
        src = str(info.get("img") or "").strip()
        if not src:
            raise ReplicaRefMissing("source=%s,pno=%s 已命中但缺少商品图" % (source, pno))
        result = {
            "ref_url": src,
            "ref_source": "supplier",
            "ref_acct": str(acct),
            "ref_source_name": source,
            "ref_pno": pno,
            "match": "source+pno",
            "evidence": "固定素材库精确命中 source=%s,pno=%s" % (source, pno),
        }
    if validate:
        fd, tmp = tempfile.mkstemp(prefix="replica_ref_", suffix=".img")
        os.close(fd)
        try:
            download_ref(result["ref_url"], tmp)
        except Exception as e:
            if isinstance(e, ReplicaRefMissing):
                raise
            raise ReplicaRefMissing("参考图预检失败：%s" % e)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    return result


def clean_product_name(title):
    """从商品标题剥出产品名（去【】前缀、去档位摘要、去下单提示）。"""
    t = re.sub(r"^【[^】]*】", "", str(title)).strip()
    t = re.split(r"\s+\S*\d+(?:天|个月|年)\S*[/／]\S*", t)[0]
    t = re.split(r"\s+下单", t)[0]
    # 货源名常是单档（如「新浪微博会员1个月」），贴尾的单档必须剥掉，
    # 否则主标题会写死一个档位，与多 SKU 商品冲突。
    t = re.sub(r"\d+(?:天|个月|年)$", "", t.strip()).strip()
    return t.strip() or str(title)[:20]


SKU_DISPLAY_MODES = ("highest", "all", "highest_month")


class SkuDisplayError(RuntimeError):
    """目标 SKU 无法按已确认的时长/面额口径确定展示档位。"""


def _sku_labels(sku):
    labels = []
    for prop in (sku or {}).get("propertyList") or []:
        value = prop.get("valueText") or prop.get("value") or prop.get("text")
        if value is not None and str(value).strip() and str(value).strip() not in labels:
            labels.append(str(value).strip())
    return labels


def _tier_measure(label):
    """返回可比较的 ``(kind, unit, score)``，不跨单位换算或猜档位。"""
    text = str(label or "").strip().replace(" ", "")
    if not text:
        return None
    duration_words = (
        (r"终身|永久", ("duration", "permanent", 10 ** 12)),
        (r"半年", ("duration", "half_year", 1)),
        (r"双月卡", ("duration", "month", 2)),
        (r"半月卡", ("duration", "month", 0.5)),
        (r"季度|季卡", ("duration", "quarter", 1)),
        (r"年卡", ("duration", "year", 1)),
        (r"月卡", ("duration", "month", 1)),
        (r"周卡", ("duration", "week", 1)),
        (r"天卡", ("duration", "day", 1)),
    )
    word_matches = []
    for pattern, result in duration_words:
        if re.search(pattern, text):
            word_matches.append(result)
            break
    duration_units = (
        (r"(\d+(?:\.\d+)?)年", "year"),
        (r"(\d+(?:\.\d+)?)个月", "month"),
        (r"(\d+(?:\.\d+)?)月", "month"),
        (r"(\d+(?:\.\d+)?)季度", "quarter"),
        (r"(\d+(?:\.\d+)?)季", "quarter"),
        (r"(\d+(?:\.\d+)?)周", "week"),
        (r"(\d+(?:\.\d+)?)(?:天|日)", "day"),
        (r"(\d+(?:\.\d+)?)小时", "hour"),
    )
    numeric_durations = []
    for pattern, unit in duration_units:
        for match in re.finditer(pattern, text):
            numeric_durations.append(("duration", unit, float(match.group(1))))
    if word_matches and numeric_durations:
        # 「15个月卡」这类标签里，周期数字比后缀的通用卡名更具体；
        # 仅当卡名单位与数字单位一致时采用数字，其他冲突仍失败关闭。
        numeric_units = {measure[1] for measure in numeric_durations}
        word_units = {measure[1] for measure in word_matches}
        if len(set(numeric_durations)) == 1 and word_units.issubset(numeric_units):
            return numeric_durations[0]
        return None
    if word_matches:
        return word_matches[0] if len(set(word_matches)) == 1 else None
    if numeric_durations:
        return numeric_durations[0] if len(set(numeric_durations)) == 1 else None
    amount_units = (
        (r"(\d+(?:\.\d+)?)元", "yuan"),
        (r"(\d+(?:\.\d+)?)(积分|币|点|钻|豆)", None),
        (r"(\d+(?:\.\d+)?)次", "times"),
    )
    measures = []
    for pattern, unit in amount_units:
        for match in re.finditer(pattern, text):
            measures.append((unit or match.group(2), float(match.group(1))))
    if len(measures) == 1:
        unit, score = measures[0]
        return "amount", unit, score
    # 同一标签多种单位或多个面额时，无法定义唯一可比较值，拒绝猜测。
    return None


def select_sku_display(item_skus, mode="highest"):
    """按用户确认的「时长/面额最大」选择主图展示档位。

    返回 labels、实际展示 SKU 和证据。highest 遇到无法唯一比较的结果直接失败；
    all 只在调用方显式选择时使用，并携带提醒证据，防止默认悄悄铺全档。
    """
    mode = str(mode or "highest").strip().lower()
    if mode not in SKU_DISPLAY_MODES:
        raise SkuDisplayError("主图 SKU 展示模式必须是 highest 或 all，实际为 %r" % mode)
    rows = []
    for index, sku in enumerate(item_skus or []):
        labels = _sku_labels(sku)
        if labels:
            rows.append({"index": index, "sku_id": sku.get("skuId"), "labels": labels})
    if not rows:
        raise SkuDisplayError("目标商品没有可用于主图的自身 SKU 档位")
    if mode == "all":
        labels = []
        for row in rows:
            for label in row["labels"]:
                if label not in labels:
                    labels.append(label)
        return {
            "mode": "all",
            "labels": labels,
            "displayed_skus": rows,
            "selection_evidence": "显式选择全档位展示；未使用参考图旧档位",
            "reminder": "⚠️ 已选择主图展示目标商品全部 SKU 档位，请确认画面空间与每档文字均可读。",
        }

    if mode == "highest_month":
        month_rows = []
        for row in rows:
            month_scores = [m[2] for label in row["labels"]
                            if (m := _tier_measure(label))
                            and m[0] == "duration" and m[1] == "month"]
            if month_scores:
                month_rows.append((max(month_scores), row))
        if not month_rows:
            raise SkuDisplayError("目标商品没有可识别的月档 SKU")
        best_score = max(score for score, _row in month_rows)
        best_rows = [row for score, row in month_rows if score == best_score]
        if len(best_rows) != 1:
            raise SkuDisplayError("月档最高值对应多个 SKU，拒绝擅自合并")
        best = best_rows[0]
        return {
            "mode": "highest_month",
            "labels": best["labels"],
            "displayed_skus": [best],
            "selection_evidence": "按用户明确选择仅展示月档；从目标商品自身 SKU 中筛选月单位并选择最大值：%s" % "/".join(best["labels"]),
            "reminder": "",
        }

    # 双维度商品里，会员等级/车型等维度可能重复出现在多条 SKU；
    # 只在同一个规格维度覆盖全部 SKU 且单位一致时比较，不能把整条 propertyList 摊平后混算。
    by_dim = {}
    for row in rows:
        sku = item_skus[row["index"]]
        seen = set()
        for prop in (sku or {}).get("propertyList") or []:
            dim = str(prop.get("propertyText") or "__default__").strip()
            label = str(prop.get("valueText") or prop.get("value") or prop.get("text") or "").strip()
            measure = _tier_measure(label)
            if not label:
                continue
            by_dim.setdefault(dim, {}).setdefault(row["index"], []).append((label, measure))
    candidates = []
    incompatible = []
    for dim, sku_values in by_dim.items():
        if len(sku_values) != len(rows):
            continue
        if any(len(sku_values[row["index"]]) != 1 for row in rows):
            continue
        entries = [sku_values[row["index"]][0] for row in rows]
        measures = [measure for _label, measure in entries]
        if any(measure is None for measure in measures):
            continue
        kinds = {measure[0] for measure in measures}
        units = {measure[1] for measure in measures}
        if len(kinds) != 1 or len(units) != 1:
            incompatible.append((dim, sorted("%s:%s" % (m[0], m[1]) for m in measures)))
            continue
        candidates.append((measures[0][0], measures[0][1], dim, [
            (row, label, measure[2])
            for row, (label, measure) in zip(rows, entries)
        ]))
    if not candidates:
        if incompatible:
            detail = "; ".join("%s=%s" % (dim, ",".join(units))
                                for dim, units in incompatible)
            raise SkuDisplayError("SKU 时长/面额单位混杂（%s），拒绝跨单位换算" % detail)
        raise SkuDisplayError("SKU 档位没有覆盖全部自身 SKU 的可比较时长/面额维度，拒绝按顺序猜测")
    # 用户选择时长/面额最大；时长维度优先于面额，但只允许同单位内比较。
    kind, unit, dim, values = next((x for x in candidates if x[0] == "duration"), candidates[0])
    best_score = max(score for _row, _label, score in values)
    best_entries = [(row, label) for row, label, score in values if score == best_score]
    tied_labels = list(dict.fromkeys(label for _row, label in best_entries))
    if len(best_entries) > 1:
        raise SkuDisplayError("最高%s档位对应多个目标 SKU 组合（%s），拒绝漏掉其他维度或擅自合并" % (
            kind, "/".join(tied_labels)))
    best_rows = [row for row, _label in best_entries]
    best_labels = list(best_rows[0]["labels"])
    if not best_labels:
        raise SkuDisplayError("最高%s档位为空，拒绝静默猜测" % kind)
    return {
        "mode": "highest",
        "labels": best_labels,
        "displayed_skus": best_rows,
        "sku_dimension": dim,
        "selection_evidence": "按目标 SKU 自身「%s」维度的%s（单位=%s）最大值选择：%s" % (
            dim, kind, unit, "/".join(best_labels)),
        "reminder": "",
    }


def build_prompt(product_name, sku_labels, account_label="", brand_hint="", sku_display_mode="highest"):
    """七段骨架（范式库 §七·八）。全部文字走白名单，模型只做合规改字。"""
    sku_display_mode = str(sku_display_mode or "highest").strip().lower()
    if sku_display_mode not in SKU_DISPLAY_MODES:
        raise SkuDisplayError("未知主图 SKU 展示模式：%s" % sku_display_mode)
    sku_labels = [str(x).strip() for x in (sku_labels or []) if str(x).strip()]
    account_label = str(account_label or "").strip()
    sku_text = " / ".join(sku_labels) if sku_labels else "保持参考图原有单档"
    if sku_display_mode == "highest":
        sku_display_line = "- 原图单档大字区 → 改为档位胶囊：%s。仅展示按目标商品自身时长/面额判定的最高档位，不展示其他档位" % sku_text
    elif sku_display_mode == "highest_month":
        sku_display_line = "- 原图单档大字区 → 改为档位胶囊：%s。仅展示用户明确选择的月档最高值，不展示天档，不进行跨单位换算" % sku_text
    else:
        sku_display_line = "- 原图单档大字区 → 改为档位胶囊：%s。已显式选择展示目标商品全部 SKU 档位，不得漏档" % sku_text
    whitelist = [product_name] + (["下单填写%s" % account_label] if account_label else []) \
        + sku_labels + ["uu小铺"]
    if brand_hint:
        whitelist.append(brand_hint)
    wl_text = "、".join("「%s」" % w for w in whitelist)
    brand_line = ("- 「%s」原样保留，不改写、不新增" % brand_hint
                  if brand_hint else
                  "- 参考图中的品牌 Logo 图形原样保留；Logo 旁文字只保留白名单中的目标商品名，不保留参考图旧产品名")
    fill_line = ("- 原图中表达填写账号并直充的文字 → 「下单填写%s」；"
                 "**若原图中根本没有这类文字，则新增这一行**：优先放在原图的说明条／权益宣传行位置"
                 "（如底部那一条小字色块），原图没有说明条时才在底部信息区另起一行。"
                 "只新增这一行，此外不得新增任何其他文字。\n"
                 "- 新增的这一行**不得替换、挤占或清空产品名与主标题所在的位置**："
                 "原图底部若有产品名大字，必须原地保留（写法按上一节统一），"
                 "填写句放到它下方的小字或说明条里，字号明显小于产品名，"
                 "不得让填写句比产品名更醒目\n" % account_label
                 if account_label else
                 "- 原图中表达「下单填写账号」的整句文字连同其色块**一并删除**"
                 "（本商品不需要买家填写账号），不得改成其他填写要求，也不得另起一行新增填写要求\n")

    return (
        "基于上传的货源商品参考图，严格复刻原图，不重新设计；不改变整体构图、版式、配色、"
        "元素位置、视觉层级与留白比例。输出 1:1 正方形（1024x1024）闲鱼虚拟商品主图，高清电商海报质感。\n\n"
        "【总体要求】严格复刻参考图的整体设计与版式，只替换指定文字内容，不做重新构图。\n"
        "- 保持外框、背景基调、主卡片、品牌 Logo、中央图标、色块分区与底部信息区的位置、比例、描边和阴影不变\n"
        "- 保持粗黑中文字体风格、字号层级、对齐方式和视觉层级不变；品牌 Logo 与图标原样保留，不重绘、不变形、不遮挡\n\n"
        "【保留的文字】\n"
        "%s\n"
        "- 只有下方白名单里列出的文字允许出现在成品图上；原图自带但不在白名单里的中文、数字、英文、符号，"
        "无论原图是否存在，一律删除或按替换清单改写，**「原样保留」不适用于任何白名单之外的文字**\n"
        "- 参考图里每个图标旁都必须保留对应说明文字：只允许删掉其中的时效承诺词，不得整行消失，也不得留下无文字的空图标\n"
        "- 原图若出现以「充值+账号／链接」命名的**参数名**，或「填写手机号充值」这类与替换清单不一致的"
        "填写说明，一律按替换清单改写或删除：不得原样保留，不得新旧两句并存，不得同一含义出现两个版本\n\n"
        "【替换的文字】\n"
        "- 主标题 → 「%s」，字形位置与大小参考原图，**必须逐字一致，不得增删任何字符**"
        "（不得写成带「VIP」「官方」「正版」等前缀/后缀的变体）\n"
        "%s"
        "%s，字号与样式统一，不新增其他档位\n"
        "- 除 Logo 图形内部原有字样外，产品全名在画面中只出现一次，且必须与主标题逐字一致；"
        "原图里的简称、省略、少字版本一律删除，不得作为阴影字、底纹字或第二标题残留；"
        "其他品牌词与厂商名只有在白名单中列出时才可保留，否则一律删除\n"
        "- 原图中央或主卡上的单档周期大字（例如「月卡」「周卡」「天卡」「年卡」这类字样）"
        "必须替换成上一条的档位胶囊，该位置不得再保留原来的单档词；"
        "其他位置的时长后缀同样并入胶囊，不要写成主标题的一部分\n"
        "- 底部设备支持或权益说明行若存在，只保留其原有合规表述，不新增权益宣传\n\n"
        "【删除的内容】\n"
        "- 删除所有涉及充值后多久生效、发货速度、处理时长的时效或履约承诺类文字，只删文字，不改变对应色块和版式结构\n"
        "- 删除价格、折扣、二维码、联系方式、平台水印、卖家水印与来源标识\n"
        "- 删除原图自带的任何「官方／正品／授权／认证」类背书字样及其角标、斜标、绶带；"
        "**原图本来就有也必须删**，不因「原图自带」而保留，删除后按周围底色补全、不留空缺\n"
        "- 删除参考图中无法由当前商品信息确认的额外权益宣传语；不得自行新增卖点、认证、授权或信任背书\n\n"
        "【新增】\n"
        "- 在不遮挡原 Logo、中央图标与主标题的前提下，右下角或底部留白处加小号店铺角标「uu小铺」"
        "（半透明黑色圆角 + 白色小字）\n\n"
        "【硬性禁令】\n"
        "- 画面只能出现这些文字：%s\n"
        "- 不得出现任何其他中文、数字、英文或符号文字；不得改变构图、色块边界、图标位置、标题位置与档位位置\n"
        "- 每句文字必须是连续的一整串：字与字之间、句首句尾都不得出现竖线、斜线、分隔线、光标、括号、下划线或任何占位符\n"
        "- 中文必须逐字准确、清晰锐利，不漏字、不多字、不乱码、不生成假字；所有文字距离边缘留出安全边距\n"
        "- 保持原图的电商海报质感，高清、干净、无水印\n\n"
        "【自查】缩小到闲鱼缩略图尺寸后，主标题与全部档位胶囊仍清晰可读；"
        "逐字对照上面的文字白名单，一个不多、一个不少。"
    ) % (brand_line, product_name, fill_line, sku_display_line, wl_text)


def text_whitelist(product_name, sku_labels, account_label, brand_hint=""):
    fill = ["下单填写%s" % account_label] if str(account_label or "").strip() else []
    return ([product_name] + fill
            + [str(x) for x in (sku_labels or [])] + ["uu小铺"]
            + ([brand_hint] if brand_hint else []))


# ---------------------------------------------------------------- 图上禁词
# 复刻式会「继承」参考图上的既有文字，这是它唯一的口子：原图有的东西模型有理由留下。
# 下面四类**只允许在商品名/档位里出现，不允许作为独立文案出现**，核验时逐项对照。
IMAGE_FORBIDDEN = [
    ("参数名", r"充值(?:账号|帐号|链接)|填写账号|输入账号|账号\s*ID|卡密链接"),
    ("时效承诺", r"秒到|秒充|秒发|秒接|极速|立即到账|马上到账|分钟.{0,3}到账|小时.{0,3}到账"
                r"|当天到账|24\s*小时|实时到账"),
    ("背书", r"官方正品|官方授权|正版保证|官方认证|官方直充|全网最低|独家|假一赔|官方渠道"),
    ("价格", r"[¥￥]\s*\d|\d+\s*元"),
]

# 人读版本（打印核验清单用；正则只给代码用）
IMAGE_FORBIDDEN_HINT = [
    ("参数名", "充值账号 / 充值帐号 / 充值链接 · 填写账号 / 输入账号 / 账号ID / 卡密链接"),
    ("时效承诺", "秒到 / 秒充 / 秒发 / 秒接 / 极速 / 立即到账 / 马上到账 / N分钟到账 / N小时到账 / 当天到账 / 24小时 / 实时到账"),
    ("背书", "官方正品 / 官方授权 / 正版保证 / 官方认证 / 官方直充 / 全网最低 / 独家 / 假一赔 / 官方渠道"),
    ("价格", "¥数字 / 数字元"),
]


def forbidden_on_image(text, allow=""):
    """返回 text 里命中的图上禁词 [(类别, 词)]；allow 是允许豁免的整串（如商品名本身含「官方直充」）。

    用途：核验时把「这张图上不该出现的词」摆出来逐项对，而不是凭印象「看着挺干净」。
    """
    allow = str(allow or "")
    hits, seen = [], set()
    for cat, pat in IMAGE_FORBIDDEN:
        for m in re.finditer(pat, str(text or "")):
            w = m.group(0)
            if w in seen:
                continue
            # 商品名/档位本身含该词（如「官方直充」写在标题里）不算违规
            if allow and w in allow:
                continue
            seen.add(w)
            hits.append((cat, w))
    return hits


# ---------------------------------------------------------------- 生成记录 manifest
MANIFEST_PATH = Path(__file__).with_name("_main_image_manifest.json")

# 合法 mode：
#   replica       —— 本模块复刻式生成并上传（默认，唯一自动路径）
#   self_supplied —— 主图由用户自备/历史遗留，但**必须**留下逐字 OCR 全文并通过禁词闸
# 旧「通用会员卡片 + 模型画文字」纯文生图仍然不算数（不写记录 = 判红）。
VALID_MODE = "replica"
SELF_MODE = "self_supplied"
ALLOWED_MODES = (VALID_MODE, SELF_MODE)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_manifest(gid):
    """读某商品的生成记录；无记录返回 {}。guard 用这个做验收。"""
    return load_manifest().get(str(gid)) or {}


def write_manifest(gid, **fields):
    """写/更新某商品的主图生成记录。mode 只能由本模块写成 replica。"""
    data = load_manifest()
    key = str(gid)
    rec = dict(data.get(key) or {})
    rec.update({k: v for k, v in fields.items() if v is not None})
    rec["gid"] = key
    rec["updated"] = _now()
    if rec.get("mode") not in ALLOWED_MODES:
        rec["mode"] = VALID_MODE
    data[key] = rec
    MANIFEST_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return rec


def mark_verified(gid, note=""):
    """逐字核验通过后标注。没有记录 / 线上未上传的不许标注，避免假绿。"""
    rec = read_manifest(gid)
    if not rec:
        raise RuntimeError("商品 %s 没有主图生成记录，不能标注为已核验" % gid)
    if not rec.get("uploaded") or not rec.get("main_img_url"):
        raise RuntimeError("商品 %s 的主图未记录为已上传线上，不能标注为已核验" % gid)
    if rec.get("mode") != VALID_MODE:
        raise RuntimeError("商品 %s 的主图 mode=%s，不是复刻式" % (gid, rec.get("mode")))
    return write_manifest(gid, whitelist_verified=True,
                          verified_note=str(note or "").strip() or "逐字核验通过",
                          verified_at=_now())


def record_self_supplied(gid, ocr_text, main_img_url, note=""):
    """登记「主图由用户自备/历史遗留」并当场过禁词闸。

    为什么需要这条路：按阿奇索 ID 上 SKU 的流程**不生成主图**，图是用户自己传的。
    没有登记口，⑨b 要么永久判红（于是被塞进 MAIN_IMAGE_LEGACY 变成静默豁免），
    要么被随手 `--mark-verified` 盖章 —— 1425 那次假绿就是这么来的。
    这里要求交出**图上逐字 OCR 全文**：没交就等于没核，一律不通过。
    """
    txt = str(ocr_text or "").strip()
    if len(txt) < 4:
        return False, "必须提供图上逐字 OCR 全文（≥4 字），否则视为未核验"
    if not str(main_img_url or "").strip():
        return False, "必须提供线上主图 URL"
    bad = forbidden_on_image(txt)
    if bad:
        return False, "图上出现禁词：%s（先改图再登记）" % bad
    write_manifest(gid, mode=SELF_MODE, uploaded=True,
                   main_img_url=str(main_img_url).strip(),
                   ocr_text=txt,
                   whitelist_verified=True,
                   verified_note=str(note or "").strip() or "自备主图逐字核验通过",
                   verified_at=_now())
    return True, "已登记自备主图（%d 字，禁词闸通过）" % len(txt)


def whitelist_url(url):
    """去掉 CDN 签名 query，避免签名换签导致比对误判。"""
    return str(url or "").split("?")[0]


def main_image_problem(gid, main_url):
    """⑨b 主图方案合规校验：返回 (ok, note)。

    ok=True  → 复刻式且已逐字核验
    ok=False → 有明确缺陷，必须红
    ok=None  → 该商品无记录（历史商品由 guard 决定是否豁免）
    """
    rec = read_manifest(gid)
    if not rec:
        return None, "无主图生成记录"
    mode = rec.get("mode")
    if mode not in ALLOWED_MODES:
        return False, "非复刻式（mode=%s）" % mode
    if mode == SELF_MODE:
        # 「按阿奇索 ID 上 SKU」流程不生成主图（图由用户/历史自备）：
        # 不能因为它没走复刻式就一律判红，也不能白放过——必须留下逐字 OCR 全文并过禁词闸。
        if not rec.get("uploaded") or not rec.get("main_img_url"):
            return False, "自备主图未登记线上图片 URL"
        if main_url and whitelist_url(main_url) != whitelist_url(rec.get("main_img_url")):
            return False, "线上主图与登记记录不一致（疑似被替换）"
        txt = str(rec.get("ocr_text") or "").strip()
        if len(txt) < 4:
            return False, "自备主图缺逐字 OCR 全文，无法证明核过图上的字"
        bad = forbidden_on_image(txt)
        if bad:
            return False, "自备主图出现禁词：%s" % bad
        if not rec.get("whitelist_verified"):
            return False, "自备主图未逐字核验"
        return True, "自备主图已逐字核验（%d 字，禁词闸通过）" % len(txt)
    if rec.get("sku_display_mode") not in SKU_DISPLAY_MODES:
        return False, "主图 manifest 缺少有效 SKU 展示模式（旧记录需重新留证）"
    if not isinstance(rec.get("displayed_skus"), list) or not rec.get("displayed_skus"):
        return False, "主图 manifest 缺实际展示档位"
    if not str(rec.get("sku_selection_evidence") or "").strip():
        return False, "主图 manifest 缺 SKU 选择依据"
    if rec.get("sku_display_mode") == "all" and not rec.get("all_skus_reminder"):
        return False, "主图全档位展示缺少提醒留证"
    if not rec.get("ref_pno"):
        return False, "缺参考图货源编号"
    if not rec.get("ref_acct"):
        return False, "缺参考图货源账号归属"
    if rec.get("ref_source") == "supplier":
        if not rec.get("ref_source_name"):
            return False, "货源参考图缺 source 归属证据"
        if rec.get("ref_match") != "source+pno" or not rec.get("ref_evidence"):
            return False, "货源参考图缺 source+pno 精确匹配证据"
    if not rec.get("ref_url"):
        return False, "缺参考图 URL"
    if not rec.get("uploaded") or not rec.get("main_img_url"):
        return False, "未记录上传线上主图"
    if main_url and whitelist_url(main_url) != whitelist_url(rec.get("main_img_url")):
        return False, "线上主图与复刻记录不一致（疑似被替换）"
    if not rec.get("whitelist_verified"):
        return False, "出图未逐字核验（白名单：%s）" % " / ".join(rec.get("whitelist") or [])[:120]
    # 白名单自身含禁词 = 把「充值账号」这类参数名当买家填写内容（165 事故形态），必须红
    for w in (rec.get("whitelist") or []):
        w = str(w)
        if w.startswith("下单填写"):
            bad = forbidden_on_image(w[len("下单填写"):])
            if bad:
                return False, "白名单把参数名/禁词当买家填写内容：%s（应为手机号/平台账号等具体标识）" % bad
    return True, "复刻式 pno=%s 参考图=%s 白名单已核验" % (
        rec.get("ref_pno"), rec.get("ref_source") or "supplier")


def _self_test(args):
    import importlib.util
    # prompt_guard 与 kuaipao_gen 同目录，跟着 CFG 走（换机器不再写死）
    _kp = (_CFG.kuaipao_gen if _CFG else None) or \
        r"C:\Users\Administrator\Desktop\workbuddy\文档提取\_yq_poster\kuaipao_gen.py"
    guard_path = Path(_kp).parent / "prompt_guard.py"
    spec = importlib.util.spec_from_file_location("prompt_guard", guard_path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    src = args.source or source_of(args.acct)
    info = lookup_supplier(args.pno, src)
    skus = [x.strip() for x in args.sku.split(",") if x.strip()]
    name = args.name or clean_product_name(args.title or info.get("name") or "")
    label = str(args.account_label or "").strip()
    if not label and info.get("form") != "卡密" and info.get("buyer_kind") in ("标识", "平台账号"):
        label = info.get("buyer_field") or ""
    prompt = build_prompt(name, skus, label, args.brand)

    print("参考图来源:", src, "| pno =", args.pno)
    print("素材命中:", info["found"], "| 商品名:", info["name"])
    print("商品图:", info["img"] or "(无)")
    print("买家填写:", label or "无（不印填写句）", "| 解析:", info.get("buyer_kind"),
          "|", info.get("buyer_evidence", ""))
    print("档位(自身SKU):", skus)
    print("\n--- 复刻式提示词 ---\n" + prompt)
    print("\n--- 文字白名单（出图后逐字核验）---")
    print(" / ".join(text_whitelist(name, skus, label, args.brand)))
    print("\n--- 成品图禁词（出现任一即不合格）---")
    for cat, words in IMAGE_FORBIDDEN_HINT:
        print("  %s：%s" % (cat, words))
    print("  商品名/档位本身含某词时豁免：%s" % (" ".join([name] + list(skus)) or "无"))

    v = guard.check_prompt(prompt)
    print("\nprompt_guard:", "✅ 通过" if not v else "❌ %s" % v)

    if args.fetch_ref and info["img"]:
        dest = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_replica_ref_%s_%s.img" % (src, args.pno))
        try:
            download_ref(info["img"], dest)
            print("参考图下载: ✅", dest, os.path.getsize(dest), "字节")
        except Exception as e:
            print("参考图下载: ❌", e)
            return 1
    return 0 if not v else 1


def main():
    ap = argparse.ArgumentParser(description="复刻式生图固定模块（自检 / 参考图 / 生成记录）")
    ap.add_argument("--self-test", action="store_true", help="只生成并检查提示词，不调 API、不写线上")
    ap.add_argument("--mark-verified", action="store_true", help="逐字核验通过后标注（guard ⑨b 变绿的唯一途径）")
    ap.add_argument("--record-self-supplied", action="store_true",
                    help="登记「主图由用户自备/历史遗留」：必须同时给 --gid --img-url --ocr-file")
    ap.add_argument("--img-url", default="", help="线上主图 URL（--record-self-supplied 用）")
    ap.add_argument("--ocr-file", default="", help="图上逐字 OCR 全文的文本文件（--record-self-supplied 用）")
    ap.add_argument("--show", action="store_true", help="查看某商品的主图生成记录")
    ap.add_argument("--gid", default="", help="阿奇索商品 ID（--mark-verified / --show 用）")
    ap.add_argument("--note", default="", help="核验说明")
    ap.add_argument("--pno", default="1425")
    ap.add_argument("--source", default="")
    ap.add_argument("--acct", default="95425")
    ap.add_argument("--sku", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--account-label", default="")
    ap.add_argument("--brand", default="")
    ap.add_argument("--fetch-ref", action="store_true", help="同时把货源商品图下载到本目录")
    args = ap.parse_args()

    if args.record_self_supplied:
        if not args.gid or not args.ocr_file:
            print("--record-self-supplied 需要 --gid 与 --ocr-file（图上逐字全文）")
            return 2
        try:
            with open(args.ocr_file, encoding="utf-8") as f:
                txt = f.read()
        except OSError as e:
            print("读不到 OCR 文件：%s" % e)
            return 1
        ok, msg = record_self_supplied(args.gid, txt, args.img_url, args.note)
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    if args.mark_verified:
        if not args.gid:
            print("--mark-verified 需要 --gid")
            return 2
        try:
            rec = mark_verified(args.gid, args.note)
        except RuntimeError as e:
            print("❌ 不能标注：%s" % e)
            return 1
        print("✅ 已标注逐字核验通过：%s" % args.gid)
        print("   白名单：%s" % " / ".join(rec.get("whitelist") or []))
        return 0

    if args.show:
        if not args.gid:
            print("--show 需要 --gid")
            return 2
        rec = read_manifest(args.gid)
        if not rec:
            print("(无记录) %s" % args.gid)
            return 1
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        ok, note = main_image_problem(args.gid, rec.get("main_img_url"))
        print("\n⑨b 判定:", ("✅ " if ok else "❌ ") + note)
        return 0

    if not args.self_test:
        ap.print_help()
        return 0
    return _self_test(args)


if __name__ == "__main__":
    sys.exit(main())
