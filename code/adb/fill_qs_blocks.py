# -*- coding: utf-8 -*-
"""给缺操作层的笔记批量补「🚀 快速开始」块（每篇按其真实入口定制）"""
import io
import os

VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"

BLOCKS = {
"项目-手机接入工具链.md": """## 🚀 快速开始

> [!note] 一句话
> 一条命令探测并接好手机（序列号 / 架构 / token / 协议全自动）。

### 前置条件
- 手机开 **USB 调试**并已授权
- USB 线插好（`adb devices` 能看到 `device` 状态，不是 `unauthorized`）

### 一键入口

```bash
# 换机 / 首次接入：跑这个就够
bash C:/Users/Administrator/.workbuddy/tools/adb/bootstrap.sh
```

### 预期输出
```
设备   : realme RMX3372  (Android 14 / SDK 34)
序列号 : ffd82337
token  : xxxxxxxxxxxxxxxx
协议   : https
✓ USB 通道已通 (https)
```
❌ 失败 → `device` 状态为 `unauthorized` → 手机上确认授权弹窗

### 完整步骤
1. 手机开 USB 调试 → 插线 → 屏幕上点「允许」
2. `bash bootstrap.sh`
3. 之后服务重启了跑 `bash firerpa_start.sh` 恢复通道

""",

"项目-手机调试能力链.md": """## 🚀 快速开始

> [!note] 一句话
> 接入完成后，用 MCP 指令直接操控手机（读屏 / 点击 / 截图 / 装 App）。

### 前置条件
```bash
# ① 手机已接入（见 [[项目-手机接入工具链]]）
curl -s --noproxy '*' http://127.0.0.1:8787/health   # 那是浏览器桥接，手机看下面
bash C:/Users/Administrator/.workbuddy/tools/adb/bootstrap.sh | grep "token"
# 期望能打出 token 和协议

# ② Shizuku 在跑（FIRERPA 依赖它）
```

### 一键入口

```bash
# 重启整条链路（Shizuku + FIRERPA + 通道）
bash C:/Users/Administrator/.workbuddy/tools/adb/bootstrap.sh
bash C:/Users/Administrator/.workbuddy/tools/adb/firerpa_start.sh   # 只恢复通道
bash C:/Users/Administrator/.workbuddy/tools/adb/mitm.sh start       # 开启抓包
```

### 预期输出
```
Shizuku: ✓ 服务已在运行 (pid xxx)
FIRERPA: ✓ 服务已启动
token   : xxxxxxxxxxxxxxxx
✓ MCP initialize → firerpa 10.9 / 14 个工具
```
❌ 401 → token 取错来源 → 从 `usr/.local/properties` 的 `ssl-web-credential` 取，**不是** server.log

### 完整步骤
1. `bootstrap.sh` 一条命令接好
2. 装 App：`startApplication(package_name)` → `adb install`
3. 读屏：`observeDevice(vision:true)` 直接截图
4. 抓包：`mitm.sh start` → 手机装 mitmproxy CA

""",

"项目-sqqy88商品抓取.md": """## 🚀 快速开始

> [!note] 一句话
> 已完全脱机 —— 直接跑脚本抓商品/详情/增量，不需要手机在线。

### 前置条件
- `.sqqy88_jwt.txt` 未过期（uni 端详情需登录态，约 7 天）
- 脚本在 `C:/Users/Administrator/Desktop/workbuddy/文档提取/`

### 一键入口

```bash
cd "C:/Users/Administrator/Desktop/workbuddy/文档提取"

# 抓商品列表 / 详情 / 增量
python sqqy88_cli.py search <关键词>
python sqqy88_cli.py detail <商品ID>
python sqqy88_cli.py incremental
```

### 预期输出
```
✓ 抓到 N 条商品（已写入 data/sqqy88_*.json）
✗ 「请登录后操作」→ JWT 过期 → 需手机在线重取
```

### 完整步骤
1. 检查 JWT 是否过期
2. 跑脚本抓取
3. 结果落 JSON，直接喂给 `上sku_siquan.py` 拉介绍/图集

> ⚠️ 双签名算法（MD5 / SHA1）已在脚本内实现，**别再手工重算**。

""",

"项目-qcqcq货源抓取.md": """## 🚀 快速开始

> [!note] 一句话
> 货源站接口逆向 + 持续抓取，用于拿成本价和货源商品。

### 前置条件
- 登录态有效（`login_guard.py` 会检查）
- 脚本目录 `C:/Users/Administrator/Desktop/workbuddy/文档提取/`

### 一键入口

```bash
cd "C:/Users/Administrator/Desktop/workbuddy/文档提取"

# 登录态守卫（先跑，失效会提示）
python login_guard.py

# 持续抓取（间隔秒 / 最大轮数）
python fetch_qcq.py 300 20

# 按加价率生成 SKU 建议
python make_sku.py --markup 10 --threshold 10 --below fixed:0.5 --out data/skus
```

### 预期输出
```
✓ 登录态有效
抓到 N 条货源，成本价区间 xxx~yyy
✓ 已生成 data/skus/*.json
✗ 登录失效 → 重新扫码登录
```

### 完整步骤
1. `login_guard.py` 确认登录态
2. `fetch_qcq.py` 持续抓
3. `make_sku.py` 出 SKU 建议

> ⚠️ **status: legacy** —— 方法论（Vue SPA 抓取、参数构造）仍有效，
> 但**货源平台已不在现行选源范围**（现行只比志远 + 商战，见 [[身份与记忆/MEMORY]]）。

""",

"操作-上SKU直连思券货源(手机通道).md": """## 🚀 快速开始

> [!note] 一句话
> 插上手机，用手机出口 IP 直连思券拉商品名/介绍/图集（电脑直连被风控拦）。

### 前置条件
```bash
# ① 手机 adb 在线
"C:/Users/Administrator/.workbuddy/tools/adb/platform-tools/adb.exe" devices
# 期望：ffd82337  device

# ② 手机连着放行出口的 WiFi
# ③ JWT 未过期（uni 端详情需登录态，约 7 天）
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
1. 手机连 WiFi + adb 在线
2. `python 上sku_siquan.py <关键词>`
3. 结果喂给 `deploy.py` 的文案⑪ 与详情图⑬

> ⚠️ **电脑直连返回 0 字节** —— 思券按**出口 IP** 风控，**必须走手机通道**。

""",
}

for fn, block in BLOCKS.items():
    p = os.path.join(VAULT, fn)
    s = io.open(p, encoding="utf-8").read()
    if "## 🚀 快速开始" in s:
        print(f"  = {fn}（已有，跳过）")
        continue
    # 插到正文标题之后（frontmatter 之后的第一个 # 标题）
    lines = s.split("\n")
    # 找 frontmatter 结束
    i = 0
    if lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                i = j + 1
                break
    # 找第一个 # 标题行
    t = None
    for j in range(i, len(lines)):
        if lines[j].startswith("# "):
            t = j
            break
    if t is None:
        print(f"  ✗ {fn} 找不到标题行")
        continue
    new = lines[:t + 1] + [""] + block.rstrip("\n").split("\n") + [""] + lines[t + 1:]
    io.open(p, "w", encoding="utf-8", newline="\n").write("\n".join(new))
    print(f"  ✓ {fn} 已补快速开始块")
