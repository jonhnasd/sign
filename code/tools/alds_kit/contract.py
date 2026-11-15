# -*- coding: utf-8 -*-
"""contract —— 上品对象的字段契约 + 单一事实来源清单。

这一层只放「定义」，不放逻辑。改动这里等于改所有链路的约定，必须同步文档：
  Obsidian `操作-阿奇索上品一条龙.md`、`闲鱼主图范式库.md` §8.8。

为什么单独一层：
  2026-11-14 之前，「买家该填什么」在 4 处各存一份（知识库、replica 的
  BUYER_FIELD_RULES、create_from_pno 的主图、deploy 的描述），于是同一个错误
  修了三次仍在漏。契约层的作用是让「重复」变成「可检查」。

用法：
  from alds_kit.contract import MAIN_IMAGE_MODES, SOURCE_OF_TRUTH, check_listing
"""

# ---------------------------------------------------------------- 核心对象字段
# Listing = 一个待上架商品。字段名是全链路通用叫法，映射到阿奇索字段见注释。
LISTING_FIELDS = {
    # 身份
    "goods": "阿奇索商品 id（新建链路发布后才拿到；草稿阶段为空串）",
    "acct": "货源账号 idNo（志远 95425 / 思券 99569 / 商战 96810）",
    "kind": "recharge | kaomi | kaomi_multi | single —— 决定是否要买家填账号、是否设直充标志",
    # 货源
    "pno": "主货源编号；多档时在 skus[].pno",
    "skus": "档位列表 [{val, pno, cost, price, mult, sid}]",
    "property": "档位维度名（2-4 字，阿奇索硬校验）",
    # 买家侧
    "buyer_field": "买家下单要填的具体项（手机号 / 华为账号 / …）。**由 supplier 一次算出**，"
                   "copy 与 main_image 只读不算；卡密或原文没写清 → 空串",
    "title": "标题（≤90 字节，剔除风控词）",
    "desc": "描述正文（含【填写内容】【档位对照】）",
    # 图片
    "main_image": "replica | keep | skip —— 见 MAIN_IMAGE_MODES",
    "main_image_sku_mode": "replica 主图档位模式：highest 默认按目标 SKU 自身同单位时长/面额最大值；all 必须显式选择并提醒",
    "imgUrls": "线上图片列表，[0] 必须是主图",
    # 定价
    "profit": "利润率，默认 0.066（售价 = 进价 / 0.934）",
}

MAIN_IMAGE_MODES = {
    "replica": "复刻式重做（新建必用；ID 链路仅在用户/上游明确确认错配时使用）",
    "keep": "保留现有主图（ID 链路默认）。不得仅凭 URL 自动猜测错配",
    "skip": "完全不碰图片（仅用于纯文案返工）",
}

MAIN_IMAGE_SKU_MODES = {
    "highest": "默认；按目标 SKU 自身可比较的时长/面额最大值只展示对应档位",
    "all": "显式展示目标商品全部 SKU；生图前提醒并在 manifest 留证",
}

MAIN_IMAGE_REFERENCE = {
    "priority": ("调用方显式参考图", "当前 acct 映射的 source + pno 精确货源图"),
    "identity_key": "acct -> source 与 pno 联合匹配；禁止跨 source/pno 复用",
    "failure": "归属不明、缺图、下载失败或图片无效均抛 ReplicaRefMissing 并停止",
    "preflight": "deploy --go 在任何线上写入前预检；复刻阶段失败时不得继续后续写操作",
}

