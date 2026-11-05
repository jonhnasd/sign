---
tags: [项目, 爬虫, 货源站]
type: 项目笔记
created: 2026-09-23
updated: 2026-09-23
status: legacy
---

# 🕸 项目：88.qcqcq.com 货源站抓取

> [!warning] 状态：历史留档（legacy）
> **本文讲的是接口逆向方法论，仍然有效**（SPA 抓取、参数构造、签名分析）。
> 但文中涉及的**货源平台（星芒 / 省省 / 追梦）已不在现行选源范围** ——
> 现行口径：**货源只比「志远 + 商战」两家，互补取低**（详见 [[身份与记忆/MEMORY]] 闲鱼铺货运营铁律）。
> ⚠️ 别照着本文的货源平台去配货。

## 目标站

`https://88.qcqcq.com/index` —— Vue SPA 虚拟卡券货源商城
站名「票务卡券货源终端 l 联盟」，主体「湖北势不可挡信息咨询有限公司」
卖视频会员、游戏、餐饮代下、演出代拍等虚拟商品。

## 🏷 系统身份：这是「卡易信」建的站

**关键背景**（2026-09-23 查明）：

| 线索 | 含义 |
|---|---|
| `KSSID` cookie | **KSS = 卡易信系统** |
| `_kss_data_`（localStorage） | 卡易信前端状态存储 |
| `kss_site_sys_config_v1`（sessionStorage） | 卡易信站点配置键 |
| `has_kssshop_token` | 卡易信「电商管理」插件的 token |
| `/addons/docking/` | **卡易信的货源对接插件** |

**卡易信** = 山东汇想网络科技旗下虚拟商品商城系统（2012 年起，官网 `kayixin.com`）。
「一次收费终身升级」的自建站系统，站长买系统后自己运营商城，并可对接上游货源。

**这对判断问题至关重要**：
卡易信有**内置的货源对接功能**，站长在**自己站点后台**选货源渠道类型 + 填对接信息即可，
**签名由系统自动处理，不需要站长自己写代码算协议**。

**行业标准的货源对接信息三件套**（参考聚比价模式）：
> 「注册登录进货源方后台，在个人中心查看到 **对接ID、对接秘钥、对接地址**，
> 用于在**卡易信那边输入对接信息**使用；对接方式选择对应的渠道，输入以上信息即可。」

**⇒ 所以「对接不了」多半不是协议/签名写错，而是：**
1. 货源方（qcqcq）侧的**渠道未建立**（需客服开通）
2. 或**对接信息不完整**（只有 APPID+密钥，缺渠道标识/对接方式的正确填法）
3. 或没在**卡易信后台的货源对接入口**正确配置

**参考文档**：
- 卡易信官网：`https://www.kayixin.com/`
- 卡易信对接教程（Apifox）：`https://s.apifox.cn/ba56dbf4-63cc-467e-8278-82e992a19a0a/6881439m0`
- 货源采购 API 文档：`https://pmqj2ys1w6.apifox.cn/`

## 🧩 生态角色：91卡券 / 阿奇索 是什么

> [!important] 这解开了「为什么中间件能对接、手写协议不行」
> **91卡券 ≠ 货源站**，它是**阿奇索（Agiso）旗下的卡券对接中间件**。

**三个角色分清楚**：

| 角色 | 是谁 | 干什么 |
|---|---|---|
| **货源方** | `88.qcqcq.com`（卡易信建站） | 提供商品与 API |
| **中间件** | **91卡券仓库 / 阿奇索**（`agiso.com`） | **内置各家平台的对接协议实现**，负责调 API、算签名 |
| **卖家端** | 闲鱼/拼多多/淘宝/抖店 | 出单后自动向货源方采购发货 |

**91卡券的标准配置流程**（据官方教程）：
1. 拿到货源方的**对接权限**：
   - 卡易信系：**「接口秘钥就是 key，客户编号就是 uid」**，并需在后台**开启接口状态**
   - 卡卡云系：uid + key
2. 登录 91卡券仓库 → **开放服务 → 接口管理 → 导入 `.api` 接口文件**
3. 填入 **用户编号 UID + 接口密钥**
4. 在电商后台配置自动发货接口

**⇒ 核心结论**：
**签名算法是「卡易信对接规范」的一部分，91卡券/阿奇索已经内置实现了。**
用户只需填 UID + key，中间件自动完成签名 → 所以「能对接上」。

而**手写协议**（我在做的）缺少那份规范 → 穷举 60+ 组合也必然失败。

