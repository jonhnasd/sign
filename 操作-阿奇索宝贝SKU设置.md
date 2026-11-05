# 操作 · 阿奇索宝贝 SKU 规格与价格

> 阿奇索·闲鱼自动发货后台（`aldsidle.agiso.com`）给宝贝加规格、改价格的完整路径。
> 2026-09-24 实测于宝贝「抖音直播抖币充值」，用 [[项目-edge-bridge]] 的浏览器桥接自动完成。

## 一、概念：SKU 规格分两层

```
价格库存（宝贝发布/编辑页）
├─ 宝贝规格  →  定义"买家能选什么"     ← 规格维度 + 规格值
└─ 销售规格  →  每个规格的售价/库存/商品编码  ← 这才是 SKU
```

| 层 | 作用 | 上限 |
|---|---|---|
| 宝贝规格 | 规格维度（如"颜色""尺码""总量"） | **最多 2 个维度** |
| 销售规格 | 每个规格组合的价格库存 | 值数量不限 |

## 二、加规格值

```
价格库存 → 宝贝规格 [编辑] → 弹窗「设置宝贝规格」
  ├─ [+ 新增总量]     → 加规格值（个数不限）
  ├─ [+ 添加多规格]    → 加第 2 个规格维度（硬上限 2 个）
  ├─ 标签可拖动排序，右侧 × 删除
  └─ [确定]           ← 确定后销售规格表格才生成对应行
```

## 三、改价格

**方式 1 · 逐行改**：销售规格表格里每行直接改「销售价」

**方式 2 · 批量设置**：
```
[范围下拉(全部/指定规格)] + [售价(元)] [库存(件)] [商品编码] → [批量设置]
```

**最后必须点页面底部「保存」** —— 不点保存前面全白做。

## 四、⚠️ 商品编码（最容易漏）

`商品编码` 是**自动发货时匹配卡券的钥匙**，阿奇索靠它去 `91卡券仓库` 找对应卡券。
**留空可能导致买家下单后匹配不上、发不出货。**

## 五、⚠️ 表格是虚拟渲染（自动化操作的关键坑）

销售规格表格**只把当前"渲染窗口"内的约 9~10 行放进 DOM**，其余行不存在。

- 症状：读到的规格行会"变"——先读到 `60,10,100…1200`，换个滚动位置变成 `200…3000`
- 排查失败的方法：设容器 `scrollTop=0`、CDP `Input.synthesizeScrollGesture`、
  `Input.dispatchMouseEvent(mouseWheel)` —— 都**改变不了渲染窗口**
- ✅ 有效方法：改变**页面滚动位置**（`window.scrollTo`）切换渲染窗口，分批读取/写入
- 从表格顶部区域开始操作，避免"前面几行被滚出去读不到"

## 六、DOM 定位技巧

按**规格名**定位行，比按坐标稳：

```js
// 1. 找「销售规格」label 的 form-item 作为范围
// 2. 在范围内找 innerText 恰好等于规格名的叶子节点
// 3. 从该叶子向上找第一个包含 >=2 个 input 的祖先 = 行容器
// 4. inputs[0]=售价, inputs[1]=库存, inputs[2]=商品编码
```

填值必须用 **native setter + 派发事件**（React 受控组件）：

```js
var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
setter.call(el, value);
el.dispatchEvent(new Event('input', {bubbles:true}));
el.dispatchEvent(new Event('change', {bubbles:true}));
```

弹窗里「新增总量」的提交方式是**派发 Enter**：

```js
['keydown','keypress','keyup'].forEach(function(tp){
  el.dispatchEvent(new KeyboardEvent(tp, {key:'Enter', code:'Enter', keyCode:13, which:13,
                                          bubbles:true, cancelable:true}));
});
```

## 七、配置「内容方式」（发货设置弹窗）

`商品设置页(/#/alds/goods)` → 商品行「修改」→ 弹窗「销售规格」→ 单选项**按SKU分别设置**
→ SKU 行「修改」→ 展开 **SKU 发货设置**面板。

### 7.1 内容方式有 4 种（不止"货源"）

面板区块顺序：`订单状态 → 发货方式 → 内容模板 → 内容方式 → [类型专属字段] → 提示信息 → 发送倍数 → 更多设置`

