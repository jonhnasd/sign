# code/ · 阿奇索上品流水线核心代码

> 本目录是**知识库的代码配套**，与根目录的规则/操作笔记同源。
> 规则正文在库根（`身份与记忆/上品规则.md` 等），代码在这里。
> 最后同步：2026-11-15

## 这是什么

闲鱼 × 阿奇索上品流水线的核心实现：从供货商编号（pno）建草稿、发布、绑货源、
生成复刻主图、改价、16 项上线核验，以及配套的环境体检与文档一致性检查。

**只收录核心代码**（40 个文件 / 0.56 MB），不含：
- 一次性脚本（文件名带商品 ID 或日期，共约 58 个）
- 供应商前端打包产物（`js/`、`_umi.js` 等，共 7.8 MB 逆向分析用）
- 运行时快照（`sku_*.json`、`backup_*.json` 等，2600+ 个）
- 凭据与私钥

## ⚠️ 已知技术债：两个文件因含明文密钥未入仓

| 文件 | 问题 | 现状 |
|---|---|---|
| `v3_huafei.py` | 星芒/省省/卡密三家的 `app_id` + `secret` 硬编码在源码 | **未入库**；原件仍在 tools/ 下可运行 |
| `siquan.py` | 思券 `SECRET` 硬编码在源码 | **未入库**；原件仍在 tools/ 下可运行 |

这两个文件**不在本仓库**，因此 clone 后无法直接调用它们。
它们的正确修法是改成从 sops 加密凭据读取（`paths.py` 已能定位
`secrets/credentials.sops.yaml`），但**这需要改动仍在生产使用的代码**，
属于独立任务，未在 2026-11-15 一并处理。

其余脚本（`agiso_direct` / `alds_kit` / `deploy` 等）不依赖这两个文件。

## 目录结构

```
code/
├── tools/                  主链路与能力层
│   ├── deploy.py           一条龙 14 环节唯一入口
│   ├── create_from_pno.py  从货源编号建草稿 → 发布
│   ├── onepipe_guard.py    16 项上线核验
│   ├── onepipe_service.py  127.0.0.1:8788 薄包装端点
│   ├── paths.py            ★ 路径单一配置源（换机器只改这里）
│   ├── doctor.py           ★ 换机器体检
│   ├── preflight_env.py    深度自检（JSON，ready/fatal）
│   ├── verify_main_image.py★ 主图核验（区分机器项/需看图项）
│   ├── replica_main_image.py 复刻式主图生成
│   ├── alds_dict.py        货源字段/买家填写项识别
│   ├── agiso_direct.py     阿奇索接口直连
│   └── alds_kit/           能力层（contract/supplier/copy/media/main_image/item）
├── adb/                    知识库自身工具
│   ├── check_vault.py      结构检查（索引/双链/M1–M4/索引一致性）
│   ├── check_doc_code.py   ★ 文档↔代码一致性检查
│   ├── gen_tools_index.py  脚本索引生成器
│   └── secret_scan.py      推送前凭据扫描
└── tools/tests/            回归（run_golden / mutate_check）
```

## 三条命令

```bash
cd code/tools
export PYTHONIOENCODING=utf-8

python doctor.py          # 能不能跑、缺什么、怎么修（只读）
python preflight_env.py   # "ready": true 才能干活（只读）
python tests/run_golden.py # 期望 65 通过 / 0 失败
```

## 换机器

路径全部走 `paths.py`，优先级 **环境变量 → 自动探测 → 内置默认**：

| 环境变量 | 指向 |
|---|---|
| `DSH_VAULT` | Obsidian 库根 |
| `DSH_SOPS_BIN` / `DSH_AGE_KEY` / `DSH_CREDENTIALS` | sops 与 age 凭据（**必须成对**） |
| `DSH_WORKSPACE` / `DSH_KUAIPAO` / `DSH_BRIDGE_PORT` | 任务目录 / 生图 / 端口 |

设错不会被静默忽略：`paths.py` 标记 `env_bad`，`doctor.py` 直接报错。
详见库根 [[操作-换机器迁移清单]]。

## 硬闸（代码已实现）

| 闸 | 判据 |
|---|---|
| 利润率 | `price = round(cost/0.934, 2)`（6.6%） |
| SKU 成本 | >¥20 不上（=¥20 允许），可 spec 覆盖 `sku_cost_max` |
| 售价上限 | >¥150 不上 |
| 描述素材 | 详情 <60 字且未给 `--desc` → 中止 |
| 买家填写项 | 直充但推断不出 → 中止 |

永不进入买家文案：`限价`、到账时效承诺、「官方正品/授权」。

## 与知识库的关系

代码改了要同步验证两道检查器：

```bash
python adb/check_vault.py      # 结构：索引/双链/M1–M4/脚本索引一致性
python adb/check_doc_code.py   # 文档↔代码：签名/参数/模块/阶段
```

后者能抓「文档写的函数签名 ≠ 代码实际」——结构检查永远看不见这类漂移。
