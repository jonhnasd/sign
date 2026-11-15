---
created: 2026-11-15
updated: 2026-11-15
tags: [项目, DSH, 工具链, 能力边界]
type: 项目
status: active
execution: read_only
verified_at: 2026-11-15
review_by: 2027-02-15
---

# 项目-DSH能力评估

> 评估对象：`https://deepseekdocs.com`（社区教程站，标 `v0.1.5-alpha.1`，背后仓库 `0xsline/awesome-deepseek-harness`）。
> 目的：判断 DSH 哪些能力**真能接进现有工作流**，哪些是看着有用实则不适用。
> 判据不是"文档怎么写"，而是**"这台机器、这个部署里到底挂了什么"**。

## 🚀 快速开始

> [!note] 一句话
> 想确认某项 DSH 能力现在能不能用 —— 先看**自己手上有哪些工具**，别急着照文档改配置。工具清单就是部署的实测结果。

### 前置条件

- DSH 会话内（能调工具）
- 需要跑库检查时：Python 在 `C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe`

### 一键入口

```powershell
# 跑库完整性检查（必须先设 PYTHONIOENCODING，否则 GBK 崩在 ✓ 字符上）
$env:PYTHONIOENCODING='utf-8'; & "C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" "C:/Users/Administrator/.workbuddy/tools/adb/check_vault.py"
```

```bash
# 改完 身份与记忆/ 只看差异、不落盘
bash C:/Users/Administrator/.workbuddy/tools/crypto/sync-memory.sh --check
```

### 预期输出

```text
✓ 检查器 13 项全绿 → exit=0
✗ 出现 UnicodeEncodeError → 漏了 PYTHONIOENCODING=utf-8
✗ 某项红 → 按提示补 frontmatter / 索引 / 快速开始块
```

### 完整步骤

1. 列出当前会话可用工具 → 与文档「默认挂载/opt-in」对照
2. 文档说可用但工具不在清单 → 该能力**没挂**，文档那套流程跑不了
3. 工具在清单 → 再看它有没有硬前提（源码构建 / 额外进程 / 反代 TLS）
4. 结论写回本页，不写进 `MEMORY.md`（那里只放硬规则）

---

## 一、结论速览

| 能力 | 文档口径 | 本部署实际 | 判定 |
|---|---|---|---|
| **沙箱与权限** | 三档 preset 打包 sandbox mode + approval | 已实测：受限令牌致 `pwsh` 起不来 `0xC0000142`，非沙箱即正常 | ✅ **已用它解释并解决真问题** |
| **目标自动推进**（`create_goal` 等） | goal-round-driver 同会话续推 | 工具在清单，可用 | ✅ **可用** |
| **workflow / subagent** | JS 编排扇出子 Agent | 工具在清单，可用 | ✅ **可用，适合批量上品** |
| **ralph**（换新 agent 迭代） | 文档整节在讲 | **工具不在清单** | ❌ 用不了 |
| **会话检索**（`session_search`） | 能力缝默认挂、工具 opt-in | **工具不在清单** | ❌ 未挂，要改配置 |
| **定时调度** | 会话内持久提醒 | **工具不在清单** | ❌ 未挂，且不是 cron |
| **MCP 长期记忆** | 接 Reference Memory / Memorix / Engram | **需要源码构建**，本机是桌面打包版 | ❌ 前提不满足 |
| **Hooks 桥** | 兼容 Claude / Codex 的 shell 钩子 | 本机没用过 shell 钩子 | ❌ 无迁移需求 |
| **Webhook** | 外部事件 → 建根 Session | 出厂不挂，需自写规则插件 + TLS 反代 | ⚠️ 成本高于收益 |

---

## 二、为什么"实际"这列可信

文档反复写「默认挂载 / opt-in / 出厂不挂」。**我手上的工具清单本身就是这个部署的实测结果**——挂了什么就一定列在清单里，没挂就调不到。

| 文档说 | 清单里 |
|---|---|
| `session-query-sqlite` 默认挂，`tool-session-query` **opt-in 出厂不挂** | 无 `session_search` 系列 → **吻合** |
| `schedule` **默认未启用**，需 `--patch` 启用 | 无 `schedule_create/list/delete` → **吻合** |
| `tool-workflow` / `tool-goal` / `subagent` 在 base 组合 | `workflow` / `create_goal` / `subagent` 全在 → **吻合** |
| `tool-ralph` 是独立插件 | 工具清单里**没有** `ralph` → 该组合未挂 |

> 这条判据可复用：**想确认某项 DSH 能力在不在，先看工具清单，别先改配置。**

---

## 三、逐项评估

### 3.1 沙箱与权限（唯一已实证的一项）

文档把我们踩的坑解释清楚了，且有两条**修正了我原来的判断**：

- Windows 后端是 **ACL restricted-token runner**，`enforcement` 恒为 `partial`，**只限制写、读永远放行**
- `danger-full-access` 下 `bash/pwsh/fs-sandbox` 会**短路**，直接委托底层执行器 —— **不是"还被沙箱兜着"**
- 受限模式没有可用后端时 **fail-closed 抛 `SANDBOX_UNAVAILABLE`，绝不裸跑**

⚠️ **如实修正**：我 2026-11-15 曾怀疑"文件系统有读不到的地方"。按文档，**读不受限**，`fs-sandbox` 每个 mode 都放行读。当时 `C:\Users` 下 glob 空结果属于**模式/深度问题，不是沙箱拒绝**。这条别再当成沙箱症状。