| 界面文本 | `spType` | 需要的额外字段 |
|---|---|---|
| **单卡种** | `1` | 卡种（`CardpwdKindList`） |
| **发卡方案** | `2` | 发卡方案（`GetSupplierPlanList`） |
| **无卡** | `3` | 无（只发提示信息） |
| **货源** | `6` | 货源账号 + 关联商品 + 货源方参数 |
| （接口） | `4` / `5` | 已下线 |

### 7.2 配货源步骤

```
1. 内容方式 → 货源
2. 货源账号 → 选（GetSupplierAccounts）
3. 关联商品 → 填货源商品编号 → 搜索（GetSupplierProductList）→ 点选结果
4. 货源方参数（如「抖音ID」）→ 点右侧「充值账号」按钮 → 自动插入 {$充值账号}
5. 平台售价 → 选（默认 2=同步订单金额）
6. 发送倍数
7. 保存
```

### 7.3 发送倍数 3 种模式（互斥）

| 模式 | 字段 | 含义 |
|---|---|---|
| 发送倍数 | `multiple: N` | 买 1 份发 N 组 |
| 固定发一 | `onlySendOne: true` | 一律只发 1 组 |
| 忽略用户下单数量 | 同 `onlySendOne` | 效果同上 |

> 勾选后两者时后端强制 `multiple = 1`。

**本地实例规则**：`发送倍数 = 钻石数 ÷ 10`（1元=10钻石）

## 八、核心字段与接口（脚本猫开发用）

### 8.1 配置字段（GetSkuAldsInfo / SaveSkuAldsInfo）

> 🔴 **参数值改一处不生效（2026-09-24 实测）**：货源参数值（如「充值账号」变量）
> 在 `supplierParamJson` **和** `attach[].value` **两处同时存在**。
> `SaveSkuAldsInfo` **以 `attach` 为准重建 `supplierParamJson`** ——
> 只改 `supplierParamJson` 会「**返回 isSuccess:true 但值不变**」。
> **改参数值必须两处都改**。`attach` 元素 GET 时不带 `type`/`required`，
> 真实保存请求带 `type:1,required:true`，回写补上更稳。
>
> 🔴 **补充（2026-09-24，见 §13.2）：`name`（key）也要对齐。**
> `attach[].name` 会被服务端**自动纠正成货源方真实字段名**（biubiu = `recharge_account`），
> 而 `supplierParamJson` 的 key 保留你传的旧值 ⇒ 必须**回读真实 name 后再对齐一次**。

#### 完整字段总表（51 字段，源码提取）

```jsonc
{
  // ── 标识 ──
  "goodsId": "1086634177063",
  "skuId": "6140547672602",
  "specName": "总量:1200钻石;",
  "idNo": 9495982,                       // 配置记录 ID（新建必须置 0）
  "platformShopId": "2223107388411",
  "outerSkuId": "",

  // ── 内容方式 ──
  "spType": 6,                           // 1单卡种 2发卡方案 3无卡 6货源
  "spId": 0,                             // 卡种ID / 发卡方案ID（视 spType 而定）
  "productType": 1,
  "apiType": 2,

  // ── 发货方式（布尔字段是真源，sendTypeOption 是位掩码合成） ──
  "enableSendBySms": false,
  "enableSendByEmail": false,
  "enableSendByTiqu": true,              // 提取
  "enableSendByIm": true,                // 闲鱼消息
  "enableSendByDummy": true,             // 虚拟发货（界面不显示）
  "enableSendByCoupons": false,
  "enableManualSendLaterSendCpd": false,
  "sendTypeOption": 28,                  // = 4+8+16，只读展示用

  // ── 订单状态 ──
  "autoSend": true,                      // true=自动更新发货状态；false=手工发货后再发卡密
  "waitConfirmSendCardPwd": false,
  "waitConfirmSendCardPwdText": "",
  "delayDummy": false,
  "delayMinutes": 0,

  // ── 内容模板 ──
  "contentTplId": -1,                    // -1 = 使用随机模板

  // ── 货源（spType=6 时有效） ──
  "supplierAccountId": 93310,            // 货源账号 ID
  "supplierProductNo": "38430",          // 货源商品编号
  "supplierParamJson": "{\"lblName1\":\"{$充值账号}\"}",   // 参数键值对
  "attach": [                            // 参数定义（来自货源商品模板）
    {"name":"lblName1","title":"抖音ID","desc":"请填写抖音ID，不要填手机号","value":"{$充值账号}"}
  ],
  "isShowPlatformPrice": true,
  "disableSendSalePriceToSupplier": false,

  // ── 平台售价 ──
  "platformPriceType": 2,
  "fixedPrice": 0.0,

  // ── 发送倍数 ──
  "multiple": 120.0,                     // 发送倍数
  "onlySendOne": false,                  // 固定发一 / 忽略下单数量

  // ── 自动改价 ──
  "autoChangePrice": false,
  "autoChangePriceSetting": {"decimalHandling": 0},

  // ── 售后 / 通知 ──
  "notifySupplierCancelType": 0,
  "enableNotifySupplierCancelUseSelf": false,
  "allowSupplierAgreeRefund": false,
  "allowSupplierRefuseRefund": false,
  "ignoreCancelRefundAmountOrCost": false,
  "enablePurchaseFailedAuthOffUseSelf": false,
  "directRechargeTipInfo": "",
  "enableThirdPartyCoupon": false,
  "defineCpdShowTpl": false,
  "cpdShowSetting": "",
  "additional": "",
  "option1": 0,
  "isCommonAldsInfo": false
}
```