**⇒ 突破口**：
官方教程明确提到要**下载 `.api` 接口文件**（「下载API接口卡券接口.api保存本地备用」）——
**该文件内应包含完整的接口定义与签名规则**。
拿到它（或抓取 91卡券 调用 qcqcq 的实际请求）即可解出正确协议。

**旁证**：qcqcq 的 Chrome `Preferences` 里出现过 `https://www.agiso.com` —— 用户确实在用阿奇索。

**参考**：
- 阿奇索卡券采购接口教程 `https://agiso.com/detail/1171`
- 导入卡券采购接口 `https://agiso.com/detail/1085`
- 91卡券对接教程 `https://www.kancloud.cn/sc668/dsdjjc/3222904`

## 🔑 关键结论：登录态价格更低（约 5%）

> [!warning] 已修正 —— 早前"游客价=登录价"的结论是错的
> 做**接口级对照测试**（同商品、同签名，仅切换 `Authorization` 有无）后确认：
> **登录态返回的价格明显低于游客态，约 5%。**

**对照测试结果（2026-09-23，4 个分类 × 100 条 = 400 条）**

| 商品 | 登录价 | 游客价 | 差额 |
|---|---|---|---|
| 爱奇艺黄金会员 3 个月 | 39.479 | 41.63 | −2.15 |
| 优酷视频 VIP 12 个月 | 92.532 | 97.572 | −5.04 |
| 爱奇艺白金会员 1 个月 | 21.965 | 23.162 | −1.20 |
| 爱奇艺黄金会员 7 天 | 10.187 | 10.741 | −0.55 |

**400 条中 390 条有差异**，`face_value` / `stock_num` / `goods_sales` 完全一致，
**只有 `goods_price` 不同** → 折扣作用在售价上。

折扣率约 **5.2%**（39.479 ÷ 41.63 = 0.948）。

### 为什么之前会判断错
早前只对比了「页面显示价格 vs 抓取字段」，看到 `￥600.00` = `face_value`、`￥70.00` = `goods_price`
就下了结论。**但页面当时是未登录态**，那个价格本身就是游客价 —— 两者一致只证明了
"游客态页面显示 = 游客态接口返回"，**没验证登录态**。

**教训**：判断权限差异必须做**接口级 A/B 对照**（只切换凭证，其他不变），不能看页面。

### 推论
- 抓取拿真实进货价**必须带登录态**，否则价格偏高约 5%
- 站点配置 `login_menu` 三个 `is_login_*` 均为 `false` → 不阻止游客看价，
  但**价格本身按等级返回**，这是两回事

## 🔌 API 对接（开放平台）

### 架构
| 项 | 值 |
|---|---|
| 商城前台 | `88.qcqcq.com` |
| **API 专用域** | **`https://api.qcqcq.com`**（与前台不是同一个域！） |
| API 路径 | `/addons/docking/index/{method}` |
| 可用方法 | **只有 2 个**：`goods`、`notify` |
| 渠道标识 | `/addons/docking/index/goods/docking/{渠道ID}` |
| 技术栈 | **ThinkPHP**（报错泄露 `addons\docking\controller\Index`） |

**探测实证**（无凭据调用）：
```
POST /addons/docking/index/goods           → 401「渠道地址有误」
POST /addons/docking/index/goods/docking/1 → 401「渠道不存在或已关闭」
POST /addons/docking/index/notify          → 400「渠道有误:class not exists: \addons\docking\services\docking\storage\379」
```

### 平台给的对接说明（来自「接口管理」页）
> API对接提示：对接域名 `https://api.qcqcq.com`
> **请先联系客服开通API权限！** 在**安全中心绑定手机号**，然后再在**接口管理重置接口秘钥**即可获取到自己的秘钥以及**添加自己网站服务器 ip 白名单**。
> KSS系统商品通知地址：`http://自己的域名/addons/docking/index/goods/docking/渠道ID`（其他系统需支持此功能）

### 接口配置接口
```
GET  /front/user/income             获取接口配置
POST /front/user/income_save        保存（IP 白名单）
POST /front/user/reset_income_key   重置密钥
GET  /front/user/safe               安全中心
GET  /front/ajcaptcha               滑块验证码（重置密钥时可能触发）
```

### 账号现状（实测 `/front/user/income`）
| 项 | 值 | 状态 |
|---|---|---|
| API 权限 | `has_api: true` | ✅ |
| APPID | `income_app` = `76BrF90I…N5mO` | ✅ 已生成 |
| **IP 白名单** | `income_ip: null` | ❌ **为空** |
| `has_kssshop_token` | `false` | ❌ 未生成 |
| 账户余额 | `0.00` | ⚠️ 影响实际下单 |
| 手机绑定 | 已绑定 | ✅ |