⚠️ **文档未覆盖的失败形态**：我们遇到的是 `0xC0000142`（进程初始化失败），**不是**文档写的 `SANDBOX_UNAVAILABLE`。说明后端"能启动"但 `pwsh` 进程本身起不来。见 [[经验-踩坑手册]] §A。

### 3.2 会话检索

- 只检索 **DSH 自己的会话日志**；跨会话访问要求 `cwd` **精确相等**
- FTS5 `unicode61` 是 **token 召回，不是子串**（`AI` 匹配不到 `BRAID`）
- 索引默认 `path: ':memory:'`、`openAt: first-search` → **进程本地、临时**

🔴 **首页写"跨 dsh、Codex、Claude Code、pi、OpenCode 检索"，但本篇正文只讲 DSH 自己的日志。**跨端能力应来自插件（`dsh-external/dsh-session-search`），不是内置能力 —— 首页那句话会误导，别拿它当"四端记忆统一"的方案。

### 3.3 MCP 长期记忆

三个后端（Reference Memory / Memorix / Engram）都要求：构建好的**源码树** + overlay `.cordis.yml` + `pnpm dsh web --patch`。本机是**桌面打包版**（源码在 `app.asar` 里），前提不满足。

即便搭起来，Reference Memory 也是**子串匹配、无语义检索、无冲突解决、无遗忘策略**。

> **结论：不动。** 现有 SSOT 模型（Obsidian 权威 + `sync-memory.sh` 单向同步 + sops 加密）比这套 MCP 记忆更成熟，接进来是降级。

### 3.4 Hooks 桥

只在"**已有** Claude/Codex `hooks.json` 想兼容"时才有意义；新写的东西文档明确说应该做 native 插件。本机没用过 shell 钩子 → 无迁移需求，跳过。

### 3.5 定时调度

默认未启用。即便启用，两条硬限制让它当不了定时任务：

- 提醒**只投递到原会话**，进程关闭或会话 cold 就**暂停计时**
- 文档原话：**"不是系统通知或跨会话常驻 cron"**

> `README` 里"GitHub 定时任务不监听上品完成事件"那个缺口，**这个能力补不上**。

### 3.6 Webhook

边界很清楚，也很窄：

- 唯一内置动作 = **创建根 Session**；没有"调工具""回写 GitHub"这类动作
- **fire-and-forget**：无队列、无重试、**无去重**、无崩溃重放、无完成回调；`202` **不代表**匹配成功或执行完成
- 要自写规则插件（Host 进程内受信任代码）+ 签名校验 + TLS 反代 + 隔离端口

> 想做"上品完成自动触发同步"，得自己写规则插件并自己做幂等——成本高于收益，**暂不做**。
> 若将来做，先记住：**它只负责起会话，不负责保证执行。**

### 3.7 目标自动推进 / workflow / subagent（真正能用的三个）

| 机制 | 关键事实 | 对我们的用法 |
|---|---|---|
| **goal-round-driver** | 同会话续推，复用 KV cache；每轮入队前 `sessions.flush()` 做**持久检查点**，检查点失败即 `disarm()` 绝不带病推进 | 长链路多档 SKU 校验、需要中途重启也接得上的任务 |
| **round 上限** | `maxGoalRounds` 到顶自动 `block`（`round-limit`）；人类消息**不计入**上限 | 跑批要设上限，别让它无限推 |
| **自报 blocked** | 目标轮次下至少 **3 个 admit 轮次**才能自报 blocked，否则机械拒绝 `GOAL_TOOL_BLOCK_THRESHOLD` | 别指望第一轮就"卡住并停下" |
| **workflow** | 模型写 JS 编排脚本扇出子 Agent；每次运行**新建 worker thread，无池化**；`node:vm` **不是安全隔离边界** | 多个 pno 并行走建品/上品 |
| **subagent** | 一两个委派用它，**别上 workflow**（文档明确） | 单篇笔记核实、单次抓取 |

> `ralph` 文档篇幅很大，但**本部署没挂这个工具**，不用深究。

---

## 四、对现有 SOP 的三条实际影响

1. **上品批量可以并行化**：多 pno 走 `workflow` 扇出，比串行跑 `create_from_pno.py` 省时。但 `maxTotalAgents` 有上限，且 worker thread 每次新建，**别一次塞太多**。
2. **权限档位要当"开关"看**：选 `danger-full-access` = **真的没有文件边界**，不是"仍然被兜着"。跑线上写操作（阿奇索 deploy）时保持这一点在心里。
3. **沙箱故障排查顺序**：先看退出码。`0xC0000142` → 沙箱挡的，换非沙箱；`SANDBOX_UNAVAILABLE` → 后端不可用，按文档装后端或改档位。两者解法不同，别混。

---

## 五、未验证 / 待办

- [ ] 跨端会话检索插件（`dsh-session-search`）到底能不能读 Codex / Claude Code 历史 —— **未核**，需装后实测
- [ ] `workflow` 在阿奇索批量上品的实际收益 —— 未跑过，属推测
- [ ] 本机 DSH 版本号 —— 源码在 `app.asar` 内读不出，站点标 `0.1.5-alpha.1`，**桌面版是否同版未确认**
- [ ] `C:\Users` 下 glob 空结果的真实原因 —— 排除沙箱后仍未定位

---

## 🔗 相关

- [[经验-踩坑手册]] —— 沙箱 `0xC0000142` 与 `check_vault.py` 编码坑
- [[本机环境档案]] —— 本机工具链实际位置
- [[记忆-回写规范]] —— 什么该写、写哪里
- [[长期记忆]] —— 索引