#### 表单提交默认值（源码提取，供对照）

```js
{
  contentTplId: -1, autoSend: true, goodsType: 0,
  enableSendByDummy: true, enableSendBySms: false,
  enableSendByTiqu: false, enableSendByIm: false, enableSendByCoupons: false,
  spType: 3,                       // 默认「无卡」
  platformPriceType: 0, fixedPrice: 0,
  multiple: 1, onlySendOne: false,
  allowMinBuyCount: 1, allowMaxBuyCount: 9999
}
```

### 8.2 关键接口（脚本猫开发用）

**请求头**：`x_front: 1`、`X-Requested-With: XMLHttpRequest`、`Authorization: Bearer {token}`
（脚本猫在页面上下文跑 `fetch` 会自动带上 token，无需自己管）

#### 8.2.1 阿奇索发货配置（`/api/AldsInfo/`）

| 方法 | 路径 | 用途 | 状态 |
|---|---|---|---|
| GET | `/GetSkuAldsInfo/{goodsId}/{skuId}` | 读 SKU 配置 | ✅ |
| GET | `/GetAldsSkuList/{goodsId}` | 读该商品 SKU 列表（**删除后交叉验证用**） | ✅ |
| POST | `/SaveSkuAldsInfo` | **存 SKU 配置**（发货/货源，全量） | ✅ 实测 |
| POST | `/BatchSaveSkuAldsInfo` | 批量存（body 为数组） | 可用 |
| POST | `/CopySkuAldsInfo` | 复制配置到其他 SKU | 可用 |
| POST | `/DeleteSkuAldsInfo/{goodsId}` | **删除 SKU 配置（含孤儿）**：body 为 **skuId 字符串数组** `["6141289720709"]`；路径只放 goodsId，带 idNo 会报「自动发货设置不存在」 | ✅ 实测 |
| POST | `/UpdateSkuAutoSend` | 开关该 SKU 自动发货 | 可用 |
| GET | `/GetAldsGoodsInfo/{goodsId}` | 商品级配置/权限 | 可用 |
| GET | `/GetGoodsAldsInfo/{goodsId}` | 商品级配置 | 可用 |
| POST | `/SaveGoodsAldsInfo` | 保存商品级配置 | 可用 |
| POST | `/BatchSaveGoodsAldsInfo` | 批量保存商品级配置 | 可用 |
| POST | `/LoadAldsGoodsList` | 商品配置列表 | 可用 |
| POST | `/SaveGoodsAldsChangePrice` | 保存改价 | 可用 |
| POST | `/SyncGoods` | 从闲鱼同步商品 | 可用 |
| POST | `/SearchGoodsByApi` | 按接口搜索商品 | 可用 |

#### 8.2.2 货源服务（`/api/AcprSerivces/`）

