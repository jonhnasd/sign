---
tags: [操作, 阿奇索, 思券, 上SKU, 手机通道]
type: 操作
created: 2026-11-05
updated: 2026-11-05
owner: 秋雨
status: 可用
---

# 操作 · 上SKU 直连思券货源（手机通道）

> 2026-11-05 建立。配合 [[操作-阿奇索上品一条龙]]（上 SKU 流程）与 [[项目-sqqy88商品抓取]]（思券协议）。
>
> **定位**：阿奇索里思券**已是发货货源**（spType=6）。手机上的思券只用来**拉商品名 / 介绍 / 图集**，填进闲鱼文案⑪ 与详情图⑬。
> 思券站按**出口 IP 风控**，电脑直连被拦；**手机出口放行**，故走手机通道。

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
