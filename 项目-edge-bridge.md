---
created: 2026-09-23
updated: 2026-11-05
tags: [项目, 浏览器, 桥接]
type: 项目笔记
status: active
---
# 项目 · Edge Bridge（浏览器桥接）

> 让 Agent 实时读取/控制**正在使用的**浏览器，不需要调试端口，不需要重启浏览器。
> 2026-09-24 自建并跑通。

## 🚀 快速开始

> [!note] 一句话
> 装好扩展 + 桥接服务在跑 → 我就能直接读页面、点按钮、调接口、调你的浏览器。

### 前置条件

```bash
# ① 桥接服务在跑（默认开机自启，也可用 MCP 自动拉起）
curl -s --noproxy '*' http://127.0.0.1:8787/health
# 期望：{"ok":true,"role":"master","port":8787,"extConnected":true}
#                              ↑ extConnected 必须 true

# ② Edge 已打开（普通 Edge，不是 webview2）
# ③ edge://extensions 里「Edge Bridge」已启用
```

**首次装扩展**：`edge://extensions` → 开启开发者模式 → 「加载已解压的扩展程序」→ 选
`C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41\edge-bridge\extension`

### 一键入口

```bash
# ① 沙箱环境启动 Edge（关键：直接后台启动会被回收）
D="C:/Users/Administrator/.workbuddy/tools/edge"; mkdir -p "$D"
cat > "$D/open-baidu.cmd" <<'EOF'
@echo off
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" https://www.baidu.com
EOF
explorer.exe "C:\Users\Administrator\.workbuddy\tools\edge\open.cmd"
# ↑ 用 explorer 调用，让 Edge 脱离沙箱进程树，才能跨命令存活
# 注：open.cmd 是旧名，实际文件是 open-baidu.cmd

# ② 发指令（POST /rpc）
RPC() { curl -s --noproxy '*' -X POST "http://127.0.0.1:8787/rpc" \
  -H "Content-Type: application/json" -d "$1"; }

RPC '{"cmd":"tabs_list","params":{}}'                    # 列出标签页
RPC '{"cmd":"eval","params":{"tabId":123,"expression":"document.title"}}'
RPC '{"cmd":"read_page","params":{"tabId":123}}'
RPC '{"cmd":"click","params":{"tabId":123,"selector":"#btn"}}'
RPC '{"cmd":"screenshot","params":{"tabId":123}}'
RPC '{"cmd":"cdp","params":{"tabId":123,"method":"Network.enable"}}'   # 万能后门
```

### 预期输出

```
tabs_list → { ok:true, data:[{id:xxx, title:"...", url:"..."}] }
eval      → { ok:true, data:{result:"..."}}
✗ 「浏览器扩展未连接」→ /health 的 extConnected 为 false（Edge 没开/扩展被关）
✗ 「未知指令: tabs」   → 指令名要**下划线小写**（tabs_list 不是 tabs）
```

### 完整步骤

1. Edge 开着 + 扩展启用（`/health` → `extConnected:true`）
2. `tabs_list` 找到目标页 → 拿 tabId
3. `eval` / `read_page` 读页面 → 分析 → `click`/`type` 操作
4. 必要时 `cdp` 直接发 CDP 命令（万能后门，能做 eval 做不到的事）

> ⚠️ **不要主动 `tab_new` 开页、不爬 DOM、不重启桥接** —— 用户开着页 = 登录态在 = 接口零等待。
> ⚠️ **eval 不带 awaitPromise** → 异步请求返回 `null`，必须走 `cdp` + `Runtime.evaluate{awaitPromise:true,returnByValue:true}`。

## 放在哪

```
C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41\edge-bridge\   ← ✅ 用这个
├─ extension\          浏览器扩展（edge://extensions 加载此文件夹）
├─ server.mjs          桥接服务（WebSocket 服务端 + MCP stdio，零依赖）
├─ start.cmd / stop.cmd
└─ tools\              各类操作脚本（阿奇索 SKU 自动化等）
```

MCP 注册在 `~/.workbuddy/.mcp.json` 的 `edge-bridge` 项 → 指向上面这个目录。