| 方法 | 路径 | 用途 | 状态 |
|---|---|---|---|
| POST | `GetSupplierAccounts` | 货源账号列表 → `[{val:93310,text:"千城"}]` | ✅ |
| POST | `GetSupplierProductList` | **货源商品搜索**（编号/标题） | ✅ |
| POST | `GetLocalSupplierTemplate` | 货源商品模板（含 `attach` 参数定义、成本价） | ✅ |
| POST | `GetSupplierDetail` | 货源详情（能力位） | 可用 |
| POST | `GetSupplierCommonParamList` | 货源通用参数（如「充值账号」） | 可用 |
| POST | `GetPlatformPriceTypeList` | 平台售价类型列表（5 项） | 可用 |
| POST | `GetSupplierPlanList` | 发卡方案列表 | 可用 |
| POST | `SendCardPlanList` | 发卡方案列表（另一入口） | 可用 |
| POST | `CardpwdKindList` | **卡种列表**（spType=1 时用） | 可用 |
| POST | `GetSupplierTemplate` | 货源模板 | 可用 |
| POST | `GetAldsOuterApi` / `AldsOuterApiList` | 自定义接口（已下线） | — |

#### 8.2.3 商品管理（`/api/GoodsManage/`）—— ✅ 已实测

> **全部 POST**，body 为 JSON。

| 方法 | 路径 | 用途 | 状态 |
|---|---|---|---|
| POST | **`GetItemInfo`** | **商品详情（含 `itemSkuList` + `saleProperties`，首选读取入口）** | ✅ 实测 |
| POST | `GetGoodsPrices` | 读 SKU 价格库存 | ✅ 实测 |
| POST | **`Edit`** | **保存商品（规格/价格/库存/编码）** | ✅ 实测（幂等） |
| POST | `GetSpec` | 读取宝贝规格 | ❌ 404 |
| POST | `UpdateGoodsPrice` | 改价（独立接口） | 未验证，用 `Edit` 即可 |
| POST | `AddQuantity` | 加数量/规格 | 未验证 |
| POST | `SearchGoodsList` | 商品列表 `{pageSize,page,categoryId,status}` | ✅ 实测 |
| POST | `Publish`/`InsertDraft`/`UpdateDraft`/`PublishDraft`/`DeleteDraft` | 发布/草稿流 | 未验证 |
| POST | `GetItemBizTypeList`/`GetStuffStatus`/`GetDivision`/`GetHistoryDivision` | 表单选项 | ✅ 实测 |
| POST | `GetVirtualSpBizTypeList` | 虚拟业务类型（直播币=25） | ✅ 实测 |
| POST | `GetCategory`/`GetNewCategoryList`/`GetLocalCategoryIdList` | 分类 | 未验证 |

