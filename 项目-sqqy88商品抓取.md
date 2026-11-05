---
tags: [项目, 协议逆向, 抓取, CRMEB, uni-app]
type: 项目
created: 2026-11-04
updated: 2026-11-04
owner: 秋雨
status: active
---

# 项目：sqqy88 商品抓取（列表 / 详情 / 增量监控）

## 🚀 快速开始

> [!note] 一句话
> 已完全脱机 —— 直接跑脚本抓商品/详情/增量，不需要手机在线。

### 前置条件
- `.sqqy88_jwt.txt` 未过期（uni 端详情需登录态，约 7 天）
- 脚本在 `C:/Users/Administrator/Desktop/workbuddy/文档提取/`

### 一键入口

```bash
cd "C:/Users/Administrator/Desktop/workbuddy/文档提取"

# 抓商品列表（脱机版：H5 端接口，cid 传 "" 才是全量）
python sqqy88_fetch.py

# 抓商品详情（uni 端，需 JWT）
python sqqy88_detail.py

# 探接口/签名是否正常
python sqqy88_probe.py
```

> ⚠️ **出口 IP 绑定**：脚本里 `IFACE` 指向 **WiFi「ZTE_43AF48」网卡的 IPv4**，
> 强制流量从该出口走。走有线（郑州管城出口）会被站点风控拦，**连首页都返回 0 字节**。
> 换网络时要改 `sqqy88_fetch.py` 里的 `IFACE`。

### 预期输出
```
✓ 抓到 N 条商品 → sqqy88商品原始数据-YYYYmmdd-HHMM.json
✓ 详情已导出   → sqqy88商品详情-YYYYmmdd-HHMM.xlsx
✗ Content-Length: 0 → 出口 IP 被拦 → 检查 IFACE 是否指向正确网卡
✗ 「请登录后操作」→ JWT 过期 → 需手机在线重取 .sqqy88_jwt.txt
```

### 完整步骤
1. 检查电脑连的是 **ZTE_43AF48** WiFi
2. `.sqqy88_jwt.txt` 未过期（约 7 天）
3. `python sqqy88_fetch.py` 抓列表 → `python sqqy88_detail.py` 抓详情
4. 结果喂给 `上sku_siquan.py` 拉介绍/图集

> ⚠️ 双签名算法（H5 端 / uni 端）已在 `sqqy88_fetch.py` 内实现，**别再手工重算**。
> ⚠️ **已知失效**：旧笔记里的 `sqqy88_cli.py` **不存在**，实际脚本是 `sqqy88_fetch.py` / `sqqy88_detail.py`。


> 2026-11-04 完成。**最终状态：完全脱离手机**，电脑独立抓取。
> 配套能力链见 [[项目-手机调试能力链]]（本篇的定位手段来自那条链）。
>
> 站���性质：`http://88.sqqy88.cn` —— CRMEB / ThinkPHP 商城，**HTTP 明文**（**不需要装 CA 证书**）。
> **双前端共存**：CRMEB H5（`/front/diy/*`）+ uni-app H5（`/uni/*`），各有独立签名。

---

## 一、最终能力一览

| 能力 | 状态 |
|---|---|
| 商品列表（全量） | ✅ 1081 个，**完全脱机**，自算签名 |
| 商品详情（50+ 字段） | ✅ **1081/1081 全部抓到**，完全脱机 |
| 产品介绍 / 图集 / 购买须知 | ✅ 含原始 HTML 与图片 URL 数组 |
| 实际券后价 | ✅ 独立接口 |
| 增量监控（网站更新了什么） | ✅ 快照 diff，实测能抓到分钟级变化 |
| 手机依赖 | ❌ **已完全解除** |

---

## 二、接口全表

### 通用请求头

```http
POST http://88.sqqy88.cn/<path> HTTP/1.1
Content-Type: application/json
Sign: <签名>
Form-Where: h5
User-Agent: Mozilla/5.0 (Linux; Android 14; RMX3372) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.0.0 Mobile Safari/537.36
Origin: http://88.sqqy88.cn
Referer: http://88.sqqy88.cn/
Accept: */*
Accept-Language: zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7
```

### 1. `POST /front/diy/goods/index` —— 商品列表

```json
{"cid":"", "cpid":"", "sort_type":0, "keyword":"", "start_price":"", "end_price":"", "goods_type":[], "index":4, "page":1, "limit":10}
```

