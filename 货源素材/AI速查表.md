---
created: 2026-11-13
updated: 2026-11-13
tags: [货源, 素材库, AI速查]
type: 索引
status: active
---

# AI 速查 · 三家货源固定素材库

> [!warning] 不要直接 Read 两个 JSON
> `货源商品清单.json` 12.5 万行 / `货源素材_详情.json` 4.7 万行，Read 会在 2000 行处截断。
> 本文件可整份读进上下文；查任何商品一律调 `query_supplier_assets.py`。

生成时间：2026-11-13 22:41:32 ｜ 数据时间：2026-11-13 22:41:31 ｜ 清单 **15503** 条 ｜ 有效详情素材 **2261** 条 ｜ 只读、不联网、不写线上
> 自动维护：每次跑 `fetch_supplier_assets.py` 入库后会自动重建本表；也可手动 `--write-digest`。

## 规模与覆盖率

| 来源 | 卡密 | 直充 | 合计 | 有详情素材 | 覆盖率 |
|---|---:|---:|---:|---:|---:|
| 志远 | 4417 | 5807 | 10224 | 633 | 6.2% |
| 商战 | 2075 | 2080 | 4155 | 539 | 13.0% |
| 思券 | 291 | 833 | 1124 | 1089 | 96.9% |

> 「查得到」≠「素材齐」：志远/商战详情只预热了候选池，命中后看 `素材` 短码。

## 常用命令（可直接复制）

```bash
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
Q="C:/Users/Administrator/WorkBuddy/2026-09-22-11-37-41/edge-bridge/tools/query_supplier_assets.py"
"$PY" "$Q" --pno 1220                       # 精确查一个编号（跨三家）
"$PY" "$Q" --keyword 剪映 --limit 10         # 名称模糊搜，只出 10 行
"$PY" "$Q" --keyword 剪映 --source 志远 --form 直充
"$PY" "$Q" --pno 1220 --source 志远 --full  # 完整固定字段（含主图 URL）
"$PY" "$Q" --pno 1220 --show intro --chars 600   # 单条介绍正文，截断输出
"$PY" "$Q" --stats                          # 统计，零明细
"$PY" "$Q" --keyword 剪映 --json --limit 5  # 给其他脚本调用
```

## 输出读法

- `素材` 短码：**G** 主图 / **I** 图集 / **T** 介绍 / **N** 购买须知 / **F** 充值表单；`-` 表示缺，`无素材` 表示未预热。
- 默认 `--limit 20`；`--show` 只对单条生效，避免长 HTML 灌进上下文。
- 多关键词默认全部命中（`--match any` 改任一）；`--source/--form/--pno` 可叠加。

## 红线

- 本库只有**固定字段**：编号、名称、形态、图、介绍、弹窗、详情、接口网址。
- 进价、库存、可售、余额、限价**不在库里**，上架时现场取，不得用本库推算收益。
- 素材是货源内部原文，买家标题/描述/SKU 说明须脱敏，禁止出现货源编号、供应商名、网站/域名。
- 数据目录：`C:/Users/Administrator/Desktop/obisidian/obisidian/货源素材`；权威说明见库根 `项目-三家货源固定素材库.md`。