### ⚠️ 对接失败的判断（已被后续联调修正，见下节）
最初怀疑 IP 白名单为空导致。**联调后推翻** —— 白名单在页面上明确标注「（可选）」。

---

## 🧪 API 联调实录（2026-09-23）

### 错误码的含义（关键）
| 返回 | 含义 |
|---|---|
| 401「**渠道地址有误**」 | **缺少 `docking` 参数**（路由未匹配到渠道） |
| 401「**渠道不存在或已关闭**」 | `docking` 有值，但该渠道不存在 |
| 401「**签名验证失败**」 | **渠道存在**，但签名不对 ← 卡在这步 |
| 400「方法 xxx() 未找到」 | 方法名不存在 |

### ✅ 已确认
| 项 | 结论 |
|---|---|
| API 域名 | `https://api.qcqcq.com` |
| 接口路径 | `/addons/docking/index/goods` |
| **渠道参数名** | **`docking`**（放 body JSON） |
| 可用方法 | 仅 `goods`、`notify` |

**参数名怎么找到的**：穷举 `url/address/domain/appid/key/secret/token/channel_id…`
全部返回「渠道地址有误」，**只有 `docking` 返回了不同错误** → 参数名即 `docking`。

### ⭐ 渠道探测
逐个试 `docking` 值，**只有 2 和 10 存在**：
```
docking=1   → 渠道不存在或已关闭
docking=2   → 401 签名验证失败   ⭐ 存在
docking=10  → 401 签名验证失败   ⭐ 存在
```
其余（3~9, 11, 12, 379, 98843, APPID, 手机号, 用户名 `丨`）均「不存在」。

### ❌ 未突破：签名算法
穷举 **40+ 组合**全部「签名验证失败」：
- `md5 / sha1 / hmac-sha256` × `apikey`、`appid+apikey`、`appid+ts+apikey`、`ts+apikey`、`docking+apikey`
- 参数按字典序拼接 + key（`&k=v` 形式）
- 大写 MD5、毫秒时间戳
- header 传法（appid / apikey / sign / token）
- query 传法
- 签名参数名变体（`sign` / `signature` / `sign_str` / `signStr` / `key`）

**判断**：渠道 2 / 10 **很可能不属于本账号**（属其他用户），签名算法与其 apikey 绑定，
用本账号密钥永远签不过。

**⇒ 真正缺失的是「本账号自己的渠道ID」+ 官方签名规则。**

### 📋 接口管理页可配置项（实测表单）
| 字段 | placeholder | 说明 |
|---|---|---|
| 商品通知地址 | `https://your-domain.com/notify` | 平台回调推送地址 |
| 白名单 IP | `例如：1.2.3.4` | textarea，**标注「（可选）」**，支持单 IP / 范围 / CIDR（`192.168.0.0/24`） |
| 验证方式 | 下拉，默认「短信验证」 | sms / trade_password / email |

### 其他账户状态
- 页面显示 API **「已开通」**；`income_order: true`（允许 API 下单）
- 安全中心：已实名 ✓、已绑手机 ✓、已绑微信 ✓、**无交易密码**、安全分 5/8

### 📌 下一步需要的
1. ~~本账号的渠道ID~~ ✅ 已解决，见下节
2. ~~官方签名规则文档~~ ✅ 已解决

---

## ✅ 对接问题已解决（2026-09-23 13:18）

### 🎯 根因：密钥重置后没同步更新

**完整证据链**：

1. `GET /front/user/income` 里 `income_app` 存在，用户后来**重置了密钥**
   （旧 `dcf85a7…` 是 32 位 hex；新 `rMyXI80…` 变成 base62 随机串）
2. qcqcq 接口管理页自己就警告过：
   > **「重置后旧密钥立即失效，请同步更新对接方配置」**
3. 91卡券 里货源账号的创建时间是 `2026-09-20`，存的是**旧密钥**
4. ⇒ 服务端拿旧密钥签名 → qcqcq 返回「签名验证失败」

### 91卡券「货源账号」机制（实测）

**添加/修改货源账号的表单**（`SupplierCode = Standard`，即「标准系统」）：

| 表单字段 | 内部名 | 必填 | 说明 |
|---|---|---|---|
| 货源账号 | `Title` | ✓ | 随便填，仅用于记忆 |
| 选择供货商 | `SupplierCode` | ✓ | 目前只有 `Standard`（标准系统） |
| 用户ID | `UserId` | ✓ | = **货源方 APPID** |
| 用户密钥 | `SecretKey` | 修改时选填 | = **货源方 apikey**（修改时留空表示不改） |
| 接口网关 | `ApiUrl` | ✓ | **结尾不能带 `/`**，正则 `^(http\|https):\/\/([\w.])\S*(?<!/)$` |
| 货源方商品ID | `ProductNo` | ✓ | **新建和修改都要填**，用于测试对接 |

