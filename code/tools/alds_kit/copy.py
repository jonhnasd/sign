# -*- coding: utf-8 -*-
"""copy —— 买家可见文案的清洗能力（唯一实现）。

目前只有一件事：**删掉到账/发货时效承诺**。

为什么必须删（不是"最好别写"）：
  闲鱼对「24小时自动发货 / 秒接单 / 立即到账」这类承诺按虚假宣传处理，
  轻则下架重则扣分；而且这类文字多半是从上游详情整段抄来的，不是我们自己想写。
  上游可以写，我们抄了就是我们的责任。

🔴 口径（别改坏了）：
  · 「自动发货」「直充自己账号」本身**不算**违规 —— 那是履约方式描述，标题里一直在用；
  · 违规的是**带时间承诺**的写法：「24小时自动发货」「5分钟内到账」「秒接单」「极速发货」；
  · 所以清单里全是「时长 + 动作」的组合，不是孤立动词。孤立动词一律放行。

与图上禁词的关系：源头是 `replica_main_image.IMAGE_FORBIDDEN` 的「时效承诺」一条，
本模块 import 它再补几条**文案特有**的写法（图上印不出来的长句）。
不另写第二份基础清单，避免「图上拦了、文案没拦」或反过来。
"""
import re

from replica_main_image import IMAGE_FORBIDDEN

# 复用图上那一份基础清单（单一事实来源），再补文案专属变体：
#   图上是短标签，文案是整句 → 「5分钟内自动发货」「当天发货」这类只能在这里补。
_BASE = dict(IMAGE_FORBIDDEN)["时效承诺"]
_EXTRA = (r"\d+\s*(?:秒|分钟|小时)\s*(?:内|之内|以内)?\s*(?:自动)?\s*(?:发货|到账|充值|接单|出库|处理|完成)"
          r"|(?:当天|当日|隔天|次日)\s*(?:发货|到账|充值|完成)"
          r"|极速(?:发货|到账|处理|充值)"
          r"|(?:立即|马上|即刻|立刻)\s*(?:发货|充值|处理)"
          r"|秒(?:接单|发货|到账|充值|出库)")
# 🔴 长模式必须排在前面：否则「极速处理」会先被基础清单的「极速」吃掉，
#    按词删留下「处理」两个字（2026-11-14 实测踩到）。
TIME_PROMISE = _EXTRA + "|" + _BASE

_RE_TIME = re.compile(TIME_PROMISE)
_SPLIT_CLAUSE = re.compile(r"[，,；;、]")


def _tidy(s):
    """删句后的标点收敛：去行首悬空标点 + 收拢连续标点。

    不收拾会留下「。支持手机平板。」这种行首孤句号 —— 删句的副作用必须一起处理，
    否则原文案读起来像被打断的半句。
    """
    s = re.sub(r"^[。，,；;、\s　]+", "", str(s or ""))
    s = re.sub(r"[，,；;、]{2,}", "，", s)
    s = re.sub(r"。{2,}", "。", s)
    return s.strip()


def find_time_promise(text):
    """返回文本里命中的时效承诺片段（去重保序）。空列表 = 干净。"""
    out, seen = [], set()
    for m in _RE_TIME.finditer(str(text or "")):
        w = m.group(0).strip()
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def strip_time_promise(text, log=None):
    """删掉含时效承诺的**分句**，返回 (新文本, 被删片段列表)。

    为什么按分句删而不是按词删：删词会留下「，，下单单，无散」这种病句，
    比带承诺词更难读。整句拿掉，剩下的仍是通顺中文。
    一行删空则该行整行去掉，不留空行堆积。

    🔴 只处理文案，不碰标题里的「自动发货」—— 那种孤立动词不匹配本清单。
    """
    s = str(text or "")
    if not s.strip():
        return s, []
    removed, out = [], []
    for line in s.split("\n"):
        if not line.strip():
            out.append(line)
            continue
        hits = find_time_promise(line)
        if not hits:
            out.append(line)
            continue
        segs = _SPLIT_CLAUSE.split(line)
        kept = []
        for seg in segs:
            h = find_time_promise(seg)
            if h:
                removed.extend(h)
                continue
            if seg.strip():
                kept.append(seg.strip())
        new = _tidy("，".join(kept))
        if not new.strip("，,；;、 　"):
            # 整行会被删空：这行多半用空格而非标点分隔（如「当天发货 极速处理 客服在线」），
            # 按分句删会把无害内容一起带走 → 退回按词删，只摘掉承诺片段本身。
            cand = _RE_TIME.sub("", line)
            cand = _tidy(re.sub(r"[ \t]{2,}", " ", cand))
            # 剩不到 4 个字说明这行本来就是纯承诺（如「24小时自动发货」），整行去掉更干净
            new = cand if len(re.sub(r"[^\w\u4e00-\u9fa5]", "", cand)) >= 4 else ""
        if new:
            out.append(new)
        # 整行删空时不再记一条「整行文本」—— 命中的片段上面已经记过，重复记只会让日志难读
    # 收拢连续空行，避免删句后留下大段空白
    txt = "\n".join(out)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip("\n")
    if removed and log is not None:
        log.append({"removed": removed[:8], "count": len(removed)})
    return txt, removed