⚠️ **`cid` 必须传 `""`（或不传）才是全量**；传 `"1"` 会返回空数组。
返回 `{"code":200,"data":[{...商品...}]}`，一次返回全量（约 708KB），`limit` 不起作用。

### 2. `POST /front/diy/category/index` —— 分类树

body `{}` → 10 个分类。

### 3. `POST /uni/categoods` —— 单商品详情（uni 端）

```json
{"id":"1181", "sku_id":""}
```
⚠️ **必须带登录态**：`Authorization: Bearer <JWT>`，否则返回 `{"code":410000,"msg":"请登录后操作"}`。
返回结构：
```json
{"code":200,"msg":"确定","data":{
  "goods": { ...51 个字段... },
  "goods_sku": [], "goods_spec_key": [], "goods_spec_value": {},
  "coupon_label": [], "activity_list": [], "merchant": {...8 字段},
  "kefulink": "", "can_up_level": true, "view_goods_price": false
}}
```

**goods 的 51 个字段（实测）**：
```
id / multiple / can_api_see / spec_type / goods_video / goods_info / goods_imgs /
goods_notice / goods_price_id / sku_id / num_count / num_type / start_count /
end_count / goods_name / demo_url / recharge_url / uid / goods_short_name / browse /
goods_tags / face_value / goods_type / ishot / goods_img / goods_sales / stock_num /
status / take_up_time / card_option / category_ids / need_balance / is_batch /
can_level / can_price / can_price_level / is_premium / json_config / attach /
goods_price / default_level_price / coupon_price / received_price ...
```
> `goods_info` = 产品介绍正文（原始 HTML）
> `goods_imgs` = 图集 URL 数组
> `goods_notice` = 购买须知（HTML）
> `browse` = 浏览量，`goods_sales` = 销量，`stock_num` = 库存

### 4. `POST /uni/goods/get_goods_price` —— 实际券后价

```json
{"quantity":1, "goods_id":1181}
```
→ `{"code":200,"data":{"coupon_price":"3.90","received_price":0,"goods_price":"3.90","coupon_id":0}}`

---

## 三、签名算法（**两套，已全部破解**）

```
KEY = 18a3257675b85febdfcdd83e7150c0b9
ts  = 秒级时间戳（Math.round(Date.now()/1000)）
```

| 端 | 公式 | 用在哪 |
|---|---|---|
| **H5 端** | `md5( md5( md5("front" + KEY) + ts ) ) + ts` | `/front/diy/*` |
| **uni 端** | `md5( md5( md5("h5" + KEY) + ts ) ) + ts` | `/uni/*` |

**完全同构，只差前缀 `front` / `h5`**。

### 推导来源

**H5 端** —— 从 CRMEB 的 `app.<hash>.js` 里模块 `5f87` 的 `u()` 函数：
```js
function u(){
  var e = n("f080"),                                   // MD5 实现
      t = Math.round(new Date/1e3).toString(),          // ts
      o = "18a3257675b85febdfcdd83e7150c0b9",          // KEY
      i = (new e).update("front"+o).digest("hex");      // md5("front"+KEY)
  return (new e).update((new e).update(i+t).digest("hex")).digest("hex") + t;
}
```
赋值点：`m.interceptors.request.use(e => { e.headers["Sign"] = Object(s["a"])(); ... })`

**uni 端** —— 从 uni-app 自己的 `index.<hash>.js` 里 `$util` 的 `reqSign`（压缩后名为 `F`）：
```js
F = function(){
  var e = Math.round(new Date/1e3).toString(),
      t = c.default.md5("h518a3257675b85febdfcdd83e7150c0b9");   // ← "h5" 前缀
  return c.default.md5(c.default.md5(t+e)) + e;
};
```
挂载点：`e.prototype.$util = { ..., reqSign: F, ... }`

### ⚠️ 关键性质

**uni 端的 sign 只依赖时间戳，与接口路径和请求参数完全无关。**
实测：同一秒内 `valiToken` / `goodslist` / `goodssearch` / `userinfo` 四个不同接口的 sign **完全相同**。

### ⚠️ 两套不能混用
- 用 H5 的 sign 调 `/uni/*` → `请校验本地或服务器时间`
- 用 uni 的 sign 调 `/front/diy/*` → 同上
- 抓包拿到的 sign 只能用于**它当时那一套**

### 时间戳容差
- H5 端：实测 7 分钟内仍有效
- uni 端：实测 166 秒后仍有效（保守起见按 2 分钟内用）