**接口**：
```
POST https://mai.91kami.com/api/SupplierAccount/GetSupplierPlatformSelectOptions
POST https://mai.91kami.com/api/SupplierAccount/GetExtenInfoForm   {"SupplierCode":"Standard","IsCreate":true}
POST https://mai.91kami.com/api/SupplierAccount/Get                {"IdNo":93310}
POST https://mai.91kami.com/api/SupplierAccount/TestPublish
     {"IdNo":93310,"Title":"千城","SupplierCode":"Standard","ProductNo":"40264",
      "extenInfoJson":"{\"UserId\":\"…\",\"SecretKey\":\"…\",\"ApiUrl\":\"https:\/\/api.qcqcq.com\"}"}
POST https://mai.91kami.com/api/SupplierAccount/List                {"page":1,"pageSize":20}
```

### ✅ 解决办法
在 91卡券 → **货源 → 货源账号 → 修改**，把「用户密钥」更新为**新密钥**，
并填上「货源方商品ID」，点「测试并发布」→ `IsSuccess: true`。

**注意**：调货源方 API 的动作发生在 **91卡券 服务端**，浏览器/前端抓不到签名过程。

### 关于签名算法
→ **不需要逆向**。91卡券 的「标准系统」协议已经内置实现了卡易信的对接规范。
用户只需填对 4 个字段，签名由中间件完成。

**这也印证了最初的判断**：手写协议走不通不是算法难，而是**缺规范**；
正确做法是用 91卡券 这类成熟中间件，或向货源方索取对接文档。

## 💰 账户与余额接口

```
GET /front/info → code=200
```
返回账户全貌（示例已脱敏）：

| 字段 | 含义 |
|---|---|
| `id` | 用户 ID |
| `balance` | **账户余额** |
| `commission_money` / `freez_money` | 佣金 / 冻结金额 |
| `level_name` | **会员等级名** |
| `has_vip` / `has_merchant` | 是否 VIP / 商户 |
| `has_api` | **是否有 API 权限** |
| `trade_password_open` / `has_trade_password` | 交易密码状态 |
| `can_up_level` | 可否升级 |
| `roles` / `menus` | 角色 / 可用菜单 |
| `need_bind_mobile` / `need_bind_email` / `need_bind_idcard` | 绑定要求 |
| `mobile` / `email` / `avatar` / `nickname` | 资料（⚠️ 含敏感信息） |

```
GET  /front/user/commission      → 分销：share_link / 佣金 / 下级数
POST /front/member_level/up_config → 等级升级配置（含金额）
POST /front/member_level/up        → 执行升级（需支付方式，⚠️ 会实际扣款）
```

⚠️ **`/front/info` 会返回手机号等敏感信息**，落盘日志需注意脱敏。

### ❓ 能否用 91卡券 查货源方余额？—— 不能

实测结论：**91卡券 没有货源方余额查询功能。**

- 货源菜单下只有：自有货源 / 采购记录 / 充值账号管理 / 采购方案
- 「充值账号管理」实为**充值账号黑名单**（防重复充值），非余额
- 货源账号列表只显示：货源账号 / 平台系统 / 时间 / 操作，**无余额列**
- 试探 10 个候选接口（`SupplierAccount/GetBalance`、`Balance`、`QueryBalance`、
  `GetAccountInfo`、`Suppliers/GetBalance` 等）**全部 404**
- 91卡券 自身只显示**奇豆余额**（计费：「下单接口调用 1 次扣 5 个奇豆」）

**⇒ 查货源方余额请直接查 qcqcq。** 已封装工具：

```bash
python qcqcq/check_balance.py
```
输出账户名、UID、会员等级、**余额**、佣金、冻结金额、下单权限、交易密码状态。

**当前实测**：余额 **¥0.00**、佣金 ¥0.00、冻结 ¥0.00、`has_api=True`、**交易密码未设置**。

## ⚠️ 其他
- `need_balance`（部分商品要求余额 1000/2000/5000 才能买）→ 存在账户等级门槛

## 接口清单（全部需要 `Sign` 头）

