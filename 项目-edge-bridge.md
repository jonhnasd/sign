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

## 放在哪

```
C:\Users\Administrator\WorkBuddy\2026-09-22-11-37-41\edge-bridge\
├─ extension\          浏览器扩展（edge://extensions 加载此文件夹）
├─ server.mjs          桥接服务（WebSocket 服务端 + MCP stdio，零依赖）
├─ start.cmd / stop.cmd
└─ tools\              各类操作脚本（阿奇索 SKU 自动化等）
```

MCP 注册在 `~/.workbuddy/.mcp.json` 的 `edge-bridge` 项。

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
