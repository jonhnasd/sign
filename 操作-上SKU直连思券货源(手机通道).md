---
tags: [操作, 阿奇索, 思券, 上SKU, 手机通道]
type: 操作
created: 2026-11-05
updated: 2026-11-13
owner: 秋雨
status: legacy
execution: read_only
verified_at: 2026-11-14
review_by: 2027-02-14
---

# 操作 · 上SKU 直连思券货源（手机通道）

> [!warning] 2026-11-13 口径更新（先看这条）
> 用户确认「思券不用手机链接，电脑也可以」；本机实测电脑直连目录一次返回 1088 条，无需手机、无需绑定 WiFi 网卡。
> **现行入口改为 [[项目-三家货源固定素材库]]**：三家固定素材已入库，思券复用 2026-11-04 历史全量（1123 清单 + 1081 详情），不再重复抓取。
> **现行口径**：电脑直连可用，常规取素材查 [[项目-三家货源固定素材库]]；本文手机通道已不在现行流程内，仅作电脑端异常时的备用方案，别照着做常规取数。正文其余内容为历史留档。

## 🚀 快速开始

> [!note] 一句话
> 备用通道：仅在本地固定素材缺失且电脑直连异常时，使用手机登录态拉取商品名、介绍和图集；正常流程优先查 [[项目-三家货源固定素材库]]。

### 使用前确认

1. 先查 `货源素材/` 是否已有该商品固定素材；有则复用，不重复抓取。
2. 电脑直连可用时优先使用电脑端，不为常规取素材启动手机链路。
3. 只有电脑端确实异常且需要登录态详情时，才检查手机 ADB 与 JWT。

### 前置条件
```bash
# 手机 adb 在线
"C:/Users/Administrator/.workbuddy/tools/adb/platform-tools/adb.exe" devices
# 手机登录态可用；JWT 过期时才需要重新取
```

### 一键入口

```bash
cd "C:/Users/Administrator/Desktop/workbuddy/文档提取"

# 入口：<关键词|ID> → 打印名称/介绍/图集/周期，并存 siquan_<id>.json
python 上sku_siquan.py <关键词或商品ID>
```

### 预期输出
```
名称: xxx会员月卡
介绍: ……
图集: 3 张
周期: 30天
✓ 已保存 siquan_<id>.json
✗ 「请登录后操作」→ JWT 过期 → 手机在线重取
```

### 完整步骤
1. 确认本地素材缺失且电脑端取数异常。
2. 必要时手机 ADB 在线并确认登录态有效。
3. `python 上sku_siquan.py <关键词|ID>`，只将缺失素材补入工作流程。
4. 结果用于 `deploy.py` 文案⑪ 与详情图⑬；价格、库存、可售与限价仍需现场读取。

> 本文是**历史备用操作**。正文后续接口细节用于故障排查，不得将历史上的“电脑必须返回空”描述当作现行结论。
>
> 2026-11-05 建立。配合 [[操作-阿奇索上品一条龙]]（上 SKU 流程）与 [[项目-sqqy88商品抓取]]（思券协议）。
>
> **定位**：阿奇索里思券已是发货货源；手机通道只在电脑端异常时用于补拉商品名、介绍和图集。

---

## 一、前提