| 接口 | 方法 | 用途 |
|---|---|---|
| **`/front/goods/goods_list`** | **GET** | **商品列表（核心）** |
| `/front/diy/goods/index` | POST | 商品详情（批量），body `{"ids":[...],"count":1}` |
| `/front/goods/tags_list` | POST | 标签列表 |
| `/front/diy/category/tree` | POST | 分类树，body `{"level":2,"is_recommend":0}` |
| `/front/diy/category/index` | POST | 分类列表 |
| **`/front/info`** | **GET** | **账户/余额（核心）** |
| `/front/user/commission` | GET | 分销 / 佣金 |
| `/front/member_level/up_config` | POST | 等级升级配置 |
| `/front/member_level/up` | POST | 执行升级（⚠️ 扣款） |
| `/front/notice/index` | GET | 公告 |
| `/front/index/sys_config` `/menu` `/search_key` `/footer` `/open_window` | GET | 站点配置 |
| `/front/kefu/center` | GET | 客服信息 |

**鉴权方式**（两种头必须同时带）：
```
Sign: <32位hash><10位Unix秒级时间戳>     ← 必带，与登录无关
Authorization: Bearer <JWT>              ← 登录后才有，决定价格档位
```

## 🔐 登录协议

### 登录接口清单（静态分析自 `app.js`）
```
/front/login             登录          /front/login_config   登录配置
/front/logout            登出          /front/is_captcha     是否需图形验证码
/front/reg               注册          /front/reg_mobile     手机注册
/front/reg_email         邮箱注册      /front/send_sms  ⚠️   发短信验证码
/front/send_email        发邮箱码      /front/qrlogin        扫码登录
/front/check_qrlogin     查扫码状态    /front/agreement      协议
/front/user/bind_mobile  /front/user/bind_email  /front/user/bind_qrcode
/front/user/certify      /front/user/certifycallback     实名认证
/front/index/getwxgzhqrcode   微信公众号二维码
```
登录方式：**手机验证码 / 密码 / 微信 / 扫码**（从页面与 JS 推断）

### 登录凭据（实测）
| 项 | 值 |
|---|---|
| 存放位置 | `localStorage.token` |
| 形式 | **JWT**，`Authorization: Bearer <token>` |
| 签发/受众 | `iss` / `aud` = `88.qcqcq.com` |
| 载荷 | `auth`（会话指纹）、`jti: {id, type:"user"}` |
| 有效期 | **7 天**（`iat` → `exp`） |
| cookie | 仅 `KSSID` 访客会话，**登录态不落 cookie** |

**获取方式**：`cdp/get_auth.js` 从浏览器 `localStorage` 读（复用 [[经验-踩坑手册]] 的 CDP 套路）。

### API 权限
`/front/info` 返回 `has_api: True` → **该账号具备 API 权限**，
配合 `has_kssshop_token`（当前 False）可能可开通下单 API。

**`goods_list` 参数**
```
sort_type=1&page=N&limit=100&keyword=&pcategory_id=<顶层分类id>&category_id=&gcategory_id=
```
- `limit` 上限 **100**
- **不带 `pcategory_id` 返回空 → 必须按分类遍历**
- 只给**顶层** `pcategory_id` 即可拿到该分类及全部子类商品
- 返回 `{list:[...], total:N}`；`keyword` 可搜索

**商品字段**：`id` `goods_name` `face_value`（面值）`goods_price`（供货价）
`stock_num`（库存）`goods_sales`（销量）`status` `category_ids` `goods_type_text`
`goods_tags` `can_price`（最低加价）`need_balance`（需余额）`can_buy`（可售渠道白名单）`can_no_buy`（禁售渠道）

## 🔐 签名机制

```
Sign: 5459bd7fbcb0505d459648a65d5842e5 1790130813
      └── 32位 hash（随时间变）───────┘└─10位Unix时间戳─┘
```
- 同一页面内**所有请求 Sign 相同** → 与请求体无关，只跟生成时刻有关
- 时间戳 = 页面加载那一刻，可直接换算判断"签名年龄"
- **有效期约 10 分钟**（实测 7 分钟仍有效，12 分钟已失效）
- 逆向算法未找到（不在 `app.js`），疑似服务端下发 → **改用自动刷新**
- 抓法：`cdp/get_sign.js` 开页面，从 `Network.requestWillBeSent` 的 headers 里捞

## 交付物

```
qcqcq/fetch_qcq.py          抓取脚本（python fetch_qcq.py [间隔秒] [最大轮数]）
qcqcq/check_balance.py      查账户余额/等级/交易密码（全自动）
qcqcq/login_guard.py        登录态守卫：查剩余有效期，--open 可直接唤起登录
qcqcq/browser.py            浏览器管理器：自动拉起/复用 headless Edge
qcqcq/data/goods_latest.json/.csv   最新快照
qcqcq/data/snapshots/<时间戳>.json  每轮独立存档
qcqcq/data/changes.log      价格/库存/上下架变动
qcqcq/data/run.log          运行日志
cdp/get_sign.js             签名获取器（走 9222 端口）
cdp/get_auth.js             登录 JWT 读取器
cdp/dump_page.js            页面渲染内容与登录状态检查
```

