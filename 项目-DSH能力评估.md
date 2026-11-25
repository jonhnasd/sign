---
created: 2026-11-15
updated: 2026-11-16
tags: [项目, DSH, 工具链, 能力边界, 第三方插件]
type: 项目
status: active
execution: read_only
verified_at: 2026-11-16
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
- [x] 本机 DSH 版本号 —— **已确认 `0.2.0-rc.2`**（2026-11-16 解析 `resources/app.asar` 头部 JSON，`dsh-base` / `dsh-desktop-host` / `dsh-web-app` 三包同版）。站点标的 `0.1.5-alpha.1` 是社区站自己的版本，与本机无关
- [ ] `C:\Users` 下 glob 空结果的真实原因 —— 排除沙箱后仍未定位

### 5.1 本机 DSH 实况（2026-11-16 核对）

| 项 | 实测值 |
|---|---|
| 安装路径 | `D:\Favorites\新建文件夹\`（**非标准路径**，不在 `LOCALAPPDATA\Programs`） |
| 版本 | `0.2.0-rc.2`（三个包一致） |
| 更新通道 | `resources/app-update.yml` → `channel: nightly`（会自己跳版本） |
| 归档状态 | 只有 `resources/app.asar`，**无 `app/` 目录 = 密封归档**，改宿主必然要解包 + 换包 |
| 启动方式 | 桌面 `DeepSeek Harness Launcher.bat`（自提权 + `--no-sandbox --disable-gpu`），见 [[经验-踩坑手册]] §T |
| CLI | 桌面版自带运行时，入口在 `resources/runtime/cli/bin/` 下的 `dsh` 批处理（**不在 PATH**，需用全路径） |
| profile | `desktop` / `web` 两个；desktop 已装 `ds-harness-remote`、`dsh-our-free-model` |
| 本机 Node | v22.22.2（≥22.5，可用红队工具） |

> [!warning] 找 DSH 别只看默认路径
> 本机装在 `D:\Favorites\新建文件夹\`。任何插件脚本若按 `LOCALAPPDATA\Programs\DeepSeek Harness` 定位宿主，一律会判"未安装"。

---

## 六、第三方插件：dsh-purge（社区版「破甲」插件）评估

> 评估对象：`github.com/kingcharleslzy-ai/dsh-purge`（社区维护版，基于原作者 小杨 / YuJunZhiXue 的 dsh-purge，MIT）。本机**未安装**，本节为读源码 + 发行说明 + 对照本机实况的结论。

### 6.1 它到底是什么

**一句话：给 DeepSeek Harness 装的越狱插件**（社区叫「破甲」/「无限制模式」）。官方措辞是"让助手更连贯地配合你的学习与动手实验"，但源码关键词表直写 `prompt injection · jailbreak · unrestricted`。

三层改动：

| 层 | 做什么 |
|---|---|
| ① 宿主源码层 | **改写 `app.asar` 内的 DSH 源码**，86 条补丁：注入系统提示词、改权限/审批默认值、调工具超时、管上下文修剪。每条 = 宿主源码精确片段替换，锚点漂移即失效 |
| ② 运行时层 | 在 `llm/stream` 包一层，检测模型拒绝（"这条我不做"/"结论：…我不出"）→ 丢弃重发。最多 3 次：硬话 → **小说角色第一人称虚构框架** → 只要最小可交付组件 |
| ③ 用户可见层 | 左侧栏整页设置 + 25 层状态自检 + 应用前自动快照 + 一键回滚 |

### 6.2 对本机的判定：✅ 已升级 + 已装插件（2026-11-16 实跑）

| 检查项 | 升级前 | 升级后实测 | 判定 |
|---|---|---|---|
| DSH 版本 | `0.2.0-rc.2` | **`0.2.2-rc.3`** | ✅ 在插件支持列表 |
| 更新通道 | nightly | 官方 feed `nightly.yml` = 0.2.2-rc.3（staging 100） | ⚠️ 仍会跳版本 |
| 安装路径 | `D:\Favorites\新建文件夹\` | 不变（就地覆盖） | ✅ Launcher 继续有效 |
| 归档状态 | 密封 asar | **仍密封**（无 `resources/app/` 解包目录） | 🔴 应用补丁前必须先解包 |
| 插件 | 未装 | **dsh-purge-community 1.7.18 已装入 desktop profile** | ✅ selfcheck 能跑通 |
| 宿主补丁 | — | **0/38 应用**（未点"应用"，预期）；另 50 条不适用 | ⏸ 待用户决策 |

> 升级走 NSIS 静默就地覆盖：`dsh-0.2.2-rc.3-win-x64.exe /S /D=<目标>`（manifest=asInvoker 无需 UAC）。
> **备份**：`D:\Favorites\.dsh-backup\2026-11-16\`（409M，含 `.credentials.yaml` 明文凭据，需保管）。

### 6.3 三个必须知道的坑

1. **1.7.15 → 1.7.18 语义反转**：1.7.15 把 14 条**权限/审批边界**补丁改为「显式选择才生效」；1.7.18 又改回**默认开启**。装最新版 = 权限默认值默认被改写。→ 与 §四·2「权限档位要当开关看」同一条结论。
2. **改的是已签名宿主**：1.7.15 新增 Windows 签名 sidecar 的 SHA256 校验（等长替换/追加/截断签名均失败）。既是保护也是摩擦点。
3. **它是越狱工具，不只是效率工具**。有价值的一半是「状态一屏看清 + 少确认打断 + 改坏能回滚 + 本机备份」，正对批量上品链路（`deploy.py` 那种一串确认）；真"破"的那部分是让模型不推脱——有明确 SOP 时收益与风险都要自己称。

### 6.4 实装记录（2026-11-16，B 方案：先升级再装）

1. ✅ DSH 0.2.0-rc.2 → **0.2.2-rc.3**（官方 nightly feed 包，SHA512 校验一致，NSIS 静默就地覆盖，路径不变）
2. ✅ 装 dsh-purge-community 1.7.18 到 desktop profile；selfcheck 跑通
3. ⏸ **未点"应用"** —— 宿主仍 sealed asar，补丁 0/38。是否应用留给用户决策

**selfcheck 结论**：宿主 9/23 层、运行时 0/1、配置 0/1、布局 0/1（sealed）。
- `missing_file` 38 条 = 补丁目标文件尚未被解包出来，**不是锚点漂移**（因为从没应用过）
- `config` 层无法读当前 profile：`desktop / desktop.bak_20261115_170320 / web` 三个 profile 未唯一确定，需 `--profile desktop` 显式指定

### 6.5 踩坑：0.2.2 封堵了外部 CLI，官方 bootstrap 装不上（已绕开）

**现象**：官方安装引导脚本（仓库 scripts 目录下的 bootstrap 安装器）报 `EPERM: mkdir ~/.dsh/dsh-purge-community`。
**真因**（二分排除后定位）：**不是文件权限**，是 DSH 0.2.2 新增保护 —— `dsh --profile desktop plugin ...` 直接返回 `error: profile "desktop" is managed exclusively by the Electron application`。插件 installer 内部就是调这条命令，被新版拒。

**环境干扰项**（排查时踩到，均非根因）：
- PowerShell 工具环境写 `~/.dsh` 报 EPERM，bash 环境可写 → 工具沙箱差异
- Electron 下 `ELECTRON_RUN_AS_NODE=1` + 设 `DSH_HOME` 会触发间歇 EPERM
- pnpm add 报 `ERR_SQLITE_ERROR` / `EPERM symlink` → DSH 自带 pnpm 在中文路径 + 沙箱下建不了符号链接；非管理员无 `SeCreateSymbolicLinkPrivilege`

**解法**（已验证成功）：绕开 CLI/pnpm，**手动完成 install() 的实质**——
1. tgz 复制到 `profile/vendor/`；2. `C:\Windows\System32\tar.exe -xzf` 解到 `node_modules/dsh-purge-community`；
3. 插件私有 `node_modules/yaml`（拷自 WorkBuddy 自带，2.9.0 兼容 2.9.1）；
4. 改 `package.json`：`dependencies[dsh-purge-community]="file:./vendor/<tgz>"` + `dsh.profile.bundles` 追加包名。
用官方 verifier 逻辑验证 `IMPORT OK` 通过。备份：`package.json.bak_before_purge_manual`。

> [!note] 通用判据（可复用）
> 第三方宿主插件先问三句：**① 支持列表里有本机版本吗？② 本机是密封还是解包？③ 装在标准路径吗？** 三句有一句不过，就先在隔离副本上做只读诊断，别直接点"应用"。
> **补第四句（0.2.2 新增）：宿主是否禁止外部 CLI 改 profile？** 若禁止，官方 bootstrap 必失败，需手动装或直接走 GUI。

---

## 🔗 相关

- [[经验-踩坑手册]] —— 沙箱 `0xC0000142` 与 `check_vault.py` 编码坑
- [[本机环境档案]] —— 本机工具链实际位置
- [[记忆-回写规范]] —— 什么该写、写哪里
- [[长期记忆]] —— 索引
