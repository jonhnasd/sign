---
created: 2026-11-10
updated: 2026-11-11
tags: [闲鱼, 主图, 卡券, prompt, 范例]
type: 操作
status: active
execution: read_only
verified_at: 2026-11-14
review_by: 2027-02-14
---

# 卡券主图 prompt — 社区改进范例（实测出图）

> **定位**：把社区里现成的「卡券/代金券主图 prompt」（稿定 AI 的**美团团购代金券**、**网盘超级 SVIP** 等）改写成**合规 + 可复用**的卡券主图提示词，并经快跑 `gpt-image-2.6` 实跑出图验证通过。
> **来源**：2026-11-10 用户从 GitHub / 设计社区查到卡券主图 prompt 后，要求「按社区的美团/网盘这些 prompt 改进下，试下」。
> **关联**：`闲鱼主图范式库.md`（选型总入口）、`操作层规范.md`（笔记格式）

---

## 🚀 快速开始

### 前置条件
- 已有一张目标卡券的**原图**（图生图传 `--ref` 保住品牌 Logo）
- 快跑 API key 已按规范**加密入库**：`secrets/credentials.sops.yaml` → `kuaipao` 段（明文不写进笔记/日志），取用命令见第五节
- 已确认品牌标识描述 / 主视觉大字 / 时长档位 / 限制说明 四要素

### 一键入口
1. 从第二节选风格：**A 黑金**（尊享感）/ **B 红橙**（讲清档位）
2. 按第四节「复用方法」替换 5 处占位（品牌/大字/副标题/档位/限制）
3. **出图前**跑 `python prompt_guard.py --check 你的prompt.txt` 确认无时效词
4. 执行（key 从加密凭据临时取出，不落盘）：
   ```bash
   export KUAIPAO_API_KEY=$(SOPS_AGE_KEY_FILE="C:/Users/Administrator/.workbuddy/tools/crypto/age/keys.txt" \
     "C:/Users/Administrator/.workbuddy/tools/crypto/sops.exe" --decrypt \
     --extract '["kuaipao"]["key"]' \
     "C:/Users/Administrator/Desktop/obisidian/obisidian/secrets/credentials.sops.yaml")
   python kuaipao_gen.py \
     --ref 原图.jpg --prompt-file 你的prompt.txt \
     --out out/卡券.png --size 1024x1024 --model gpt-image-2.6
   ```

### 预期输出
- 1:1 正方形卡券主图，Logo 保留未遮挡，无「秒到账/自动发货」等时效词
- 底部信任背书「官方正品 充值本人账号 不支持电视端」清晰可读
- 含「uu小铺」固定角标，与原图 ≥2 项不同

### 完整步骤

1. 提取原图可见文案 → 列给用户确认（删时效词、不加未确认的商品信息）
2. 选 **A 黑金 / B 红橙**，按第四节替换 5 处占位
3. `python prompt_guard.py --check 你的prompt.txt` 过禁词
4. 用第五节命令从加密凭据临时取 key → `kuaipao_gen.py --model gpt-image-2.6` 出图
5. 放大 200% 逐字核对中文 → 按 [[项目-剪映主图与商品补全]] §2.5 两步法上传主图、下载线上图回读
6. 核对主图档位/价格与商品 SKU、描述【档位对照】、标题**四处一致**

---

## 一、社区 prompt 的「好」与「坑」

社区卡券主图 prompt（如美团代金券、网盘 SVIP）暴露的**固定结构**，和我们已有的体系一致：

- 保留官方 Logo 不重绘 + 差异化二创
- 卡型 / 渐变背景 + 品牌 Logo + 面值或时长档位 + 券名 + 卖点标签 + 店铺角标
- 文字不遮挡 Logo、差异化二创

**但社区 prompt 普遍踩雷**：用了 `秒到账 / 1分钟到账 / 24小时自动发货` 这类**到账时效词** —— 这正是我们 `prompt_guard.py` 已禁掉的闲鱼/淘宝违规词。

**本范例做的事**：照搬社区「黑卡 + Logo + 面值 + 直充说明」的结构，但把违规时效词**全部替换为合规信任背书**：

| 社区原做法（违规） | 本范例改写（合规） |
|---|---|
| 「官方直充｜秒到账」 | 「官方正品 充值本人账号 不支持电视端」 |
| 「下单后填写账号 充值1分钟到账」 | 同上信任背书，删掉时效描述 |
| 「24小时自动发货」 | 直接删除，不写发货速度 |

---

## 二、范例 A — 黑金高端风（适合中高客单 / 尊享感）

**适用**：影音 / 会员 / 权益类卡券，想要「显贵」质感时。
**实测**：2026-11-10 以喜马拉雅 VIP 月卡原图做图生图，保 Logo，出图合格（Logo 保留、月卡大标题、底部信任背书、无时效词）。

```text
基于参考图保留喜马拉雅品牌标识（红色“听”字方形图标与“喜马拉雅”字样），重新设计为一张 1:1 电商卡券主图。整体纯黑高级背景，中央放置一张红橙渐变立体会员卡，卡面大号白色粗体标注“月卡”，下方小字“喜马拉雅VIP会员”。左上角保留品牌 logo 不重绘、不被遮挡。卡面右下角用浅色半透明小字写店铺角标“uu小铺”。底部一条干净区域用克制的中文写信任背书：“官方正品 充值本人账号 不支持电视端”。科技感光影，霓虹微光点缀，主体居中，画面留白充足，层次清晰，商业电商主图质感，超清 8K。构图元素克制，文字不遮挡品牌标识，不含任何与物流时效或发货速度相关的描述文字。
```