## 🔁 运行依赖与登录态维护（重要）

### 依赖什么
所有工具都依赖一个**带调试端口的 Edge 实例**（9222），用于取两样东西：
- **Sign** —— 有效期约 **10 分钟**，必须从浏览器实时取
- **JWT** —— 登录态，有效期 **7 天**

### 关键结论：浏览器关掉 ≠ 登录失效
登录态存在**独立 profile 目录**（`cdp/profile`）的 localStorage 里，**落盘持久**。
实测：关掉浏览器 → 自动重启 → token 完好（UID 98843，有效期不变）。
**不需要重新登录，更不需要过验证码。**

### 已实现自动化（不用手动开浏览器）
`qcqcq/browser.py` 提供 `ensure()`：
- 9222 没在跑 → **自动拉起 headless Edge**（不弹窗），0.5 秒就绪
- 复用同一 profile → 登录态自动带上
- `check_balance.py` 已集成，实测「关掉浏览器后直接跑工具」全自动跑通

### ⏰ 唯一需要人工介入的时刻：JWT 到期（每 7 天）
用 `python login_guard.py` 查看剩余天数。

### ⚠️ 实测更正：**密码登录也需要滑块验证**

早前判断「密码登录不用验证码」是**错的**。实测证据：

```
GET  /front/is_captcha   →  {"code":200,"data":{"is_captcha": true}}   ← 全局开关：开
POST /front/login   {}   →  {"code":400,"msg":"请拖动滑块验证"}          ← 明确要求滑块
```

登录表单结构（实测）：
- 两个 tab：**验证码登录** / **账号密码登录**
- 输入框：`请输入账号`、`请输入登录密码`（type=password）
- 另有**微信扫码**入口
- **滑块不在初始视图** → 提交时才弹出（`/front/ajcaptcha?captchaType=blockPuzzle`，即 aj-captcha 滑块组件）

**⇒ 结论：该站 `is_captcha` 全局开启，密码登录同样要过滑块。**

### 但这不影响方案可行性
| 项 | 值 |
|---|---|
| 登录态有效期 | **7 天** |
| 需要人工操作的频率 | **每 7 天一次** |
| 操作内容 | 拖一下滑块（或扫码） |

**每 7 天手动过一次滑块，是这套方案的天花板，也是合理边界。**

**不做验证码识别/破解** —— 属于平台安全机制，只走「人工登录一次 → 长期复用」路线。
若要「无人值守自动登录」，必须识别滑块，本项目不做。

## 数据规模（2026-09-23）

- 商品总数 **13,697**
- 单轮耗时约 **112 秒**（34 个顶层分类，limit=100 分页）
- 轮询间隔 300 秒
- 价格中位数 **3.05**，区间 0.022 ~ 1054271（有面值 999999 的测试商品，属异常值）
- 分类规模：封面系列 8277、餐饮代下 2634、影视会员 293、商务办公 291 …

## 🛒 SKU 上架表生成（闲鱼）

脚本：`qcqcq/make_sku.py`
```bash
python make_sku.py --markup 10 --threshold 10 --below fixed:0.5 --out data/sku.csv
```

### 「限价」字段（`can_price`）的真实语义
商品名里直接写着，**限价 = 最低销售价约束**：
```
#29580 青桔电单车骑行卡6个月…丨限价289-支持回收   goods_price=289  can_price=289
#29583 青桔电单车骑行卡1个月…丨限价55.8-支持回收  goods_price=55.8 can_price=55.8
```

**分布（13697 个里只有 57 个有限价，0.42%）**：
| 关系 | 数量 |
|---|---|
| 限价 == 供货价 | 39 |
| 限价 > 供货价 | **0** |
| 限价 < 供货价 | 18 |

**三类脏数据必须排除**：
- `【纪念展示】001-011` × 11 个 → 限价=供货价=**9999**，占位展示品
- `酒店代订` × 18 个 → 供货价 3.0 但**限价仅 1.0**（低于成本，疑似设置错误）
- `【代理分成】仅供内部使用` → 内部品

**⚠️ 重要结论**：因为「限价 ≤ 供货价」恒成立，`售价 = max(按规则算的价, 限价)` 的结果是
**限价永远不会生效** —— 加价后的价格天然高于限价。实测「限价生效 0 个」。

