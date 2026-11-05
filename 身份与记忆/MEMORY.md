---
created: 2026-09-23
updated: 2026-11-05
tags: [记忆, 用户级, 硬规则, SSOT]
type: 用户级记忆
status: active
---
# MEMORY.md — 用户级长期记忆

## 📍 本文件与 WorkBuddy 的关系（读之前先看）

**本文件是用户级记忆的唯一权威源。** WorkBuddy 通过「自动注入」把它带进每个新对话。

```
① 权威源（在这里，改这里）
   C:\Users\Administrator\Desktop\obisidian\obisidian\身份与记忆\MEMORY.md
                        │
                        │  sync-memory.sh  （单向：库 → 本地）
                        ↓
② 注入副本（WorkBuddy 自动读取，勿手改）
   C:\Users\Administrator\.workbuddy\user-6e1ce042-0701-4318-8682-d9adc18279df-personal\MEMORY.md
```

| 谁在用 | 读哪里 | 怎么改 |
|---|---|---|
| **WorkBuddy** | ② 注入副本 | **改 ①**，然后跑同步脚本 |
| **Claude Code** | ① 库内本文件 | 直接改 ① |
| **Codex** | ① 库内本文件 | 直接改 ① |

**同步命令**（改完 ① 后跑）：
```bash
bash C:/Users/Administrator/.workbuddy/tools/crypto/sync-memory.sh          # 有冲突会中止
bash C:/Users/Administrator/.workbuddy/tools/crypto/sync-memory.sh --force  # 放弃本地改动强制覆盖
bash C:/Users/Administrator/.workbuddy/tools/crypto/sync-memory.sh --check  # 只看差异
```

⚠️ **不要直接改 ②** —— 下次同步会被 ① 覆盖（脚本有冲突检测会提前警告，但改了仍会丢）。
⚠️ ② 里含**明文凭据**（① 里是加密后的指引），所以 ② 绝不能进 Git 仓库。

---

## 🚨 硬规则：每次任务前先读 Obsidian 库

**默认动作，不需要用户提醒。** 用户说「继续 / 接着上次 / 之前那个」时，**必须先读再动手**。

```
C:\Users\Administrator\Desktop\obisidian\obisidian\
├─ 长期记忆.md          ← 索引 / MOC（先看这个）
├─ 本机环境档案.md       ← 硬件 / 系统 / 工具链 / 网络限制
├─ 经验-踩坑手册.md      ← 坑与解法全量（动手前扫一遍）
└─ 记忆-回写规范.md      ← 读写规则
```

（目录名拼写为 `obisidian`，库在**嵌套一层**的子目录里。）

**任务完成后回写。** 敏感凭据（密码 / API key / token / 手机号）**不入库**。信息变化**就地更新**，不追加矛盾条目。

### 📚 库内分册速查（命中需求 → 直接读对应文件，不必全库扫描）

| 需求关键词 | 读这个文件 |
|---|---|
| 连手机 / 换手机 / adb 报错 | `项目-手机接入工具链.md`（**换机一条命令** `bootstrap.sh`） |
| 点手机屏幕 / 读屏 / 抓包 / 让 AI 操作手机 | `项目-手机调试能力链.md`（ADB→Shizuku→FIRERPA→MCP→MITM） |
| 抓 sqqy88 商品 / 详情 / 增量 / 签名算法 | `项目-sqqy88商品抓取.md`（双签名算法 + 出口 IP 风控，已脱机） |
| 找货源成本 / 货源站接口 | `项目-qcqcq货源抓取.md`（⚠️ legacy，方法论有效但货源平台已不在现行选源范围） |
| **闲鱼上商品 / 上 SKU / 存草稿箱** | `操作-阿奇索上品一条龙.md`（**主流程**：扒源→填模板→deploy.py→发货→直充→文案→草稿） |
| 闲鱼 SKU 档位 / 规格 / 价格怎么设 | `操作-阿奇索宝贝SKU设置.md`（接口层配方） |
| 拉商品介绍 / 图集 / 周期（思券） | `操作-上SKU直连思券货源(手机通道).md`（**必须走手机通道**，电脑直连被风控） |
| 操作用户正在用的浏览器 / 页面内接口 | `项目-edge-bridge.md` |
| 微信排版 / 请柬 / 改文案换图 | `项目-135编辑器.md` |
| **查硬规则 / 环境 / 沟通偏好 / 运营铁律** | `身份与记忆/MEMORY.md`（**本文件即权威源**） |
| 改了代码报奇奇怪怪的错 | `经验-踩坑手册.md`（按节号定位） |
| 硬件 / 网络限制 / 工具装哪了 | `本机环境档案.md` |
| 货源平台密钥 / APPID | `secrets/credentials.sops.yaml`（**加密**，用 `sync-memory.sh` 取明文） |
| 想知道这库怎么组织的 | `README.md` |
| 最近变更 / 哪篇刚改过 | `最近变更.md`（自动生成，git log 驱动） |
| **写笔记的格式规范 / 怎么写操作层** | `操作层规范.md`（**新笔记必须带「🚀 快速开始」块**，体检会查） |
| **写脚本前 / 找现成脚本** | `脚本索引.md`（706 个脚本按用途分类，**先查再写**） |
| **上新品 / 配 SKU / 找货源价 / 看历史上品** | `上品资料索引.md`（spec 模板 + 上品决策记录） |

