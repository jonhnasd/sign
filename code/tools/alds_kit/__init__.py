# -*- coding: utf-8 -*-
"""alds_kit —— 阿奇索(闲鱼)上品能力层。

设计依据（2026-11-14 用户拍板）：
  把「新建宝贝」链路里已经验证过的步骤抽成能力模块，ID 上 SKU / 存量返工
  复用同一批模块，新规则只改一处。

三层，不许跨层反向依赖：
  ① contract  对象字段 + 单一事实来源清单（纯文档 + 常量）
  ② 能力模块   supplier / media / main_image（纯逻辑为主，副作用集中在函数末尾）
  ③ 编排器     各 pipeline_*.py 只写「顺序 + 闸门」，不写实现

硬约束：
  · 能力模块之间可以互相调用，但不许 import 任何 pipeline_*；
  · 一个事实只有一个来源，见 contract.SOURCE_OF_TRUTH；
  · 旧脚本名（create_from_pno / deploy / replica_main_image）保持不变，
    内部改为调用本包，外部引用不受影响（绞杀式迁移）。
"""
import os
import sys

__version__ = "0.1.0"

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 让包内模块能 import 平级的 agiso_direct / replica_main_image（旧脚本不搬家）
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

__all__ = ["TOOLS_DIR", "contract", "supplier", "media", "main_image"]