### ⚠️ 价格分布 —— 定价门槛必须重新考虑
```
供货价 <  3 元 :  6550 个  ( 47.8%)
供货价 <  5 元 :  8545 个  ( 62.4%)
供货价 < 10 元 :  9004 个  ( 65.7%)   ← 中位数仅 3.05 元
供货价 < 50 元 : 12575 个  ( 91.8%)
中位数 3.05
```

**若「10 元以上 +10%、10 元以下不加」，则 8916 个商品零利润（65%）。**

### 四方案实测对比
| 方案 | 门槛以下 | 零利润 | 中位售价 | 单件利润均值 |
|---|---|---|---|---|
| B | 不加 | **8916 个** ❌ | 3.05 | 2.47 |
| C | 同样 +10% | 3 个 | 3.36 | 2.61 |
| **D** | **+0.5 元** | **0 个** ✅ | 3.55 | 2.80 |
| E | +1 元 | **0 个** ✅ | 4.05 | 3.13 |

**推荐 D**（门槛以下 +0.5 元）：零亏本，低价品也有利润。

### SKU 规格提取（`--sku-name spec`，默认）
SKU 名称 = **买家要选的规格**（`1个月` / `3个月` / `12个月`），不是时间戳。

**分层提取规则**（`extract_spec()`，命中率 100%）：

| 优先级 | 匹配对象 | 示例 | 占比 |
|---|---|---|---|
| ① | 时长 | `1个月` `3个月` `12个月` `7天` | 11.5% |
| ② | 卡类型 | `月卡` `季卡` `年卡` `终身卡` | 1.1% |
| ③ | 面额 | `500元` `20元券` `10K币` | 3.1% |
| ④ | 款式（`『』`内 或 `丨` 后） | `萌宠圣诞树` `金龙飞天/long` | 16.0% |
| ⑤ | 商品名兜底 | `通兑中杯` `随心配1+1` | 68.4% |

**⚠️ 三个踩过的坑（务必保留这些规则）**：

1. **「小时」不能进时长词** —— 商品名里 `24小时全天秒单`、`质保时间1小时` 是**营销语/质保语**，不是规格。
   误判量：`24小时` ×1024、`1小时` ×56。
   ⇒ 仅当商品名含 `加速器/时长/包时/计时` 时才认「小时」。

2. **「永久/终身」必须用括号包裹才算** —— 否则红包封面的 `新款永久微信红包封面…` 会被误判为"永久会员"。
   误判量：**6093 个**（全站最大误判源）。
   ⇒ `RE_CARD_WEAK = [『「](终身|永久)[』」]`，且必须写在 `_match_spec` 里 `RE_CARD` 之后。

3. **`『』` 括号内容优先级最高，且要分"规格"与"款式"两用** ——
   - 括号内能匹配到规格 → 直接用（`『20元』`→`20元`）
   - 匹配不到 → 记为**款式候选**（`『金龙飞天/long』`→款式）
   - 若都不做，会退到 `丨` 分割，把 `24小时自助提卡！` 这种营销段当成规格（误判 996 个）

**营销语黑名单** `RE_MKT`：`到账|秒单|自助|提卡|直充|兑换|发货|卡密|立即|快速|全天|小时|工作日|下单|倍数|起充|自动|福利|官方|封面`
用于 ④⑤ 两步过滤，避免把 `24小时自助提卡！`、`微信红包封面` 当规格。

**列结构**：
```
SKU规格 | SKU编码 | 货源ID | 商品名称 | 货源分类 | 商品类型 | 供货价 | 限价 | 上架售价 |
单件利润 | 利润率% | 库存 | 销量 | 面值 | 限价生效 | 货源商品编号
```
- `SKU规格` = 提取出的规格（同上表）
- `SKU编码` = `时间戳-4位序号`（如 `20260923215823-0001`），**全局唯一**，做内部标识
- 已排除 24 个（22 个价格异常 + 1 内部品 + 1 无库存）
- 供货价**保留 3 位原始精度**（如 `26.545`），售价固定 **2 位**
- 输出 `data/sku_*.csv`（utf-8-sig，Excel 直接打开）

### SKU 名称演变（用户需求修正过程）
1. 最初用「时间戳」→ 用户说"sku的名字一般是时间"（我理解成时间戳）
2. 用户澄清：**"sku一般为1个月，三个月这样的"** ⇒ 是**规格**，不是时间戳
3. ⇒ 时间戳降级为 `SKU编码`（唯一标识），`SKU规格` 改为规格提取