### 🔑 age 私钥备份在哪（用户决定）

**用户 2026-11-05 决定：age 私钥备份放自己的云盘，不用密码管理器。**

- 本机：`C:\Users\Administrator\.workbuddy\tools\crypto\age\keys.txt`（主力）
- 桌面备份：`C:\Users\Administrator\Desktop\age-keys-BACKUP-勿外传.txt`
- **云盘备份**：用户自存（私钥全文 = `AGE-SECRET-KEY-` 开头那一整行）
- ⚠️ 私钥丢失 = 仓库里的密文**永久无法解密** → 云盘那份必须真的存
- 恢复流程见 `README.md`「换设备恢复流程」一节

**通用调用话术**：用户说「继续 / 接着上次 / 之前那个 / 类似任务」→ 先读 `长期记忆.md` 索引定位项目 → 读对应分册 → 再动手。

**写完 Obsidian 笔记后必跑完整性检查**（防止「写了但没挂索引」＝新对话发现不了）：
```bash
"C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" "C:/Users/Administrator/.workbuddy/tools/adb/check_vault.py"
```
检查：索引覆盖 / 速查表覆盖 / 双链断链 / 敏感凭据 / daily log 超 30 天未蒸馏。退出码 0 = 全通过。

## 🔄 记忆四写

变更同步四处：桌面文档 / Obsidian 库 + WorkBuddy 记忆 + Claude Code + Codex。

## 🌱 记忆 / Skill 自进化纪律（跨项目，2026-09-26 用户定）

记忆与 skill 不是存档，要**自己沉淀、自己淘汰、自己进化**，不等用户提醒：

- **沉淀**：每完成多步任务 / 踩新坑 / 发现可复用流程 → 立刻把结论写进对应 `MEMORY.md` 或 skill（不堆在聊天里）。
- **淘汰**：发现**过期 / 错误 / 自相矛盾**的条目 → 就地修正或删除，不保留矛盾副本。daily log 满 30 天按主题蒸馏进 `MEMORY.md` 后删原文件；skill 里失效脚本 / 误导步骤直接删。
- **进化**：skill 内容与实际不符（命令错、步骤漏、参数变）→ 不等用户说就 `SkillManage` 改；发现重复 / 重叠 skill 主动提示用户整理；单条过长就拆 / 合。
- **精简（2026-10-06 用户重申「自动蒸馏」）**：同一事实只在一处权威留存，别多处矛盾副本；**主动、不等提醒地蒸馏/删除不需要的东西**——`MEMORY.md` 超长就立刻砍细节、删总览表类冗余、合并重复；daily log 满 30 天按主题蒸馏进 `MEMORY.md` 后删原文件。

## 🖥 本机环境要点（速查）

