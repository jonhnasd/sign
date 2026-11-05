---
created: 2026-11-05
updated: 2026-11-05
tags: [索引, 架构说明]
type: 索引
status: active
---
# 📚 Obsidian 记忆库

> **唯一权威源（SSOT）**。所有 AI 工具的长期记忆都从这里读。
> 库路径：`C:\Users\Administrator\Desktop\obisidian\obisidian\`

---

## 一、架构

```
                        干活 / 决策
                            ↓
              ┌─────────────────────────┐
              │   Obsidian 库（本目录）  │  ← 唯一权威源
              └─────────────────────────┘
                   ↓            ↓
        ┌──────────────┐   ┌──────────────┐
        │  明文可读     │   │   加密存放    │
        │ 13篇专题笔记  │   │ secrets/     │
        │ 身份与记忆/   │   │ (sops+age)  │
        └──────────────┘   └──────────────┘
                   ↓            ↓
        ┌────────────────────────────────────┐
        │  各 AI 工具读取                     │
        │  WorkBuddy  ← 脚本同步（单向）      │
        │  Claude Code ← 直接读本库           │
        │  Codex       ← 直接读本库           │
        │  人 / 手机   ← Obsidian 同步        │
        └────────────────────────────────────┘
```

---

## 二、目录结构

| 路径 | 内容 | 加密 |
|---|---|---|
| `长期记忆.md` | **索引 / MOC** —— 任何任务先看这个 | — |
| `本机环境档案.md` | 硬件 / 系统 / 工具链 / 网络限制 | — |
| `经验-踩坑手册.md` | 坑与解法全量（按节号定位） | — |
| `记忆-回写规范.md` | 读写规则 + 完整性检查器 | — |
| `项目-*.md` | 各项目专题方案 | — |
| `操作-*.md` | 各操作流程手册 | — |
| **`身份与记忆/`** | MEMORY.md / SOUL / IDENTITY / USER | — |
| **`secrets/`** | 货源平台凭据 | ✅ **sops + age** |
| `.sops.yaml` | SOPS 配置（age 公钥，公钥非敏感） | — |
| `.gitattributes` | 标记 SOPS 文件（diff 不误判二进制） | — |
| `最近变更.md` | **自动生成**的变更历史视图（git log 驱动） | — |
| `.gitignore` | 排除 age 私钥、明文源文件、本地缓存 | — |

---

## 三、身份与记忆/（用户级记忆进库）

| 文件 | 作用 | 谁在用 |
|---|---|---|
| `MEMORY.md` | 硬规则 / 环境要点 / 沟通偏好 / 运营铁律 / 库速查表 | WorkBuddy（自动注入）+ Claude + Codex |
| `SOUL.md` | 助手人格设定 | 同上 |
| `IDENTITY.md` | 助手身份记录 | 同上 |
| `USER.md` | 用户档案 | 同上 |

### 同步机制：**库 → 本地（单向）**

```
C:\Users\Administrator\.workbuddy\tools\crypto\sync-memory.sh
```

- 库是权威源，改记忆**只改库里**
- 脚本把库里的 `身份与记忆/*` 同步到 WorkBuddy 用户目录（供自动注入）
- **凭据段特殊处理**：库里是指引（真值已抽离加密），同步时用 sops 解密把**真值表补回本地**
  → 本地能用明文，仓库里只有密文

```bash
bash C:/Users/Administrator/.workbuddy/tools/crypto/sync-memory.sh          # 同步
bash C:/Users/Administrator/.workbuddy/tools/crypto/sync-memory.sh --check  # 只查差异
```

---

## 四、secrets/（加密凭据）

| 文件 | 内容 |
|---|---|
| `credentials.sops.yaml` | **密文**（值 → `ENC[AES256_GCM,...]`，键名结构明文） |
| `.sops.yaml` | SOPS 配置，记录 age 公钥 |

### 工具位置

```
C:\Users\Administrator\.workbuddy\tools\crypto\
├─ sops.exe            3.13.3
├─ age.exe             1.2.1
├─ age-keygen.exe      1.2.1
├─ age\keys.txt        ★ age 私钥（绝不进仓库）
└─ sync-memory.sh      库 → 本地同步脚本
```

### 常用命令

```bash
# 解密查看
SOPS_AGE_KEY_FILE="C:/Users/Administrator/.workbuddy/tools/crypto/age/keys.txt" \
  "C:/Users/Administrator/.workbuddy/tools/crypto/sops.exe" --decrypt \
  "C:/Users/Administrator/Desktop/obisidian/obisidian/secrets/credentials.sops.yaml"

# 改值后重新加密（先编辑 credentials.yaml，再 encrypt）
```

### ⚠️ 铁律

- **age 私钥绝不进仓库**（`.gitignore` 已兜底，但也要自己注意）
- 私钥丢了 = 密文永久无法解密 → **务必另存一份到云盘/密码管理器**
- 凭据只用于本地调用，**不外传**

### 🔑 换设备恢复流程（照着做，一步别漏）

**需要准备两样东西**：① 这个仓库 ② age 私钥备份

```bash
# ── 1. clone 仓库 ──
git clone git@github.com:jonhnasd/obsidian-vault.git
cd obsidian-vault

# ── 2. 装工具（age + sops）──
#    到 https://github.com/FiloSottile/age/releases 和
#       https://github.com/getsops/sops/releases 下载对应平台二进制
#    放到 C:\Users\<你>\.workbuddy\tools\crypto\

# ── 3. 恢复 age 私钥 ──
#    把云盘里的备份存成：
#    C:\Users\<你>\.workbuddy\tools\crypto\age\keys.txt
#    （内容格式：
#      # created: ...
#      # public key: age1xxx...
#      AGE-SECRET-KEY-1XXXX...   ← 一整行，从 AGE-SECRET-KEY- 到结尾
#    ）

# ── 4. 验证能解密 ──
SOPS_AGE_KEY_FILE="C:/Users/<你>/.workbuddy/tools/crypto/age/keys.txt" \
  "C:/Users/<你>/.workbuddy/tools/crypto/sops.exe" --decrypt \
  "secrets/credentials.sops.yaml"
# 能看到明文 appid/secret = 恢复成功

# ── 5. 装同步脚本 + 建 user 目录 ──
bash C:/Users/<你>/.workbuddy/tools/crypto/sync-memory.sh
```

**验证成功标志**：第 4 步能输出明文密钥、第 5 步报告「同步完成」。

> ⚠️ **公钥丢了也能找回** —— `credentials.sops.yaml` 里的 `sops.age[].recipient` 就是公钥。
> 但**公钥不能解密**，所以私钥备份是唯一途径。

---

## 五、Git 推送安全（两道闸）

| 闸 | 位置 | 作用 |
|---|---|---|
| **post-commit** | `.git/hooks/post-commit` | 库内 `身份与记忆/` 改动后**自动同步**到 user 目录 |
| **pre-push** | `.git/hooks/pre-push` | 推送前审计：age 私钥 / 明文凭据 / 真密钥 / JWT —— 命中即**中止推送** |

手动审计（不依赖 hook）：
```bash
bash C:/Users/Administrator/.workbuddy/tools/crypto/publish.sh <仓库名> --check
```

**首次推送前务必做一次换设备演练**（见上节第 4 步）—— 能提前发现 90% 的坑。

---


```bash
"C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" \
  "C:/Users/Administrator/.workbuddy/tools/adb/check_vault.py"
```

检查 7 项：索引覆盖 / 速查表覆盖 / 双链断链 / 敏感凭据 / daily log 超 30 天未蒸馏 /
**legacy 笔记是否加口径提示** / **frontmatter 完整性** / **库内口径交叉引用**。
退出码 `0` = 全通过。

### 重新生成「最近变更.md」

```bash
bash C:/Users/Administrator/.workbuddy/tools/crypto/gen-changelog.sh [天数]   # 默认 30
```

### 统一 frontmatter

## 六、写完必跑检查

```bash
"C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe" \
  "C:/Users/Administrator/.workbuddy/tools/adb/fix_frontmatter.py"
```

字段：`created / updated / tags / type / status`
`status` 语义：**active** 现行可照做 · **legacy** 历史留档（别照做业务决策）· **draft** 草稿 · **ref** 索引规则类

---

## 七、Git 同步

```bash
cd "C:/Users/Administrator/Desktop/obisidian/obisidian"
git init
git add -A
git commit -m "init: obsidian memory vault"
git remote add origin git@github.com:jonhnasd/<repo>.git
git push -u origin main
```

**推之前必查**：`git status` 里不能出现 `secrets/credentials.yaml`（明文）、`age/keys.txt`。

---

## 八、相关

- [[长期记忆]] —— 索引
- [[记忆-回写规范]] —— 读写规则
- [[经验-踩坑手册]] —— 坑与解法