### 待用户确认
1. **10 元门槛以下的定价方式**（推荐 +0.5 元）
2. **闲鱼上传模板的列名** —— 目前用的是通用列名

## 🔎 搜索 / 商品详情接口（2026-09-24 实测补抓）

> 完整版：`WorkBuddy\2026-09-22-11-37-41\qcqcq\API-搜索与商品接口.md`
> 抓法：桥接连**已登录浏览器** → `net_install` → **页内路由 `$router.push()`** 触发（整页导航会让钩子失效）

### ① 搜索接口

```
GET /front/goods/goods_list?sort_type=1&sort=&page=1&limit=12&keyword=<词>&pcategory_id=&category_id=&gcategory_id=
```
响应 `{code,msg,data:{list:[29字段], total}}`；卡片关键字段
`id / goods_name / face_value / goods_price / stock_num / goods_sales / spec_type / can_buy / need_balance / can_price / status`。

### ② 商品获取接口

```
GET /front/goods/detail?id=<商品id>&sku_id=      # 单规格 sku_id 留空
```
响应 `data:{goods(52字段), goods_sku, merchant, goods_spec_key, goods_spec_value, …}`。

⭐ **`data.goods.attach` = 下单参数定义**，如
`[{"type":"text","name":"手机号","key":"recharge_account","vali":"mobile","tip":"请输入手机号"}]`
—— 这就是「这个商品下单要填什么」。抖音/快手类会换成对应账号字段。

### ⚠️ 纠正旧结论

| 旧说法 | 更正 |
|---|---|
| 「不带 `pcategory_id` 就返回空，必须按分类遍历」 | **带 `keyword` 可单独搜索**，`pcategory_id` 留空也有结果 |
| 「商品详情 = POST `/front/diy/goods/index`」 | 详情页实为 **GET `/front/goods/detail`**（`diy/goods/index` 是首页装修批量用） |
| 该站多规格商品很多 | 实测**绝大多数单规格** `spec_type=0` |
| 未登录也能取价 | **登录价更低**（实测 `40658`：匿名 0.255 → 登录 0.242，≈ −5%） |

## ⭐ 重大关联：阿奇索「货源商品编号」== qcqcq「商品 id」

**证据**：阿奇索里抖币 SKU 的 `supplierProductNo` = **38430 / 42959**，
而 qcqcq 上 id **38430** =「抖音抖币（钻石）1元丨下单范围6-5000」、id **42959** =「…范围1-5000」；
倍数也吻合（38430 那批 mult=钻石/10；60钻石 mult6 用范围从 1 起的 42959）。
⇒ **阿奇索的货源上游就是 qcqcq（或同 id 镜像）**，编号可**直接平移**。

**用法**：要在阿奇索配某商品 → 先来 qcqcq 搜同名货源 → 把它的 `id` 填进阿奇索「货源商品编号」。

**biubiu加速器档位 → 货源编号**

| 档位 | 全平台通用 | 仅手游 |
|---|---|---|
| 1天 | 40653 (面值1.00 / 供货0.246) | 40658 (0.31 / 0.242) |
| 3天 | 40652 (3.90 / 2.778) | — |
| 7天 | 40651 (5.90 / 4.192) | 40657 (3.00 / 1.675) |
| 1个月 | **40650 (20.00 / 17.685)** | 40656 (8.00 / 4.733) |
| 3个月 | 40649 (60.00 / 48.763) | 40655 (18.00 / 12.733) |
| 6个月 | 40648 (94.13 / 91.148) | — |
| 12个月 | 40647 (240.00 / 168.852) | 40654 (80.00 / 46.638) |

> biubiu 是「直冲你号」：货源参数 `attach` 要**手机号**（`key=recharge_account`，`vali=mobile`）。

### ⭐ biubiu 在阿奇索侧的落法（2026-09-24 实测）

- 阿奇索 `attach[].name` = **`recharge_account`**（服务端自动纠正，不是你填的 `lblName1`）
  ⇒ `supplierParamJson` 的 key 要跟着对齐成 `recharge_account`
- 参数值填 **`{$充值账号}`**；**发送倍数恒为 1**（货源商品本身就是整份时长卡）
- 全平台通用 → 40647/40649/40650/40651；仅手游（= 闲鱼上常写作「手游免广告」）→ 40654/40655/40656/40657
- 实测实例：闲鱼宝贝 `1084793623900` 已按 2 维度 × 4 档 = 8 SKU 配通（见 [[操作-阿奇索宝贝SKU设置]] §13）

## 🔗 相关

- [[经验-踩坑手册]]（CDP / 签名部分）
- [[长期记忆]]