- 机型 **Dell G3 3590**，i5-9300H，**8GB RAM（偏小）**，GTX1650，Win10 专业版 22H2
- 账户 `PC-20260922DWHG\Administrator`，⚠️ **但 WorkBuddy 里起的 PowerShell 进程 `IsAdmin = False`**（未提升）：写 `HKLM` 注册表被拒「不允许所请求的注册表访问权」，`dangerouslyDisableSandbox` 也无效。**需管理员权限的注册表操作 → 生成 `.reg` 文件让用户双击导入**。例外：`powercfg` 命令免提权即可写电源方案
- ⚠️ **`reg.exe` 在 WorkBuddy 程序黑名单里**（Program Blacklist）→ 备份/导入注册表都不能走 reg.exe，用 PowerShell `Get-ItemProperty` / `ConvertTo-Json` 代替
- ⚠️ **本机 ExecutionPolicy 禁止运行 `.ps1`** → 调用需 `-ExecutionPolicy Bypass`，且先 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
- ⚠️ **.ps1 也是 GBK 读取**（不止 .cmd）—— PowerShell 5.1 按 ANSI 读脚本，UTF-8 中文注释会被打乱导致「字符串缺少终止符」语法错误。**写 .ps1 同样必须纯 ASCII 注释**（已有 ASCII 版：`~\.workbuddy\tools\check-workbuddy-health.ps1`、`protect-memory.ps1`）
- ⚠️ **沙箱内 PowerShell 的 `Write-Host` 输出会被吞** → 调试脚本要支持 `-OutFile` 参数写文件再读，否则看不到任何输出、exit code 也可能异常
- ⚠️ **主网卡常是手机热点**（`Remote NDIS based Internet Sharing Device`，Realtek 有线口 Disconnected），热点抖动导致长连接 ECONNRESET。插网线后需确认双网卡 **metric 同分会让流量随机走热点**，要用 `Set-NetIPInterface -InterfaceMetric` 拉开优先级
- Go **1.27.1** 在 `D:\go`；项目 `D:\projects\crawler`；脚本 `D:\docker`
- Docker Desktop 已装但 **daemon 起不来**（WSL2 内核缺失）
- ⚠️ **网络**：`delivery.mp.microsoft.com`、`desktop.docker.com`、`gcr.io` 被墙；**仅中国移动 DNS 能解析部分主机**，别乱改 DNS
- ⚠️ **环境代理**：会话内有 `http_proxy/https_proxy=http://127.0.0.1:52510`。Python `urllib`/`curl` 会走代理 → 访问 **127.0.0.1 本地服务**（如 edge-bridge 8787）会报 `upstream connect failed`/502，**不是服务挂了**。本地请求须绕过代理（`ProxyHandler({})` 或 `curl --noproxy '*'`）
- ⚠️ **写 Windows 批处理（.cmd/.bat/.vbs）一律纯 ASCII 注释**：保存为 UTF-8 会被 cmd.exe 按 GBK 解析，中文乱码并**打断脚本解析**导致整脚本崩。文件名/路径同理不要带中文
- 声卡与移动热点已修复（驱动 / `pnputil /enable-device`）

## ⛔ 代码红线（必须放在提示词开头）

**禁止乱改、乱删、重构无关代码。严格控制修改范围。**

## 💬 沟通偏好

简洁直接、短问句推进；行动导向回复附**状态表格**；继续未完成任务时**先总结进度**再推进；产出**直接写入指定文件夹**；方案用**单字母 A/B/C** 确认，确认前先给优化建议；偏好详细技术解释与本地环境。

## 🤝 浏览器协作方式（闲鱼铺货默认，2026-09-25 确认）

**⚠️ 接口优先（2026-10-02 用户明确要求）：** 凡是能走接口/API 完成的操作，**一律优先用接口，别用 UI 自动化**。

- **背景**：闲管家 / agiso 等后台是 Vue + Element UI，UI 自动化极其脆弱——合成点击受 `isTrusted` 校验拦截、输入框只监听 `keyup.enter` 不认 `keydown`、弹窗取消/X/Esc 合成事件无效、下拉懒渲染需复用已渲染行。一次简单「加档位」要反复绕过这些坑，**投入产出比极差**。
- **因此**：能拿到官方/直连接口（如 kayixin 3.0 API、各平台 OpenAPI、页面内部 RPC）就直接调接口；**只有在确实没有接口、或接口拿不到目标字段时才退而求其次用 UI 自动化**，且 UI 自动化前先评估 ROI。
- **用户自己保持浏览器页面打开**（agiso 编辑页 + qcqcq 货源页 + 源闲鱼页），我通过 **edge-bridge 桥接 RPC** 直接调页面内部接口操作（`GetItemInfo` / `Edit` / `SaveSkuAldsInfo` 等），不依赖用户手动点击。
- 默认**不主动 `tab_new` 开页、不爬 DOM、不重启桥接**（除非标签真的掉了 / 桥接 `127.0.0.1:8787` 无监听）。用户开页 = 标签活跃 + 登录态在 = 接口零等待、不超时。
- 仍须走接口、省不掉的部分：货源成本与参数 key（qcqcq 侧取）、建 SKU / 配自动发货 / 回读校验。
- **最快路径**：用户开 agiso 目标页 + qcqcq 货源页，并给「货源编号 + 变量名 + 档位清单（或源链接）」，我跳过扒源与爬 qcqcq，直接建 + 配 + 校验。