#### 8.2.4 其他

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/SendContentTpl/GetContentTplSelectOption` | **内容模板列表** |
| POST | `/api/AldsSetting/GetAldsSetting` | 全局发货设置 |
| POST | `/api/AldsSetting/SaveAldsSetting` | 保存全局设置 |
| GET | `/api/Common/LoadToken` | 加载 token |
| GET | `/api/Common/ImageCaptcha` | 图形验证码 |

### 8.3 枚举字典（源码提取，非猜测）

```js
// 内容方式
spType:           单卡种=1 发卡方案=2 无卡=3 接口=4 接口方案=5 货源=6
// 发货方式位掩码（sendTypeOption）：实测 28 = 4+8+16
SendType:         Email=1 SMS=2 提取=4 闲鱼消息=8 虚拟发货=16 卡券=32 手工后发券=64
// 货源类型（内部）
SupplierType:     None=0 OuterApi=1 Supplier=2 CardKindPurchase=3
// 配置作用域
SendSettingType:  Unknown=0 Global=1 Goods=2 Sku=3 AllPlatform=4
// 编辑类型
EditType:         editGoods=1 editSku=2
// 平台售价 platformPriceType（来源 GetPlatformPriceTypeList）
1=不同步销售单金额 2=同步订单金额 3=同步买家实付 4=同步商品单价 5=指定金额(配合 fixedPrice)
```

### 8.4 脚本猫 / UI 自动化坑（仅当必须走 UI 时参考）

> 本手册主推**纯接口方案**（§九起），以下坑只在退而用 UI 自动化时才会踩。

| 坑 | 现象 | 解法 |
|---|---|---|
| **虚拟渲染** | 销售规格表格 DOM 只约 9~10 行，其余不存在；设 `scrollTop` 不生效 | 改变**页面滚动位置**切换渲染窗口，分段处理；或直接走接口 |
| **两处分页** | `querySelector('.ant-pagination')` 取到外层商品列表分页 | 限定在目标 `.ant-modal` 内查询 |
| **按钮全角空格** | 「取 消」「保 存」`innerText.trim()==='取消'` 匹配失败 | 比较前 `replace(/\s+/g,'')` |
| **按钮式单选** | 内容方式不是 `.ant-radio-wrapper` | 用 `.ant-radio-button-wrapper` |
| **受控输入框** | 直接改 `.value` 不生效 | 原生 setter + 派发 `input`/`change` |
| **新增规格需回车** | 填值不回车不加入标签列表 | 派发 `keydown({key:'Enter'})` |
| **弹窗内层/外层** | 两个 `.ant-modal` 嵌套 | 用「含关键字 + 取 height 最大」区分 |
| **直接开编辑页报错** | `tab_new` 打开 goodsRelease 报「获取分类信息失败」 | 从商品列表正常点击进入 |
| **裸 fetch 返回 401** | 不带鉴权头 | 加 `Authorization: Bearer ` + `localStorage.getItem('TOKEN')` |
| **hook `window.fetch` 抓不到** | 抓到 0 条 | **axios 走 XHR**，hook `XMLHttpRequest.prototype.open/send` |
| **CDP `Runtime.evaluate` 拿不到 Promise** | 返回 `null` | 必须 `awaitPromise:true`（bridge 自带 `eval` 不行） |
| 🔴 **回读仍看到旧值** | GET `GetSkuAldsInfo` **服务端缓存**，`cache:'no-store'`+`?t=` 破不掉 | 删除/改值后想确认，改用 `GetAldsSkuList/{goodsId}` 返回全部配置 skuId 列表交叉验证，**别信即时回读** |

### 8.5 三条硬规则

1. **先读后写**：`GetSkuAldsInfo` → 只改目标字段 → `SaveSkuAldsInfo`。**不要拼全新 body**，否则覆盖掉用户的其它设置。
2. **跳过已配置**：已是目标值就不写（快且安全）。
3. **保存后回读校验**（⚠️ 注意 §8.4 服务端缓存坑，必要时用 `GetAldsSkuList` 交叉验证）。

## 九、⭐ 加 SKU / 改价格 —— 纯接口方案（已验证）

> 2026-09-24 实测：**不用碰页面 UI**，三步搞定。

### 9.1 三步配方

```js
// ① 读：一个接口拿全（29 字段，含规格与 SKU）
POST /api/GoodsManage/GetItemInfo
body: { goodsId, draft:false, virtualGameGoods:false }
→ data.data 里已有 saleProperties（规格值）+ itemSkuList（价格/库存/编码）

// ② 改
saleProperties[0].values          ← 规格值列表（决定有哪些 SKU）
itemSkuList[i].price / .quantity / .outerId

