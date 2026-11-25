# AGENTS.md · 上品一条龙运行时入口

> 任何 agent 接手本目录前，**先读完本文件**（约 90 秒），再动手。
> 本文件是入口说明书，不是规则正文——规则正文在 Obsidian 库，见第 3 节。

---

## 1. 三条命令，先跑再问

```bash
cd "C:/Users/Administrator/WorkBuddy/2026-09-22-11-37-41/edge-bridge/tools"
export PYTHONIOENCODING=utf-8          # Windows PowerShell: $env:PYTHONIOENCODING='utf-8'

python doctor.py          # ① 换机器体检：能不能跑、缺什么、怎么修（只读）
python preflight_env.py   # ② 深度自检：首行 "ready": true 才能往下（只读）
```

**判据（不要靠感觉）：**

| 命令 | 看什么 | 不合格怎么办 |
|---|---|---|
| `doctor.py` | 退出码 0，且无 `✗` | `python doctor.py --fix-env` 拿到要设的环境变量 |
| `preflight_env.py` | `"ready": true`、`"fatal": []` | 读 `fatal` 里那一项，按 `doctor.py` 的提示修 |

**两个都绿了才允许碰线上。** 任何一个红，先修环境，不要试着「先跑跑看」。

---

## 2. 换机器 / 换用户名：只改一个文件

路径全部集中在 `paths.py`（单一配置源）。核心链路原本有 17 处写死
`C:\Users\Administrator\...`，已全部改为走 `paths.py`。

**优先级**：环境变量 → 自动探测 → 内置默认。

| 环境变量 | 含义 | 不设的后果 |
|---|---|---|
| `DSH_VAULT` | Obsidian 库根 | 找不到素材/凭据，货源查询与主图全断 |
| `DSH_SOPS_BIN` | sops 可执行 | 凭据解不开，无法登录供货商 |
| `DSH_AGE_KEY` | age 私钥 | 同上（**换机器最容易错的一项**） |
| `DSH_CREDENTIALS` | 加密凭据文件 | 同上 |
| `DSH_WORKSPACE` | WorkBuddy 任务目录 | 部分脚本找错根 |
| `DSH_PYTHON` | **指定解释器**（2026-11-15 新增） | `doctor.py` 无法对比「该用/在用」，换机器时最容易漏 |
| `DSH_KUAIPAO` | 快跑生图脚本（可选） | 少一种生图方式，不致命 |
| `DSH_BRIDGE_PORT` | 桥接端口（默认 8787） | 改了端口才需要设 |

**设错了不会被静默忽略**：`paths.py` 会记 `env_bad`，`doctor.py` 直接报 `✗` 并说明「环境变量指向不存在的路径，已回落」。这是刻意设计的——否则「以为配好了」是最难查的故障。

### 解释器为什么要单列（2026-11-15）

`doctor.py` 原本只报 `sys.version_info`，即「**你运行 doctor 用的那个 python**」。它永远绿——因为报告的是「当下碰巧是哪个」，不是「该用哪个」。换机器时真正会炸的是**体检的解释器 ≠ 实际跑批的解释器**。

现在 `paths.py` 显式解析 `CFG.python`，`doctor.py` 对比 `sys.executable` 与它，不一致直接打 `⚠️ 在用 X，该用 Y`。

> 本机实测：`...\python\versions\3.13.12\python.exe` 目录名是 3.13.12，**实际版本 3.13.14**。目录名与版本不符是既有事实，不影响功能，但别拿目录名当版本。

### 新 agent 从哪拿到这些

DSH 会加载**用户全局** `C:\Users\Administrator\.dsh\AGENTS.md`（任何工作目录都生效），它指向本目录。因为默认工作目录 `D:\Documents\deepseek-harness\default-workspace` 是空的、且向上没有 `.git` 标记，光靠项目级 `AGENTS.md` 不会被发现。

一键看当前解析结果：

```bash
python paths.py            # JSON：每项路径 + 来源（env/probe/default/missing）
python doctor.py --fix-env # 打印要设哪些环境变量
```

---

## 3. 规则与操作正文在 Obsidian 库（不要在本目录找）

本目录是**代码**。**规则、踩坑、操作流程**全在库内，必须先读再动手：