## 🐟 闲鱼铺货运营铁律（一条龙默认规则）

### 🔴 【现行 · 2026-10-12 用户定】货源是「直充」且与所填「类型」一致 → 直接上 SKU，不再逐次确认

- **判据**：志远货源 `getDetail.goodsType==3`（直充）**且** 用户模板「类型」栏填「直充」→ **直接按档位建 SKU**。
- **不再因商品名 / 档位措辞与品类不符而反复追问**（起因：连续多单用户模板沿用「畅骑卡，次数卡」但商品并非单车，AI 每次都要先核对品类再问一次，拖慢上品）。
- 仅两种情况仍需先问一次：①**类型不符**（用户填卡密/单品，但货源不是对应类型）②**档位或货源确实缺失**。

### 🔴 【现行 · 2026-10-15 用户定】货源**只比「志远 + 商战」两家**，互补取低

- 用户原话：「**以后货源只比志远和商战，两个货源互补**」。
- **只在这两家之间比价**：同一商品**逐档比 `salesPrice` 取低者**；某家没有的品类/档位 → 用另一家补位。**不再考虑 省省 / 星芒 / 追梦 / 千城**（取代旧的「志远默认、必要时切省省/星芒/追梦」；**存量已按旧源配好的商品不动**）。
- **志远** = alds 供货商账号 `95425`（主力，余额须充足）；**商战 qqkami** = alds 供货商账号 `96810`。
- **别按品牌整切**：换源仍**逐档**决定，同一商品不同档可以来自不同家（实测讯飞听见：转写1h/2h、畅享包1月商战更便宜，转写5h 志远更便宜）。
- 两家 API 各走自家：志远 `v3_huafei.search()`；商战 `qqkami_search.search_front(kw)`（无搜索 API，走前台页）。`spec.acct` 填对应 alds 账号 ID 即可自动配货。

### 🔴 【现行 · 2026-10-15 用户定】SKU 档位**默认全部添加**（用户原话「sku默认全部添加」）

- **上 SKU 默认把「该商品产品线内的货源全档」全部加上** —— **不必问、不必等用户说「都加」**。标题只写「年卡」也照样铺全周期；**标题随之改宽泛**（覆盖全部周期），否则标题与规格不符。
- **边界 = 不跨产品线**。喜马拉雅实证（1092189305909）：只上「喜马拉雅VIP会员」系列 5天/7天/15天/月卡/2个月/季卡/半年卡/年卡/15个月 = 9 档 + 首单 = 10 档；**不混**儿童会员、白金/升级白金、无用学SVIP、喜点充值、组合包、人工代充、CDK卡密、刷评类。
- **同周期多个货源**（如含「1号1次」限购措辞的版本）→ 取**标准版**（无限购措辞那个），每周期只留一档（规格名不得重复）。
- 🔴 **引流档（首单）只在「已定 SKU 集合内部」取进价最低那档**。
- （**已被取代**的历史口径 · 2026-10-14：档位按标题定、标题限定了周期就只上那个周期 —— 保留备查，不再执行。）

### 🔴 【现行 · 2026-10-12 用户定，优先】默认**必设引流款/首单款**

- **跑一条龙默认自动加一个「首单」SKU**（`deploy.py::resolve_skus` 已内建；`spec["first"]=false` 可整体关闭）。**推翻 2026-10-11 的「默认不加」**。
- **引流价 = 进货价 − 0.30**：亏损**不得超过 0.30**（`_first_price()` 向上取整到分，例：成本 13.013 → 售 **12.72**，亏 0.293）；**无硬下限**（10-12 取消旧 5 元地板）。`ppt=1`（不同步订单金额）。
- 实现：复用**已定 SKU 集合内**最低成本档的 pno（集合外的不算），放 SKU 列表最后，命名 `首单+档位值`（如 `首单30天30次`），spType=6、同参数。
- 🔴 **首单 SKU 库存 = 10**（2026-10-12 用户定）：`deploy.py::FIRST_STOCK=10` 自动生效（首单档=10，其余档=9999）；`_add_first_sku.py --stock` 默认 10；存量批量改 `_set_first_stock.py <gid...> [--go]`。
- ⚠️ 限购一次经 alds 接口设不了（`ppt` 存不进、`GetItemInfo` 无限购字段）；要真限购须走闲鱼 listing 级设置，不在一条龙范围（可写进规格名文案）。