---

## 三、范例 B — 红橙品牌渐变风（适合贴合原图色系 / 讲清档位）

**适用**：想保留原图品牌色、且需要把「时长档位」一次性列清的卡券。
**实测**：2026-11-10 喜马拉雅月卡出图合格；唯一瑕疵是「uu小铺」水印与「年卡」档位稍挤，**正式上架前把水印挪开即可**。

```text
基于参考图保留喜马拉雅品牌标识（红色“听”字方形图标与“喜马拉雅”字样），重新设计为一张 1:1 电商卡券主图。红橙品牌渐变背景，中央一张干净立体会员卡，左上角保留品牌 logo 不重绘、不被遮挡，卡面中央大号白色粗体“月卡”，下方“喜马拉雅VIP会员”。卡面右侧用小图标加短标签列出时长档位：“周卡 月卡 季卡 年卡 全平台通用”。右下角浅色半透明店铺角标“uu小铺”。底部一条干净区域写信任背书：“官方正品 充值本人账号 不支持电视端”。柔和棚拍光，主体居中，画面留白充足，商业电商主图质感，超清 8K。构图元素克制，文字清晰不重叠，不含任何与物流时效或发货速度相关的描述文字。
```

---

## 四、复用方法（换品只改这几处）

这两条 prompt 是**以喜马拉雅月卡为样本写出**的，复用给其他卡券时只替换以下占位即可，结构不变：

| 替换项 | 范例 A / B 中的位置 | 说明 |
|---|---|---|
| **品牌标识描述** | `保留喜马拉雅品牌标识（红色“听”字方形图标与“喜马拉雅”字样）` | 改成目标品牌的真实 Logo 描述 |
| **主视觉大字** | `标注“月卡”` / `粗体“月卡”` | 改成目标时长/主卖点（如「季卡」「SVIP」） |
| **副标题** | `下方小字“喜马拉雅VIP会员”` | 改成目标品类名 |
| **时长档位（仅 B）** | `周卡 月卡 季卡 年卡 全平台通用` | 改成目标商品的真实档位 |
| **限制说明** | `不支持电视端` | 按商品真实限制写（没有就删掉这一句） |
| **店铺角标** | `“uu小铺”` | 保持固定 |

> ⚠️ 替换时**不要**加回「秒到账 / 自动发货 / 24h」等时效词 —— 这是本范例相对社区 prompt 的核心合规升级。

---

## 五、调用命令（快跑 API）

> ⚠️ **模型与代理坑**（2026-11-10 实测）：
> - 这把 key（newapi_channel_conn，url `https://kuaipao.ai`）所属分组「gpt_绘图」**只支持 `gpt-image-2.x` 系列**（含 `2.6`），**不支持** `nano-banana-2-*`（`nano-banana` 是另一把 key 的通道）。调用必须显式 `--model gpt-image-2.6`。
> - 本机系统代理 `127.0.0.1:54387` 会把 `kuaipao.ai` 拦成 503；`kuaipao_gen.py` 已加强制直连 opener 修复。
> - `KUAIPAO_API_KEY` **可入库但必须加密**：2026-11-11 已用 sops+age 写入 `secrets/credentials.sops.yaml` → `kuaipao` 段（`_type=newapi_channel_conn` / `url=https://kuaipao.ai` / `key`），值为 `ENC[...]` 密文。取用只走 `sops --decrypt --extract '["kuaipao"]["key"]'` 临时注入环境变量，明文不写进笔记、日志或命令行历史。

```bash
# 图生图（带原图保 Logo），从工作目录 _yq_poster/ 执行
export KUAIPAO_API_KEY=$(SOPS_AGE_KEY_FILE="C:/Users/Administrator/.workbuddy/tools/crypto/age/keys.txt" \
  "C:/Users/Administrator/.workbuddy/tools/crypto/sops.exe" --decrypt \
  --extract '["kuaipao"]["key"]' \
  "C:/Users/Administrator/Desktop/obisidian/obisidian/secrets/credentials.sops.yaml")
python kuaipao_gen.py \
  --ref 原图.jpg \
  --prompt-file 卡券promptA_黑金.txt \
  --out out/卡券A.png \
  --size 1024x1024 \
  --model gpt-image-2.6

# 范例 B 同样换 --prompt-file 与 --out 即可
```

---

## 六、关联文件

- `闲鱼主图范式库.md` —— 6 套范式选型总入口（本范例属于「社区改进」路线，可与范式③深色尊享 / 范式⑥ 3D 展台互为替代）
- [[项目-剪映主图与商品补全]] —— 端到端实跑：出图 → 上传两步法 → 补 SKU/描述/标题
- `prompt_guard.py` —— 出图前必过的到账时效禁词校验
- `secrets/credentials.sops.yaml` —— 快跑 API 凭据密文（`kuaipao` 段，sops+age；取用命令见第五节）
- 工作目录资产：`_yq_poster/prompt_喜马拉雅A_黑金.txt`、`_yq_poster/prompt_喜马拉雅B_红橙.txt`、`_yq_poster/ref_喜马拉雅月卡.jpg`、`_yq_poster/out/喜马拉雅A.png`、`_yq_poster/out/喜马拉雅B.png`