// ③ 写
POST /api/GoodsManage/Edit   body = 整份 payload
→ {"statusCode":200,"data":{"isSuccess":true,"code":0}}
```

### 9.2 payload 需要补 2 个字段

`GetItemInfo` 返回 **29** 个，`Edit` 要 **31** 个：

| 字段 | 示例 | 来源 |
|---|---|---|
| `spBizType` | `25` | `GetVirtualSpBizTypeList` → `["25","22","23","20"]` |
| `categoryName` | `"卡券/卡券充值/虚拟币/直播币"` | 记一次，按类目复用 |

### 9.3 skuId 规则（源码确认）

```js
ne = ou.current++                 // 新 SKU：skuId = 自增序号（0,1,2…）
Cu && (ne = Cu.skuId || ne)       // 已有 SKU：沿用原 skuId
// 匹配键 = propertyList 按 "规格名:规格值" 排序后 join('|')
```

- **改已有 SKU** → 必须沿用原 skuId（按 `规格名:规格值` 匹配，**不是按顺序**）
- **新增 SKU** → skuId 随便给（别与已有冲突），平台保存时重新分配

### 9.4 实测记录

| 测试 | 做法 | 结果 |
|---|---|---|
| 抓真实 body | hook `XMLHttpRequest` + 点「保存」 | 拿到 3521 字节完整请求体 |
| no-op 保存 | 不改任何东西点保存 | 「保存成功」，**读回逐字段完全一致** |
| 纯接口保存 | `GetItemInfo` + 2 字段 → `Edit` | `isSuccess:true`，**读回完全一致** |

**⇒ `Edit` 幂等可靠，全接口链路可用。**

### 9.5 两个硬要求

1. **`saleProperties` 与 `itemSkuList` 必须同时改** —— 页面逻辑是**由 `saleProperties` 重建 `itemSkuList`**。
2. **`Edit` 是整份提交，不是增量** —— 必须先读全量、只改目标字段、整体回写；**自己拼新 body 会丢字段**。

### 9.6 抓请求体的三个坑

| 坑 | 解法 |
|---|---|
| hook `window.fetch` 抓到 0 条 | **axios 走 XHR** → hook `XMLHttpRequest.prototype.open/send` |
| 裸 fetch 返回 401 | 加 `Authorization: Bearer ` + `localStorage.getItem('TOKEN')` |
| CDP 拿不到 Promise 结果 | 必须带 `awaitPromise: true`（bridge 自带 `eval` 不行） |

## 十、⭐ 批量改 SKU 货源参数值 —— 纯接口（已验证）

场景：把某商品**所有 SKU** 的货源参数值（如「充值账号」变量）统一改成另一个值。

**配方**：逐 SKU `GetSkuAldsInfo` → 改 `supplierParamJson.mobile` **和** `attach[].value` → `SaveSkuAldsInfo`。

> 实测（2026-09-24）：商品 `1086681905342`（虎牙直播币自动充值）11 个 SKU，
> `{$充值账号}` → `{$虎牙平台账号}`，**11/11 `isSuccess:true`，回读 11/11 一致**。
> 脚本：`tools/set_huya_account_1086681905342.py`（`--dry` 预览，自动落盘改动前备份）、
> `tools/verify_1086681905342.py`（回读校验）。

⚠️ 记得**两处同时改**（见 §8.1 红字），否则返回成功但值不变。

## 十一、⭐ 先删后建 SKU + 一条龙配货源（已验证）

场景：整份换掉某商品的 SKU 档位，再一次性配好货源。

| 步 | 接口 | 关键点 |
|---|---|---|
| ① 读+备份 | `GetItemInfo` | 全量 29 字段 |
| ② 补字段 | `Edit`（先 no-op 验证） | 补 `spBizType=25` + `categoryName` |
| ③ 重建 SKU | `Edit` | 只改 `saleProperties[].values` + `itemSkuList[]`；**旧档自动删、新档 skuId 平台重分配** |
| ④ 配货源 | `SaveSkuAldsInfo` ×N | 模板取**同品类姊妹商品**的 SKU 配置，逐 SKU 改 `skuId/specName/goodsId/multiple/pno/参数值` |

> 🔑 **`idNo` 置 0** —— 它是每 SKU 独立的记录号，新建时必须置 0 让服务端分配；照抄模板会串记录。

> 🔑 从零拼 51 个字段易漏，**优先拿同品类姊妹商品的配置当模板**。

实测（2026-09-24）：商品 `1085667022115` 旧 2 档 → 新 34 档，价格/货源/变量/倍数 **回读 34/34 全绿**。

## 十二、⭐ 平台售价（platformPriceType）规则 —— 售价低于商城进价就「不同步」

**规则**：`闲鱼售价 < 货源成本（商城进价 / qcqcq `goods_price`） × 倍数` → **`platformPriceType = 1`（不同步）**；否则 `= 2`（同步订单金额）。⚠️ **判据基准是商城进价，不是货源面值（face_value）**——用户 2026-09-24 16:5x 纠正（抖币/虎牙/快手 1元货源 面值≈成本所以没暴露，biubiu/iQiyi 面值≫成本会误判）。

**为什么**：贴价/亏本档（首单特惠）不能把低价订单金额同步给货源方。

**货源商品单价**（取 qcqcq 的 `goods_price` 进价，1元货源即 1、10元货源即 10）：

| 货源编号 | 名称 | 单价(元) |
|---|---|---|
| 38430 / 42959 | 抖音抖币（钻石）1元 | 1 |
| 78900 | 虎牙币充值1元 | 1 |
| 78899 | 虎牙币充值10元 | 10 |
| 29577 | 快币充值1元 | 1 |

**枚举**：`1=不同步　2=同步订单金额　3=同步实付　4=同步单价　5=指定金额`

**实测**：4 个商品全量校准，仅「首单特惠」档满足「低于」→ 全部 `ppt=1`；
脚本 `edge-bridge/tools/fix_platform_price_type.py <tabId> [--dry]`（幂等，可反复跑）。

## 十三、⭐ 双维度 SKU 一条龙（biubiu 实例，2026-09-24）

场景：把一个**完全没有 SKU** 的闲鱼宝贝，照抄另一个在售商品的档位结构，一条龙配好货源。

**实例**：`1084793623900`「biubiu 游戏加速器月卡」（原 `saleProperties=null`）
照抄源商品 `1012104092517` → 2 维度 × 4 档 = **8 个 SKU**，闲鱼端实测已生效。

### 13.1 双维度 `saleProperties` 结构

```jsonc
" saleProperties": [
  {"name":"规格", "values":["全平台通用","手游免广告"]},
  {"name":"时长", "values":["7天【新户体验卡】","1个月【官方直充秒到】","3个月【官方直充秒到】","12个月【官方直充秒到】"]}
]
```
`itemSkuList` 按 **外层规格 × 内层时长** 展开；每个 SKU 的 `propertyList` 顺序与之一致，
`specName` = `"规格:全平台通用;时长:7天【新户体验卡】;"`（**分号分隔、分号结尾**）。

### 13.2 ⭐ 参数配置必须走两步（新坑）

| 步 | 动作 | 为什么 |
|---|---|---|
| ① | `SaveSkuAldsInfo`，`attach[0].name` **随便填**（如 `lblName1`），`supplierParamJson` 同 key | 服务端会**自动把 `attach[].name` 纠正成货源方真实字段名** |
| ② | 回读 `GetSkuAldsInfo` → 取 `attach[0].name`（真实名）→ **把 `supplierParamJson` 的 key 改成这个真实名**，再存一次 | 否则两处 key 不一致（`supplierParamJson` 保留你传的旧 key） |

> **实测**：biubiu 货源真实字段名 = **`recharge_account`**（手机号，「直冲你号」）。
> 传 `lblName1` 后回读 `attach[0].name` 已变 `recharge_account`，但
> `supplierParamJson` 仍是 `{"lblName1":"{$充值账号}"}` ⇒ **对齐后才 8/8 干净**。
> 抖币货源真实字段名恰好就是 `lblName1`，所以**以前没暴露这个坑**。

**⇒ 通用结论：`attach[].name` 以服务端纠正后的值为准，`supplierParamJson` 必须跟着对齐。**

### 13.3 `spBizType` / `categoryName` **并非必填**（纠正 §11）

实测 `1084793623900`：**不补**这两个字段，28 字段直接 `Edit` → `isSuccess:true`，
回读与原 payload **零差异**。

§11 说的「`GetItemInfo` 返回 29 个、`Edit` 要 31 个」对**从闲鱼同步、无 SKU** 的商品**不成立**。
⇒ 先试 **no-op（不补字段）**，失败再补；不要一上来就硬塞类目值（塞错反而有风险）。

> 备份里该商品的分类：`pvList` 显示 **游戏加速器**、`itemBizType=2（普通C2C宝贝）`。
> 阿奇索虚拟业务类型候选：`GetVirtualSpBizTypeList` → `["25","22","23","20"]`（只有 id 无名称）。

### 13.4 biubiu 货源映射（qcqcq id 直接平移）

| 档位 | 全平台通用 | 面值/供货 | 仅手游 | 面值/供货 |
|---|---|---|---|---|
| 7天 | 40651 | 5.90 / 4.192 | 40657 | 3.00 / 1.675 |
| 1个月 | **40650** | 20.00 / 17.685 | 40656 | 8.00 / 4.733 |
| 3个月 | 40649 | 60.00 / 48.763 | 40655 | 18.00 / 12.733 |
| 12个月 | 40647 | 240.00 / 168.852 | 40654 | 80.00 / 46.638 |

参数 `recharge_account` = 手机号 → 阿奇索填 `{$充值账号}`；**倍数恒为 1**（货源本身就是整份时长卡）。

### 13.5 脚本流水线（`edge-bridge/tools/`）

```bash
python read_goofish_item.py 1012104092517            # ① 读源商品 SKU
python probe_target.py 1679427147 1084793623900      # ② 读目标现状 + 自动备份
python rebuild_1084793623900_skus.py <tab> --noop    # ③ 先 no-op 试字段
python rebuild_1084793623900_skus.py <tab>           # ④ 建 8 个 SKU
python config_1084793623900_alds.py <tab> --dry      # ⑤ 干跑看映射
python config_1084793623900_alds.py <tab>            # ⑥ 写货源
python fix_param_1084793623900.py <tab>              # ⑦ ⭐ 对齐参数 key（新增必需）
python verify_1084793623900.py <tab>                 # ⑧ 回读校验 + 导出清单
python read_goofish_item.py 1084793623900            # ⑨ 闲鱼端验收 ✅
```

## 十四、🔴 硬规则：扒来的 SKU 必须做「去同质化」

> **上传 SKU 时，规格名必须改写，不许一字不差照抄源商品。**
> **价格严格照抄源商品**（2026-09-24 用户明确：**只改规格名，不动价**）。

**为什么**：闲鱼对同质化商品（标题 / 规格 / 价格高度雷同）会**限流、降权** —— 抄得越像，流量越差。

**怎么做** —— 换措辞 / 分隔符 / 后缀，保持档位语义一一对应、买家一眼看懂：

| 源（照抄） | 去同质化后 |
|---|---|
| 7天【新户体验卡】 | 7天·新客体验卡 |
| 1个月【官方直充秒到】 | 1个月·官方直充 |
| 3个月【官方直充秒到】 | 3个月·官方直充 |
| 12个月【官方直充秒到】 | 12个月·官方直充 |
| 全平台通用 | 全平台通兑 |
| 手游免广告 | 手游免广告版 |

**落地时三处必须同步改**（漏一处就白做）：

1. `Edit` 的 `saleProperties[].values`
2. `Edit` 的 `itemSkuList[].propertyList[].valueText`
3. 阿奇索 `SaveSkuAldsInfo` 的 `specName`（`"规格:全平台通兑;时长:7天·新客体验卡;"`）

> ⚠️ 改写要**保持档位一一对应**，别把 7天 写成 7 日卡又漏掉 3天 这种。
> ⚠️ 别忘了 `platformPriceType` 的判据是「售价 vs 商城进价（goods_price）」，**改写规格名不影响它**。

> 📌 `1084793623900`（biubiu 8 档）是**规则生效前**配的，用户同意**保持现状不动**。

## 🏭 货源选择策略（2026-10-15 用户定 · 只比两家）

> **货源只在「志远」和「商战」两家里比，两家互补。**

| 货源 | alds 供货商账号 | 取数方式 | 备注 |
|---|---|---|---|
| **志远** zy.kkam | `95425` | `v3_huafei.search()` / `getDetail` | **主力**，余额须充足 |
| **商战** qqkami | `96810` | `qqkami_search.search_front(kw)`（无搜索 API，走前台 `/search/{kw}`） | 2026-10-15 接入，**余额 0 需先充值** |

- **逐档比价取低**：同一商品**每一档**分别比 `salesPrice` 取便宜那家 —— **不按品牌整切**（不同档可来自不同家）。
- **互补**：某家没有该品类/档位 → 直接用另一家。
- **不再使用** 省省(95131) / 星芒(95105) / 追梦(95329) / 千城(93310)（存量已按旧源配好的商品**不动**）。
- `spec.acct` = 对应 alds 账号 ID，`deploy.py` 自动走该家配货，脚本层无需改动。

## 🔗 相关
- [[操作-阿奇索上品一条龙]] —— **流程层权威源**（上品工作流 / deploy 一条龙 / 填写模板 / 双闸 / 命名 / 文案 / 改价 / 周期 / 双维度），2026-11-04 整合自 WorkBuddy
- [[项目-edge-bridge]] —— 用于自动化操作的后台桥接
- [[经验-踩坑手册]]
- 旧版完整手册 `WorkBuddy\...\edge-bridge\README-阿奇索SKU配置.md` 已于 **2026-11-05 并入本文件并改为指针**，内容以本文件为准。
