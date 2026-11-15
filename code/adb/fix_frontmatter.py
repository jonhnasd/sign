# -*- coding: utf-8 -*-
"""
统一 Obsidian 库全部笔记的 frontmatter
- 保留已有字段与顺序
- 补齐缺失字段：created / updated / tags / type / status
- status 语义：active（现行可执行） / legacy（历史留档，别照做） / draft（草稿） / ref（索引/规则类）
"""
import io
import os
import re
import glob

VAULT = r"C:\Users\Administrator\Desktop\obisidian\obisidian"
TODAY = "2026-11-05"

# 逐文件指定：tags / type / status / created
SPEC = {
    "README.md":                        dict(tags=["索引", "架构说明"], type="索引", status="active", created="2026-11-05"),
    "欢迎.md":                          dict(tags=["模板"], type="模板", status="legacy", created="2026-09-23"),
    "长期记忆.md":                      dict(tags=["记忆", "索引", "MOC"], type="长期记忆", status="active", created="2026-09-23"),
    "本机环境档案.md":                  dict(tags=["环境", "本机", "硬件"], type="环境档案", status="active", created="2026-09-23"),
    "经验-踩坑手册.md":                  dict(tags=["经验", "踩坑", "手册"], type="经验手册", status="active", created="2026-09-23"),
    "记忆-回写规范.md":                  dict(tags=["记忆", "规范"], type="规则", status="active", created="2026-09-23"),
    "项目-135编辑器.md":                 dict(tags=["项目", "编辑器", "桥接", "135编辑器"], type="项目笔记", status="active", created="2026-09-23"),
    "项目-edge-bridge.md":              dict(tags=["项目", "浏览器", "桥接"], type="项目笔记", status="active", created="2026-09-23"),
    "项目-qcqcq货源抓取.md":             dict(tags=["项目", "爬虫", "货源站"], type="项目笔记", status="legacy", created="2026-09-23"),
    "项目-sqqy88商品抓取.md":            dict(tags=["项目", "协议逆向", "抓取", "CRMEB", "uni-app"], type="项目", status="active", created="2026-10-03"),
    "项目-手机接入工具链.md":             dict(tags=["项目", "Android", "ADB", "Shizuku", "FIRERPA", "MCP", "通用化"], type="项目", status="active", created="2026-11-04"),
    "项目-手机调试能力链.md":             dict(tags=["项目", "Android", "ADB", "Shizuku", "FIRERPA", "MCP", "MITM"], type="项目", status="active", created="2026-11-04"),
    "操作-阿奇索上品一条龙.md":           dict(tags=["操作", "阿奇索", "闲鱼", "上SKU", "deploy"], type="操作", status="active", created="2026-11-04"),
    "操作-阿奇索宝贝SKU设置.md":         dict(tags=["操作", "阿奇索", "闲鱼", "SKU", "规格", "价格"], type="操作", status="active", created="2026-09-23"),
    "操作-上SKU直连思券货源(手机通道).md": dict(tags=["操作", "阿奇索", "思券", "上SKU", "手机通道"], type="操作", status="active", created="2026-11-05"),
    "身份与记忆/MEMORY.md":   dict(tags=["记忆", "用户级", "硬规则", "SSOT"], type="用户级记忆", status="active", created="2026-09-23"),
    "身份与记忆/SOUL.md":     dict(tags=["身份", "人格"], type="身份文件", status="active", created="2026-09-23"),
    "身份与记忆/IDENTITY.md": dict(tags=["身份", "助手"], type="身份文件", status="draft", created="2026-09-23"),
    "身份与记忆/USER.md":     dict(tags=["身份", "用户档案"], type="身份文件", status="draft", created="2026-09-23"),
}

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def parse_fm(text):
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def split_kv(block):
    """解析 frontmatter 块为 [(key, raw_value)]，保留原始格式"""
    out = []
    for line in block.split("\n"):
        if not line.strip():
            continue
        if re.match(r"^\s+\S+:", line) or re.match(r"^\s+-\s", line):
            # 属于上一个 key 的续行
            if out:
                out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
                continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if m:
            out.append((m.group(1), m.group(2)))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
    return out


def main():
    changed = []
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if d not in (".obsidian", ".git")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, VAULT).replace(os.sep, "/")
            spec = SPEC.get(rel)
            if not spec:
                spec = SPEC.get(fn)
            if not spec:
                print(f"  ? 无规格，跳过: {rel}")
                continue

            text = io.open(full, encoding="utf-8", errors="ignore").read()
            block, body = parse_fm(text)
            kv = split_kv(block) if block else []
            d = dict(kv)

            # 补齐缺失字段（不覆盖已有）
            if "created" not in d:
                kv.append(("created", spec["created"]))
            if "updated" not in d:
                kv.append(("updated", TODAY))
            if "tags" not in d:
                kv.append(("tags", "[" + ", ".join(spec["tags"]) + "]"))
            if "type" not in d:
                kv.append(("type", spec["type"]))
            if "status" not in d:
                kv.append(("status", spec["status"]))
            # 强制 status 用规格值（统一语义）
            kv = [(k, (spec["status"] if k == "status" else v)) for k, v in kv]

            new_fm = "\n".join(f"{k}: {v}".rstrip() for k, v in kv)
            new_text = f"---\n{new_fm}\n---\n{body}"
            if new_text != text:
                io.open(full, "w", encoding="utf-8", newline="\n").write(new_text)
                changed.append(rel)
                print(f"  ✓ {rel}")

    print(f"\n共处理 {len(changed)} 个文件")


if __name__ == "__main__":
    main()