| 想知道什么 | 读哪篇 |
|---|---|
| 全部运营铁律（价格/档位/主图/填写项/发布闸） | `身份与记忆/上品规则.md` |
| 踩过的坑（**务必读，否则会重犯**） | `经验-踩坑手册.md` §A–§Y |
| 从货源编号建新品 | `操作-从货源编号新建宝贝.md` |
| 一条龙主流程（14 环节） | `操作-阿奇索上品一条龙.md` |
| **已上架商品只改一处**（标题/主图/价格） | `操作-阿奇索单阶段重入调用.md` |
| 库怎么维护、规则怎么登记 | `规则-知识库元约束.md` |
| **易店商品标题 / 描述文案怎么写**（共享号 / 链接直充） | `项目-易店共享号与链接直充文案库.md`（形态判据 + 10 条标题模板 + 2 套正文骨架 + 易店字段映射 + 3 个对标样本实测数据） |
| **抓闲鱼对标**（同行标题/描述/档位/浏览想要率） | `xyh_resolve_and_dump.py`（短链→卖家全店）/ `xyh_dump_items.py`（按 itemId）；抄之前先读文案库 §六「哪些不能抄」 |
| 全库索引 | `长期记忆.md` |

🔴 **`deploy.py --go` 不要用于「只改标题」这类返工**：它会重生主图、清掉 ⑨b 核验章、并留下旧主图。返工一律用 `操作-阿奇索单阶段重入调用.md` 里的单阶段调用。

---

## 4. 硬闸（代码已实现，不要绕过）

| 闸 | 判据 | 绕过方式（仅限确有理由） |
|---|---|---|
| 利润率 | `price = round(cost/0.934, 2)`（6.6%） | 无。`NO_LOSS` 保护 |
| SKU 成本 | 成本 >¥20 的档不上（=¥20 允许） | spec 里写 `sku_cost_max` |
| 售价上限 | 售价 >¥150 的档不上 | 无 |
| 描述素材 | 未给 `--desc` 且详情 <60 字 → 中止 | `--allow-default-desc` |
| 买家填写项 | 直充但推断不出填写项 → 中止 | `--recharge-types` |
| 主图档位 | 默认只展示最高档；单位混杂/并列 → 失败关闭 | `--main-image-sku-mode all` |

**永不进入买家文案**：`限价`、到账时效承诺、「官方正品/授权」类不可靠背书。

---

## 5. 改完代码要跑的四道验证

```bash
# 业务回归（在 tools/ 下）
python tests/run_golden.py        # 期望 65 通过 / 0 失败
python tests/mutate_check.py      # 期望 8 个变异 / 0 漏报
python _test_alds_kit.py          # 期望 0 diffs
python onepipe_guard.py --inspect --gid <商品ID>   # 期望 16 项全通过

# 知识库（任意目录）
python C:/Users/Administrator/.workbuddy/tools/adb/check_vault.py     # 结构
python C:/Users/Administrator/.workbuddy/tools/adb/check_doc_code.py  # 文档↔代码
```

后两个**都要跑**：`check_vault.py` 只证明「结构合格」，`check_doc_code.py` 才管「文档写的函数签名/参数/模块是否和代码一致」。

---

## 6. 常见故障对照

| 症状 | 原因 | 处理 |
|---|---|---|
| `doctor.py` 报 bridge ✗ | Edge 没开 / 扩展禁用 / 代理劫持 | 开 Edge + `edge://extensions` 启用；`curl` 必须加 `--noproxy '*'` |
| sops 解密失败 | age 私钥与加密文件不配对 | 换机器时最常见；确认拷的是同一对密钥 |
| `UnicodeDecodeError: 'gbk'` | 子进程输出含非 GBK 字节 | 已修（子进程统一 `encoding="utf-8", errors="replace"`）；新代码照此写 |
| 主图没换 / 旧图残留 | 只改了标题没重生主图 | 单阶段调 `phase_main_image` + `strip_template_images(gid, <旧URL>)` |
| 标题档位不对 | 用了货源名里的档位 | 走 `deploy._copy_title`，入口 `--title-sku-mode {highest,all}` |
| 草稿发布报「类目检查限制」 | 模板类目与商品不符 | 换模板线路重发；失败草稿用 `DeleteDraft` 清掉 |

---

## 7. 边界（不要越线）