> ⚠️ **另有一份旧副本**：`C:\Users\Administrator\Desktop\workbuddy\杂\edge-bridge`
> （server.mjs 19900 字节 / 09-24）。**注册在用的是上面那个新版本**（21160 字节 / 10-10）。
> 两份同名目录容易搞混 —— 认准 `WorkBuddy\2026-09-22-11-37-41` 这个路径。

## 结构

```
用户日常 Edge 窗口
  └─ Edge Bridge 扩展（chrome.debugger + scripting）
        ↕ WebSocket 127.0.0.1:8787
     本地桥接服务（master；多实例时后启动的转 slave 转发）
        ↕ MCP stdio
     Agent
```

## 能力

`browser_status` / `tabs` / `navigate` / `eval` / `read` / `click` / `type` /
`screenshot` / `net_install` / `net_get` / `cdp` / `cookies` / `detach`

其中 `browser_eval` 最通用，`browser_cdp` 是万能后门。

## 🔧 实际调用方式（2026-11-05 实测校正）

**指令走 `POST /rpc`**（不是 REST！body 是 `{cmd, params, timeout}`）：

```bash
curl -s --noproxy '*' -X POST "http://127.0.0.1:8787/rpc" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"tabs_list","params":{}}'
```

**⚠️ 指令名是下划线小写**（`tabs_list` / `tab_get` / `read_page`），
不是驼峰也不是 `tabs`。完整表在 `extension/background.js` 的 `HANDLERS` 对象里：

```
ping  status  tabs_list  tab_get  tab_activate  tab_new  tab_close
navigate  eval  read_page  click  type  screenshot
net_install  net_get  cdp  cookies  attach  detach
```

**只有 `/health` 是 GET**，其它路径（`/tabs` 等）会返回纯文本 `edge-bridge`。

### 启动 Edge（沙箱环境的坑）

**⚠️ 直接后台启动会被回收** —— shell 退出时 Edge 一起被杀（实测进程数归零）。

**解法：用 `explorer.exe` 调用 `.cmd` 启动器**，让 Edge 脱离沙箱进程树：

```bash
# 启动器：C:\Users\Administrator\.workbuddy\tools\edge\open-baidu.cmd
explorer.exe "C:\Users\Administrator\.workbuddy\tools\edge\open-baidu.cmd"
```

实测：这样启动后 Edge **跨命令存活**，扩展自动重连（`extConnected: true`）。

### 扩展连不上的两种情况

| `/health` 返回 | 原因 | 处理 |
|---|---|---|
| `extConnected: false` | Edge 没开 / 扩展被禁用 | 开 Edge + `edge://extensions` 确认启用 |
| `extConnected: true` 但 RPC 报「扩展未连接」 | 连接刚建立还没稳 | 等 3~5 秒重试（SW 心跳 20s） |

---

## 关键设计（踩过的坑）

1. **MV3 service worker 会休眠** → `chrome.debugger` 附加状态丢失
   ⇒ 用 **offscreen document** 维持 WebSocket（永不休眠）+ 每 20s 心跳唤醒 SW
2. **网络抓包别依赖 CDP 事件流**（SW 重启就断）⇒ 用注入 hook
   注入必须用 `files`（不受页面 CSP 限制），不能用 `func + eval`
3. **Node 后台启动会秒退**：stdin 立即 EOF ⇒ 记录 `sawStdin` 区分 daemon 模式
4. **stdin 关闭不能立即退出**：在途异步请求会丢 ⇒ `inflight` 计数
5. **端口冲突**：首个进程当 master，后续 EADDRINUSE 转 slave 走 HTTP 转发

## 已知边界

- 扩展权限大（`<all_urls>` + `debugger`），仅本机自用
- 页面顶部会显示「正在调试此浏览器」黄条（正常）
- 不做验证码识别

## 🔗 相关
- [[操作-阿奇索宝贝SKU设置]] —— 用桥接自动填 SKU 的实战
- [[经验-踩坑手册]]
- [[本机环境档案]]