---

## 四、怎么找到 uni-app 的代码（完整推导链）

这套推导花了最久，值得完整记录。

### 线索 1：同一 URL 返回两份 HTML

`/pages/goods/detail?id=1181` 会返回**两份不同大小的 HTML**：
- **17853 字节** = CRMEB 模板（`/template/front/diy/static/js/app.<hash>.js`）
- **2102 字节** = uni-app 模板 ← **这个才是 uni-app 的入口**

> 判别方法：看响应体大小。

### 线索 2：uni-app 的 HTML 直接写着它的入口

```html
<div id=app></div>
<script src=/template/h5/default/static/js/chunk-vendors.84178d07.js></script>
<script src=/template/h5/default/static/js/index.7e57eb6e.js></script>
<script src="/static/kefu/kefu.js"></script>
```

### 线索 3：在 index.<hash>.js 里搜 `reqSign`

```bash
curl -A "<移动端UA>" -o index.js http://88.sqqy88.cn/template/h5/default/static/js/index.7e57eb6e.js
grep -o "reqSign[^,;]\{0,80\}" index.js
```
命中 `$util` 对象定义 → `reqSign: F` → 顺着找到 `F=function(){...}` 即算法本体。

### 线索 4：静态资源不吃风控

**API 接口按出口 IP 拦，但 JS/CSS/图片等静态资源电脑直连就能下** —— 这一点是能继续挖 JS 的前提。

### 走过的弯路（避免重走）
| 弯路 | 原因 |
|---|---|
| 在 CRMEB 的 `app.js` 里找 `reqSign` | uni 端代码不在这个 bundle 里 |
| 在 `pages-goods-detail.js`（520KB）里找 | 只有调用点，定义在 uni-app 的 index 里 |
| 找 `chunk-commons.<hash>.js` | 那是 CRMEB 自己的 chunk（hash 来自 CRMEB 的 runtime），不是 uni-app 的 |
| 用 mitm 抓 chunk 正文 | addon 截断到 40000 字节，关键代码在后半段 |

---

## 五、出口 IP 风控（最隐蔽的一关）

### 现象

同一个接口、同样签名、同样 UA：
```
电脑直连        → HTTP 200, Content-Length: 0   （连首页都空）
手机直连        → HTTP 200, 17885 字节          ✓
```

### 根因

**站点按出口 IP 风控**。而这台电脑的**两个出口都不同**：

| 出口 | 归属 | 结果 |
|---|---|---|
| 电脑「以太网」192.168.10.101 | 河南移动 · **郑州管城** 34.7657,113.753 | ❌ 被拦 |
| 电脑「WiFi ZTE_43AF48」192.168.0.102 | 河南移动 · **柘城城关镇** 34.1046,115.318 | ✅ 放行 |
| 手机 WiFi 192.168.0.100 | 同上（柘城） | ✅ 放行 |

同一 `192.168.0.x` 网段，但**运营商多 WAN**，且 Windows 路由 metric 让流量默认走了**有线**（metric 35 < WiFi 45）。

### 已排除的干扰项（都试过，全无效）
- 签名错误 → 会明确报「手机签名错误」，而实际是**静默返回空**
- Cookie（先 GET 首页拿 KSSID 再请求）→ 无效
- 完整 Chrome 指纹头（`sec-ch-ua` / `sec-fetch-*` / `sec-ch-ua-platform`）→ 无效
- `curl_cffi` 的 `impersonate="chrome"`（TLS JA3 指纹伪装）→ 无效
- 本机已有代理（出口仍是郑州）→ 无效

### 正确做法：绑定 socket 到指定网卡

```python
import http.client, socket

class BoundHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((IFACE, 0))        # ← 关键：绑定本地 IP 决定出口
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))

class BoundHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(BoundHTTPConnection, req)

class BoundHTTPSHandler(urllib.request.HTTPHandler):
    def https_open(self, req):
        return self.do_open(BoundHTTPConnection, req)

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), BoundHTTPHandler(), BoundHTTPSHandler())
```

⚠️ **`HTTPHandler` 和 `HTTPSHandler` 是两个类，必须分别重写。**
只写 `https_open` 对 HTTP 站点**完全无效**（我踩过：请求没 code、返回空）。

命令行等价写法：`curl --interface 192.168.0.102 ...`