- **无删除 API**：废弃商品壳子只能 Agiso 网页手工删，任何脚本都做不到。
- **主图逐字核验需要视觉能力**：`preflight_env.py` 明确声明不能代替。agent 看不了图时，主图这关只能标「待人工核验」，**不得声称已核验**。
- **并发无锁**：多个 agent 同时跑会互相覆盖 spec 与线上商品。动手前确认没有别的会话在跑。
- **`--dry` 只写 `spec_preview_<pno>.json`**，不覆盖生产 spec；这是 2026-11-15 修过的坑，别再改回去。

---

## 8. 已固化的提速命令 `fastlane.py`（2026-11-17）

> 这些步骤以前每次手工做，已确认「机械、可枚举、不需要判断」，所以固化。**先看这里，别再手工重做一遍。**

```bash
python fastlane.py add    --brand "UC网盘超级会员" --tier 1天 --label 手机号      # 一句话上品（默认预演）
python fastlane.py check  --gid <GID> [--gid <GID2>] [--fix]                    # 验收 + 自动返工
python fastlane.py new    --pno <PNO> --title "..." [--go]                      # 新建宝贝（默认预演）
python fastlane.py prep   --gid <GID> --pno <PNO> --name "..." --label 手机号     # 单件出图（2 秒）
python fastlane.py ship   --gid <GID> --png out_layered/<GID>_final.png          # 上传+清旧图+登记
python fastlane.py batch-prep --jobs jobs.json                                   # 多件并行出图
python fastlane.py batch-ship --jobs jobs.json                                   # 多件串行上线+统一验收
python fastlane.py title  "标题文本"                                             # 标题字节预算（≤90）
python fastlane.py attach --gid <GID>                                            # 混源参数 key 修复
```

**`check --fix` 只自动修机械项**：① 商品在线、⑪ 擦亮/售完上架、⑤ 直充 attach、清单外的残留旧图。
**不会替你动**：主图对不对（要看图）、描述写什么、SKU 改名（会重排 skuId）、换不换货源。

**主图出图走本地分层合成**（`compose_main_image.py` + `_fastlane_bg.py`，需 Pillow，`fastlane.py` 自动切 DSH 解释器）。生图 API `gpt-image-2.6` / `nano-banana-2-1k` 2026-11-17 起持续 503（分组无可用通道），**不要再试生图 API**，直接用本地合成。

---

## 8b. 批量建品 `batch_new.py`（2026-11-18）

> 一次环境检查 → 逐件一条龙 → 统一巡检。多件新建时用它，**别逐件手敲 `create_from_pno.py --go`**（每件都会重跑 preflight，且巡检不汇总）。

```bash
python batch_new.py 95425:15232:埋堆堆 95425:15234:埋堆堆    # 命令行：acct:pno:keyword
python batch_new.py --file items.txt                          # 配置文件（每行 acct:pno:keyword）
python batch_new.py 95425:15232:埋堆堆 --dry --skip-env       # 只预演
python batch_new.py --file items.txt --template-gid <13位ID> --account-label 手机号 --recharge-types 1
```

- **不并行**：并行会撞阿奇索 API 限流 + 草稿箱/标题竞争，**串行优先**。
- 每件独立 try/except：一件失败不影响后续，末尾统一巡检并汇总成败。
- 单件要单独覆盖 title/desc → 用配置文件行内 JSON。
- ⚠️ 主图档位跨单位时，`create_from_pno` 已自动切 `main_image_sku_mode=all`（2026-11-18 根治），不会再像 11-18 那样被预检拦停。

---

## 9. 🔴 重复三次 → 主动提议做成命令（2026-11-17 用户定）

> 用户原话：「**以后重复多次用的项目，记得提醒我做成命令提高速度**」

**这是 agent 的主动义务，不是等用户提。**

| 第几次做同一套操作 | 动作 |
|---|---|
| 第 2 次 | 记下来，不急着写代码（可能只是一次性需求） |
| **第 3 次** | **停下当前工作，主动提议**：「这套已经做了 3 次，要不要固化成命令？」 |
| 用户同意 | 当天实现 + 登记知识库 + 跑验证，不留半成品 |

- **提议必须带量化**：现在每次 X 分钟 → 固化后 Y 秒，否则用户无法判断值不值。
- **只固化机械步骤**：判断、核验、比价决策不固化，避免把错误自动化。
- **固化后必须登记**：写进本文件 §8 + `操作-*.md`，否则其他 agent 下次还是手工。
- 判据一句话：**这件事我下次还会再做一遍吗？会 → 就该是一条命令。**

正文见 [[操作层规范]] §八。