<details><summary>历史口径（2026-10-02 定，已被 10-12 取代，仅备查）</summary>

> 引流款标准 = 用户存量商品（快手币/抖音钻石）实测模式。

- 每个商品跑一条龙**必须**设一个低价引流款（命名「首单」），放在 SKU 列表最后。
- 引流款价格 = **低于成本价**（亏本引流），但**硬下限 5 元**——售价 `≥ 5 元`。
- 即 `引流价 = max(5, 成本×0.88~0.9)`；成本 < 5 元时按 5 元设。
- **命名规范**：规格维度「总量」，规格值 = `首单+面值` + 文案限购，如 `首单50快币`、`60钻石【首单特惠 限购1单】`；**「限购1单」只是规格名文案**（系统限购不存在）。

</details>

### 🔴 一条龙必须包含「登记已付款后发货列表」（2026-10-03 用户定）

- **每个商品跑一条龙，必须把商品登记进阿奇索「发货设置 → 宝贝单独设置 → 已设置-付款后发货」列表。**
- **关键事实：配好 SKU 的 alds 并不会自动出现在该列表里**——实测新商品配完后 `GetGoodsAldsInfo` 仍是空壳（`idNo=0 / createTime=0001-01-01 / defineSku=false`），列表查无此商品。**漏登记 → 买家下单不触发自动发货。**
- 做法两步：① `POST /api/AldsInfo/AddGoods`，**body 必须是裸 JSON 数组** `["<goodsId>"]`（传 `{goodsId:"x"}` 或 `{goodsId:["x"]}` 都报 `[goodsId]Cannot deserialize...IEnumerable<String>`）；② `POST /api/AldsInfo/SaveGoodsAldsInfo`，body = 克隆一个已正常的姊妹商品 `GetGoodsAldsInfo/{goodsId}` 全量记录，只改 `goodsId`+`idNo`，强制 `defineSku=true/autoSend=true/sendTypeOption=28/spType=3/contentTplId=-1`，删掉 `createTime/modifyTime`。
- **验收标准 = 与模板商品做全字段 diff 为 `[]`**（排除 idNo/goodsId/createTime/modifyTime/platformShopId）。
- 列表里的 `hasSku` 显示 false 是**商品侧派生的只读展示位、不是配置项**，商品级 diff 为空即达标，不必纠结。
- 已落地进 `alds-xianyu-sku-pipeline` 技能步骤⑨ + 项目 `一条龙服务说明.md` 第 5 节（六大环节→七大环节）。

### 🔴 一条龙必须包含「标题+详情文案同步」（2026-10-11 用户定）

- **每个商品跑一条龙，默认自动按公式写好标题+详情并同步**（走 deploy 步骤⑪，`Edit` 只改 `title`/`desc`、原 skuId 原样回传 → 不重建 SKU、写回闲鱼前台）。
- 依据 = **该商品现有标题 + 抓取的 SKU 档位**（若是照抄源链接，则用源商品标题+规格）；公式见根目录 `挖卡小铺-文案公式.md`（标题四段式 + 详情五段 + 三段标准条款，含售后录屏）。
- **不必等用户说「按公式」** —— 这是默认动作。用户要保留原文案时会明说「不改文案」。
- 标题 **≤30 字**（超长被平台截断）。⑪ 失败**不阻断**主链路，只告警。

### 🔴 一条龙必须包含「标识为直充」（2026-10-03 用户定）

- **每个商品跑一条龙，必须把商品「标识为直充」**（= 走闲鱼官方直充通道，而非发卡/聊天链接）。
- 页面：宝贝发布/商品列表页工具栏 → 勾选商品 → 「**标识为直充**」（旁为「撤销标识」）。接口 `POST /api/GoodsManage/OpenRecharge`，撤销用 `CloseRecharge`。
- **两个必踩的坑**：① `goodsIds` 必须传**数组** `["<gid>"]`，传 `goodsId:"x"` 报「请选择需要标识为直充的商品」；② **必须带 `rechargeAccountTypes`（充值账号格式数组）**，否则报「充值账号格式至少勾选一个」。
- **验收**：`SearchGoodsList` 里 `item.setting.rechargeOnOff === true` **且** `item.apiRechargeOnOff === true`（后者才代表闲鱼官方直充**真正生效**，界面显示「使用闲鱼官方直充」），`rechargeReason` 应为「直充开通成功」。若 `rechargeOnOff=true` 但 `apiRechargeOnOff=false`，界面会提示「自动取消闲鱼官方直充…将使用聊天窗口发链接直充」= 直充没生效，需排查。
- **卡密类商品（CDK）跳过这一步**——发卡不是账号直充。
- 多数商品在配好直充 SKU alds 后已被系统自动开通，**先查后调**（已 true 就别重复调）。
- 已落地进 `alds-xianyu-sku-pipeline` 技能步骤⑩ + 项目 `一条龙服务说明.md` 第 7 节。