# ---------------------------------------------------------------- 单一事实来源
# 每条：事实 → 唯一定义位置 → 谁只读不写。
# 新增规则时先在这里登记，再写代码；否则一定会有第二份实现。
SOURCE_OF_TRUTH = {
    "买家填写文案": ("replica_main_image.BUYER_FIELD_RULES + resolve_buyer_field()",
                 "supplier.buyer_field_of() 唯一出口；copy / main_image 只读"),
    "档位切分": ("supplier.tier_val() / product_family()",
             "create_from_pno.emit_spec 与 ID 链路共用，禁止各写正则"),
    "售价与硬闸": ("deploy.SKU_COST_MAX / NO_LOSS / DEFAULT_PROFIT",
              "只允许 deploy.filter_plan_limits 执行，编排器不得自行算价"),
    "商品形态 kind": ("create_from_pno.emit_spec（productType 1=直充 2=卡密）",
                  "deploy 只读，不重新推断"),
    "主图方案": ("replica_main_image.build_prompt / write_manifest",
             "main_image 模块唯一出口；guard ⑨b 唯一验收"),
    "主图参考图": ("replica_main_image.resolve_reference",
               "唯一决定显式参考图或 source+pno 货源图；main_image/deploy 只调用并传递证据"),
    "主图档位展示": ("replica_main_image.select_sku_display",
               "默认按目标 SKU 自身时长/面额最大值只展示一档；all 必须显式指定并留提醒；不可比较即失败关闭"),
    "主图失败关闭": ("main_image.preflight_reference + deploy.preflight_main_image",
                 "缺图/归属不明/下载/生图/上传/置顶失败均阻止后续线上写操作"),
    "图上禁词": ("replica_main_image.IMAGE_FORBIDDEN",
             "主图 prompt 与 OCR 核验共用同一份"),
    "标题风控词": ("create_from_pno.RISK_WORDS / AGGRO_WORDS",
              "发布与文案共用，禁止在 deploy 再写一份"),
    "回归基线": ("tests/golden/ 下三个真实案例 + run_golden 里的不变量",
             "任何人改 core 层后必须跑；改期望值前先判断是「代码错了」还是「规则变了」"),
}

# 已知仍存在的重复实现（收口进度表，改完一项划掉一项）
KNOWN_DUPLICATES = [
    "✅ 已合并：deploy.upload_media / create_from_pno._upload_media / upload_main_images.upload_media → media.upload_media",
    "✅ 已迁出：主图能力（生图/置顶/清模板图）→ main_image 模块",
    "✅ 已加：deploy ⑭ phase_main_image（ID 链路与新建链路同一段代码，spec.main_image 控制）",
    "✅ 已加：guard ⑨b 比对 manifest.account_label 与当前 buyer_field",
    "✅ 已收口：resolve —— ID 链路 spec 加 auto_family 即自动补同产品线全档（supplier.build_skus）",
    "✅ 已补：文案时效承诺词拦截（alds_kit.copy，deploy 标题/描述/sanitize 三处出站口统一调）",
]

# 🔴 改完必须跑的验证（顺序即优先级）。跳过等于放弃「行为没变」这个结论。
VERIFY_AFTER_CHANGE = [
    "python tests/run_golden.py     # 真实案例断言，退出码 0 = 没漂",
    "python tests/mutate_check.py   # 确认用例本身还能抓到事故（改了断言就要跑）",
    "python _test_alds_kit.py       # 重构前后一致性（新老文件对比）",
    "python onepipe_guard.py --inspect   # 联机巡检（涉及线上商品时才跑）",
]



def check_listing(lst):
    """组装前的轻量自检：返回缺失/矛盾的字段名列表（不联网、不改任何状态）。

    编排器在调用副作用模块前必须跑一遍，避免「字段没传 → 静默走默认分支」
    （2026-11-14 之前 deploy 描述退化成「按页面提示填写」就是这类）。
    """
    bad = []
    if not str(lst.get("goods") or "").strip():
        bad.append("goods")
    if lst.get("kind") not in ("recharge", "kaomi", "kaomi_multi", "single"):
        bad.append("kind")
    if lst.get("main_image") not in MAIN_IMAGE_MODES:
        bad.append("main_image")
    if lst.get("kind") == "recharge" and not str(lst.get("buyer_field") or "").strip():
        # 不报错，只提示：卡密不填、直充原文没写清都合法，但必须显式知道自己在走哪条
        bad.append("buyer_field(空→描述写「按页面提示填写」，主图不印填写句)")
    return bad