- 手机已 adb 连接（USB 调试授权），连着**放行出口 WiFi**（柘城网段 `192.168.0.x`）。
- `.sqqy88_jwt.txt` 未过期（uni 端详情需登录态，约 7 天；过期后 `extract` 返回「请登录后操作」，需手机在线重取）。
- 依赖：Python（默认 env）、`adb.exe`（`C:\Users\Administrator\.workbuddy\tools\adb\platform-tools\`）。

## 二、脚本（均在 `Desktop/workbuddy/文档提取/`）

| 文件 | 作用 |
|---|---|
| `siquan_phone.py` | 手机通道模块：自动连 adb、`make_sign`、search/detail/类别/实付价、`extract()` 抽名称/介绍/图集/周期 |
| `上sku_siquan.py` | 入口：`<关键词|ID>` → 打印名称/介绍/图集/周期，并存 `siquan_<id>.json` |

### 🔴 思券商品 id ≡ 阿奇索货源 pno（2026-11-13 实测确认）

**两套编号是同一个**。思券站 CRMEB 的 `goods_id` 直接等于该商品在阿奇索里的货源编号 `productNo`：

| 思券 id | agiso pno | 商品 | 标题 |
|---|---|---|---|
| `11` | `11` | 魔音工坊VIP标准版月卡 | 【官方卡密】魔音工坊VIP标准版『月卡』限价25.8 |
| `1177` | `1177` | 剪映SVIP月卡 | 剪映会员【链接直冲】剪映SVIP会员=====月卡 |
| `1176/1175/1174` | 同 | 剪映SVIP 1天/三天/7天 | 同上系列 |

→ **用户说「思券 id N」= 阿奇索 pno N**，可直接喂 `create_from_pno.py --acct 99569 --pno N`，无需再做 id→pno 换算。

### 🔴 思券商品的介绍/图集不一定有（2026-11-13 实测）

`id=11`（魔音工坊月卡）`intro_text` **长度为 0**、`notice_text` 空、图集只有 1 张。此时 `deploy.auto_copy()` 会因「无详情素材」**整个跳过标题与描述生成** → 描述停在默认模板、缺【档位对照】→ ⑦ 报红。
→ **无介绍商品必须手写 spec 的 `title` + `desc`**（见 [[操作-从货源编号新建宝贝]] 实测记录）。

### 签名（同 [[项目-sqqy88商品抓取]]）
```
KEY = 18a3257675b85febdfcdd83e7150c0b9
H5 端: md5(md5(md5("front"+KEY)+ts))+ts   → /front/diy/*
uni端: md5(md5(md5("h5"+KEY)+ts))+ts      → /uni/*   （详情需 JWT）
```

## 三、用法

```bash
cd C:/Users/Administrator/Desktop/workbuddy/文档提取
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

"$PY" 上sku_siquan.py 剪映          # 关键词搜索，列命中；仅 1 个命中则直接拉详情
"$PY" 上sku_siquan.py 1177          # 直接拉 goods_id=1177 的详情
"$PY" 上sku_siquan.py 1177 --no-save # 不写 JSON
"$PY" 上sku_siquan.py 1177 --spec    # 同时生成 spec_siquan_1177.json 骨架（待补阿奇索侧字段）
```

> **一条命令全流程**：`上sku_siquan.py <ref> --spec` = 自动 `adb devices` 检测手机 → 手机通道拉思券（名称/介绍/图集/周期/到手价）→ 生成 `spec_siquan_<id>.json` 骨架。思券侧字段真填，`goods/kind/property/acct/skus[].pno` 等阿奇索侧留 `_todo` 待补，补全后再喂 `deploy.py`。

输出：商品名 / 标价 / 库存 / 图集张数+URL / 周期 / 介绍前若干行 / 购买须知；默认存 `siquan_<id>.json`。

## 四、字段映射（→ 上SKU 模板）

| 思券字段 | 上 SKU 用途 | 模板行 |
|---|---|---|
| `goods_name` | 闲鱼标题（⑪ 标题来源） | 文案(10) |
| `intro_text` / `notice_text` | 描述「使用说明」段（⑪，已抽纯文本） | 文案(10)、卡密说明(8) |
| `images[]` | 详情图上传（⑬，上限 9 张，幂等） | 详情图片(12) |
| `period` | 周期标注（⑩：每月1号/31天充一次…） | 充值周期(13) |
| `price` / `stock` / `sales` | 定价/库存参考（发货货源在阿奇索已配，此处仅展示） | — |
| `coupon_price`（get_goods_price） | 到手价参考（弹窗「券后价」） | 定价参考 |

## 五、思券商品弹窗数据（均可拉取，无需抓 UI）

思券商品在手机上点开后弹出的详情/购买弹窗，其显示内容**全部来自后端接口**，
我们已验证可直连拉取（2026-11-05 实测，手机通道）：

| 弹窗展示 | 接口 | 实测返回 |
|---|---|---|
| 名称 / 介绍 / 图集 / 库存 / 销量 / 分类 / 须知 | `POST /uni/categoods` | 51 字段全返回 |
| 到手价 / 券后价 / 优惠 | `POST /uni/goods/get_goods_price` | `coupon_price` / `received_price` / `goods_price` |
| 搜索列表（弹窗前的入口） | `POST /front/diy/goods/index` | 列表 + 分页 |

→ **结论**：弹窗只是接口数据的渲染层，直接调接口拿到的即弹窗全部内容，结构化、不依赖 DOM、不怕前端改版。

⚠️ **多规格商品**（`spec_type≠0`）：弹窗里的「选规格/档位」选项来自商品的 spec 字段，
当前 `extract()` 未单独拉取 spec 明细。若上 SKU 遇到带档位商品，需补解析 spec（见 [[项目-sqqy88商品抓取]]）。

## 六、接入上 SKU 流程

1. 用户说「上sku」→ 发 [[操作-阿奇索上品一条龙]] 模板 → 回填（含思券商品关键词/ID）。
2. 我跑 `上sku_siquan.py <ref> --spec` 直连思券，把名称/介绍/图集/周期/到手价拉回，并生成 `spec_siquan_<id>.json` 骨架（思券侧已填，阿奇索侧 `_todo` 待补）。
3. 我（或你）补全 `_todo` 里的 `goods`(阿奇索宝贝ID)/`kind`/`property`/`acct`/`skus[].pno` 等，即得完整 spec。
3. 据此填模板的文案⑪ / 详情图⑬ / 周期⑩；发货货源（spType=6 / pno）用阿奇索里已接的思券账号，不在此处改。
4. 生成 `spec.json` → `deploy.py --dry` → 确认 → `--go`。

## 六、相关

- [[操作-阿奇索上品一条龙]] —— 上 SKU 流程权威源
- [[操作-阿奇索宝贝SKU设置]] —— 接口层（配货源/改价）
- [[项目-sqqy88商品抓取]] —— 思券协议细节（签名/风控/字段）
- [[项目-手机调试能力链]] —— 手机接入与 adb 通道