### 换网络后怎么办
改 `sqqy88_fetch.py` 里的 `IFACE`（或设环境变量 `SQQY_IFACE`），用 `ipconfig` 查当前 WiFi 的 IPv4。
**前提是这个 WiFi 的出口 IP 不在被拦名单里** —— 若换到别的 WiFi，需要重新验证。

### 临时切 WiFi 抓数据再切回有线（2026-11-05 新增）

适合场景：日常用有线上网，但要抓 sqqy88 时临时切 WiFi。

```bash
# ① 连接 WiFi ZTE_43AF48（出口 IP 必须在 192.168.0.x 段）
# Windows: 设置 → 网络和 Internet → WiFi → 连 ZTE_43AF48

# ② 查 WiFi 分配的 IPv4
ipconfig | findstr "IPv4"
# 期望看到类似: IPv4 地址 . . . . . . . . . . . . : 192.168.0.102

# ③ 设置环境变量（或直接改脚本 IFACE）
$env:SQQY_IFACE="192.168.0.102"

# ④ 跑抓取
cd C:/Users/Administrator/Desktop/workbuddy/文档提取
python sqqy88_detail.py          # 全量详情
# 或
python sqqy88_fetch.py           # 列表 + 分类 + 详情样例

# ⑤ 抓完切回有线
# Windows: 断开 WiFi
# 脚本里 IFACE 自动失效（绑定不到 192.168.0.102 会报错），下次抓之前记得重新设
```

> ⚠️ **关键**：WiFi 必须是 ZTE_43AF48（或同出口网段）。其他 WiFi 的出口 IP 可能也在风控名单里，需要先验证：
> ```bash
> python sqqy88_probe.py
> ```
> 看到 "网卡 192.168.0.xxx" 的「分类接口/商品列表」都返回数据 ≠ 风控，才算可用。

---

## 六、增量监控（网站更新了什么）

### 为什么必须用快照 diff

**站点接口不返回任何时间戳**（无 `update_time` / `create_time` / `modify_time`），
所以无法直接问「哪些更新了」，只能靠两次快照对比。

### 比对字段

`goods_price` / `stock_num` / `goods_sales` / `status` / `goods_type` / `face_value` / `category_ids` / `ishot`

### 输出三类 → Excel 三表

1. **字段变更** —— 商品ID / 名称 / 变更字段 / 旧值 / 新值
2. **新增商品**
3. **消失商品**（下架）

### 实测有效

间隔几分钟跑第二次，立刻抓到真实变化：
```
商品 1172  库存: 674 → 673
商品 1172  销量: 1824 → 1825   【链接激活】WPS超级会员1天-卡密直冲 日常可兑换
```

### 基线管理

快照存 `_snapshots/snapshot-YYYYmmdd-HHMM.json`，`--save` 参数更新基线：
```bash
python sqqy88_diff.py            # 与最近基线对比
python sqqy88_diff.py --save     # 对比后把当前存为新基线
python sqqy88_diff.py --baseline 某个文件.json
```

---

## 七、脚本用法

### 文件位置

```
C:\Users\Administrator\Desktop\workbuddy\文档提取\
├─ sqqy88_fetch.py     底层封装
├─ sqqy88_detail.py    全量详情 → Excel + JSON
├─ sqqy88_diff.py      增量对比 → Excel 三表
├─ .sqqy88_jwt.txt     登录态 JWT（约 7 天有效）
└─ _snapshots/         增量基线快照
```

### `sqqy88_fetch.py` API

```python
import sqqy88_fetch as F

F.IFACE                  # 绑定的出口网卡 IP（默认 192.168.0.102）
F.make_sign(ts=None, flavor="h5")   # flavor: 'h5' | 'uni'
F.get_jwt()              # 读本地 JWT
F.get_goods(cid="", page=1, limit=20, **kw)   # 商品列表
F.get_categories()       # 分类树
F.get_goods_detail(goods_id)      # uni 端详情（51 字段，自动带 JWT）
F.get_real_price(goods_id, quantity=1)         # 实际券后价
```

### 命令行

```bash
cd C:/Users/Administrator/Desktop/workbuddy/文档提取
PY="C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

"$PY" sqqy88_fetch.py           # 自检 + 分类 + 列表样例 + 详情样例
"$PY" sqqy88_detail.py          # 全量详情（并发16，约 2 分钟，1081/1081）
"$PY" sqqy88_detail.py 50       # 只抓 50 个（调试用）
"$PY" sqqy88_diff.py            # 增量对比
"$PY" sqqy88_diff.py --save     # 对比后更新基线
```