## 📄 产出文件规则（硬性，2026-09-24 用户明确要求）

> **一个会话只允许 1 个文档：`xls`(表格) 或 `md` 二选一。**

- **禁止**在一次会话里堆多个文档 / 多个中间文件（如同时给 N 个 csv + N 个 md）。
- 多个主题的内容 → **合并进同一个文件**（分 sheet / 分章节），不要拆成多个文件。
- 中间产物（探查脚本、原始 JSON 快照等）不算「交付文档」，但**不要主动列举/呈现**；只把**那一个**交付文档给用户。
- 已有历史文件不要删；规则只约束**新产出**。

## 🕳 本机踩坑速查

- **Bash 工具**：`rm` 走 safe-delete 钩子会失败 → 用 Python `os.remove`；本机无 `md5sum`/`strings`/`sleep`
- **PowerShell 工具**返回空输出 → 排查一律走 Bash + `reg query`
- **Bash 沙箱禁用** `wsl`/`msiexec` 等系统工具 → 用 PowerShell 工具跑
- **大文件下载**：PowerShell `Invoke-WebRequest` 会静默截断 → 用 git-bash `curl -sSL` + 国内镜像
- **Go**：git-bash 里 `GOROOT` 必须写 `D:/go`；`build` 报 `Access denied` 先 kill 进程
- **CDP**：Edge 已在运行时必须加独立 `--user-data-dir`，否则端口不生效
- **Edge 同步**：版本需 ≥133
- **Vite**：同步源码绝不带 `.js`（阴影 bug）
- **端口 18082**：后勤站与 card_dist 共用，注意冲突

## 🔌 货源平台 API 凭据（跨项目，2026-10-03/10-06 用户授权入库，仅本地调用用、勿外传）

> 三个货源平台均可 API 直连（接口优先）。密钥已实测可用；任何会话/工作区直接复用，无需重新给。

| 别名 | 基址 | 签名 | 凭据位置 |
|---|---|---|---|
| 星芒 xmang | `https://xmang.cc` | MD5(APPID+secret+Ver+Ts+body) | 🔒 `secrets/credentials.sops.yaml` → `xmang` |
| 省省 ssyq | `http://ssyq.kbb1.cn`（必须 http） | 同星芒(MD5) | 🔒 `secrets/credentials.sops.yaml` → `ssyq` |
| 追梦 sup12 | `https://1.sup12.cn`（卡速售2.0） | **SHA1**(13位ms时间戳+body_json(ASCII升序)+apikey) | 🔒 `secrets/credentials.sops.yaml` → `sup12` |

> 🔒 **真值已抽离并加密存放**（sops + age）。
> 本地解密副本：`~/.config/sops/age/keys.txt` 持有 age 私钥；
> 仓库内只有密文（`ENC[AES256_GCM,...]`），键名与结构明文可读。
> 解密命令：`sops --decrypt secrets/credentials.sops.yaml`

- **星/省省（同源，v3 网关）**：头 `X-APP-ID / X-Version(="1.0") / X-Timestamp(秒) / X-Signature`。接口 `POST /api/v3/...`：`/user/getAccount`(余额)、`/goods/getList`(keyword搜索)、`/goods/getDetail`(按goodsId取成本/限价)。实测余额：星芒≈1051.95、省省≈586.712。
- **追梦（sup12）**：头 `Sign / Timestamp(13位ms) / UserId(=APPID)`。接口 `POST /api/v1/...`：`/user/info`(余额，body `{}`)、`/goods/list`(keyword/cate_id/page/limit)、`/goods/info`(详情，body `{id}`，⚠️ 是 info 非 detail)、`/order/create`、`/order/getDetail`。限频约1请求/秒（退避重试）。实测余额 0.0000。
- 客户端：`edge-bridge/tools/` 下 `sup12_client.py`（SHA1）、`balance_query.py`（省省/星 v3 余额）。
- 品类覆盖：星/省省是卡券库（无话费直充）；追梦有话费券类；话费直充主走 qcqcq（登录态 token，未接 API）。