### 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `SQQY_IFACE` | 绑定的出口网卡 IP | `192.168.0.102` |
| `ADB_SERIAL` | 旧的手机借道模式用的序列号 | `ffd82337` |

### 环境变量与依赖

- Python 环境：`C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
- 依赖：`openpyxl`（Excel 导出）
- 可选：`curl_cffi`（已装，但**对绕过风控无效**，留着备用）

---

## 八、数据结构与规模

### 商品列表字段（32 个）

```
id / category_ids / spec_type / num_count / num_type / start_count / end_count /
goods_name / goods_short_name / goods_tags / face_value / goods_type / ishot /
goods_img / goods_sales / stock_num / status / take_up_time / can_price /
need_balance / can_buy / can_no_buy / can_price_level / can_api_see / goods_price /
from_list / goods_type_text / uid_text_type / uid_text
```

### 分类（10 个）

```
280 低价福利品（父）
├ 226 88vip权益充值
├ 238 剪映教程
├ 278 剪映
├ 283 WPS系列
├ 284 ChatGPT
├ 285 Claude PRO
├ 286 豆包系列
├ 287 移动兑换
└ 289 自助卡密
```

### 规模统计（2026-11-04 快照）

- 商品总数 **1081**：虚拟商品 813 / 卡密商品 268 / 实物商品 0
- 价格分布：<1元 62 / 1-10 214 / 10-50 353 / 50-100 172 / 100-300 209 / ≥300 71
- 详情覆盖率：`goods_info` 683/1081、`goods_imgs` 1054/1081、`goods_notice` 99/1081
- **弹窗字段全空**：`goods_sku` / `goods_spec_key` / `goods_spec_value` / `coupon_label` / `activity_list` / `card_option` / `attach` 全部 0 条
  → **该站全部商品单规格、无优惠券、无活动 → 不存在规格选择弹窗**
- 全站 `spec_type` 均为 0

---

## 九、产物文件

| 文件 | 内容 |
|---|---|
| `sqqy88商品抓取-<时间戳>.xlsx` | 商品表（16 列，含筛选）+ 分类表 |
| `sqqy88商品原始数据-<时间戳>.json` | 全量商品原始 JSON |
| `sqqy88商品详情-<时间戳>.xlsx` | 详情表（21 列：标价/实付价/券后价/面值/库存/销量/浏览量/介绍长度/图集数/详情链接…） |
| `sqqy88商品详情原始-<时间戳>.json` | 详情原始 JSON（含 `goods_info` 完整 HTML、`goods_imgs` URL 列表） |
| `sqqy88站点更新-<时间戳>.xlsx` | 增量报告三表 |

---

## 十、已知限制

1. **JWT 约 7 天过期** → 过期后 uni 端详情返回「请登录后操作」。重取办法见 [[项目-手机调试能力链]]（需手机在线一次）。
2. **换 WiFi 就要改 IFACE**，且新 WiFi 的出口 IP 未必被放行，需重新验证。
3. **详情接口需登录态**，所以**列表能脱机、详情在 JWT 有效期内才能脱机**。
4. 站点无时间戳字段 → 增量只能靠 diff，快照频率决定了更新精度。
5. 该站是 HTTP 明文，**将来若改 HTTPS，全部需要重新装 CA 证书 + 改签名分析**。

---

## 十一、一句话复用模板

> 抓 sqqy88：跑 `C:\Users\Administrator\Desktop\workbuddy\文档提取\sqqy88_detail.py`（详情）或 `sqqy88_diff.py`（增量）。
> 前提：电脑连着 **WiFi ZTE_43AF48**，且 `sqqy88_fetch.py` 的 `IFACE` 绑该网卡 IP（出口 IP 才不被风控）；`.sqqy88_jwt.txt` 未过期。
> 签名：H5 端 `md5(md5(md5("front"+KEY)+ts))+ts`，uni 端把 `front` 换成 `h5`；KEY=`18a3257675b85febdfcdd83e7150c0b9`。

---

## 🔗 相关

- [[长期记忆]] —— 总索引
- [[经验-踩坑手册]] —— L/M/N 节（风控、Git Bash、Android 调试）
- [[项目-手机调试能力链]] —— 本篇的定位手段来源
- [[项目-qcqcq货源抓取]] —— 同类货源站抓取，可对照风控处理

---

*本文件由 AI 助手维护。敏感凭据（密码 / JWT / token / 手机号）**不入库**。*
