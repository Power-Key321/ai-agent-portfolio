# WorkBuddy 技能迁移记录

> **本文件在 `workbuddy` 分支上，不合并回 `main`。**
> `main` 保持「Claude Code / Codex / Cursor 三端通用」的形态；WorkBuddy 有专属契约，单独维护。
>
> **上架操作指南见 [`workbuddy/README.md`](workbuddy/README.md)** — 本文只记录「改了什么、为什么」。

## 为什么单独拉分支

WorkBuddy（腾讯，2026-09-02 开放平台上线）的 Skill 基于同一套 **Agent Skills 标准**，但有一层自己的硬约束。这些约束和三端通用形态**不完全兼容**，混在一起会互相污染：

- frontmatter 有**固定的字段集合**（客户端读 6 个），多写的字段不会被解析
- `allowed-tools` **按逗号切分**，空格分隔在三端能跑、在这里会静默失效
- `allowed-tools` 是**安全审查核心项**，缺失影响过审
- 技能名规则是**小写字母 + 数字 + 连字符**，与 `agent_harness` 的下划线冲突

## 改了什么

### 1. frontmatter 对齐官方文档契约（4 个技能）

**直接源自 `open.workbuddy.cn/docs/skill`**（本机代理 49150 抓取后解析），不再依赖二手资料。

**必填**：`name` + `description`。其他 10 个字段均为可选。

**修正三轮此前的错误认知**：

| 此前的说法 | 文档/二进制实测 | 影响 |
|---|---|---|
| "只认 5 个字段" | 文档列 10 个可选；客户端二进制读 6 个（含 `when_to_use`），但**文档里 0 命中** | `when_to_use` 在文档里没出现 → 上传版删除 |
| "`allowed-tools` 用空格分隔" | 文档原文"多个用逗号分隔" + 客户端 `c.split(",")` | 全部改为逗号 |
| "display_name 放在 metadata 下" | 文档原文：`display_name` / `display_name_en` 是**顶级字段** | 移出 `metadata:` |
| "author / version 必须 metadata 嵌套" | 文档原文：`author` `version` 是**顶级字段** | 移出 `metadata:` |
| "有 P0/P1/P2 安全分级" | 文档本节 **0 命中** | 来自社区说法，文档原文不支持 |
| "正文 500 行 / 5000 token 硬上限" | 文档本节 0 命中 | 来自社区资料，未核对 |

最终 frontmatter 结构（`smart-loop` 为例）：

```yaml
---
name: smart-loop                                                # kebab-case，与目录名一致
description: 把多轮、周期长、中途可能失败的任务，拆成…            # 必填：一句话描述
description_zh: 长任务循环推进器 — 先用最少信息推断真实目标…     # 可选：中文短介绍
description_en: Long-Task Loop Driver — break a multi-round…    # 可选：英文短介绍
display_name: 长任务循环推进器                                  # 可选：用户看到的名字
display_name_en: Long-Task Loop Driver
allowed-tools: Read, Write, Edit, WebFetch, WebSearch           # 逗号分隔
version: 6.2.0
author: Bo Wang
license: MIT
---
```

各技能的 `allowed-tools`（**全部逗号分隔**）：

| 技能 | allowed-tools |
|---|---|
| `smart-loop` | `Read, Write, Edit, WebFetch, WebSearch` |
| `tech-reserve-finder` | `Read, Write, WebFetch, WebSearch` |
| `multi-agent-research` | `Read, Write, WebFetch, WebSearch` |
| `agent_harness` | `Read, Write, Bash` |

### 1b. 中文显示名

`name` 必须是 ASCII kebab-case（与目录名一致），**不能写中文**。中文名走三个官方字段：

| 字段 | 内容 |
|---|---|
| `display_name` | 中文显示名（用户在 SkillHub 列表页看到的名字） |
| `description_zh` | 简短中文介绍 |
| 正文 H1 | 中文名 |

对照：`smart-loop` → 长任务循环推进器；`tech-reserve-finder` → 跨产业技术平替发现器。

### 1c. `tech-reserve-finder` 案例脱敏

原始 11 个 A 级案例 → 公开 4 个。本轮进一步降"张扬"度：

- 去掉对抗色彩表述（卡脖子 / 受制于 / 追赶）
- 去掉无法证伪的强断言（"全球范围内几乎没人想到" → "公开材料中少见直接连接"）
- 去掉全部企业/院所点名，只留产业特征
- 去掉硬数字（10-50x / 全球唯一 / 全球独有）
- 「军工/重工」→「极端工况行业」
- 删除内部笔记引用 `[[中国全产业链…]]`
- **撤下**：高能材料药柱 → 固态电池（军工背景）
- **新增**：轨道交通牵引变流 → 大型数据中心供配电（全民用，零敏感）

完整分级表见 [`workbuddy/README.md`](workbuddy/README.md) §三。

### 2. `description` 补上触发条件（`smart-loop` / `tech-reserve-finder`）

原描述只说「是什么」不说「什么时候用」，模型难以判断该不该加载。已补「适用于…」段落。

### 3. `author` 字段统一

`Custom` → `Bo Wang`。

### 4. 上架集合的切分

| 技能 | 上架 | 原因 |
|---|---|---|
| `smart-loop` | ✅ | 单文件、纯指令、无 P0 模式 |
| `tech-reserve-finder` | ✅ | 单文件、纯指令、无 P0 模式 |
| `multi-agent-research` | ❌ | 真能力在 `workflow.js`，依赖 Claude Code Workflow 引擎，换平台跑不动 |
| `agent_harness` | ❌ | ① 依赖 Python 3.10+ 与 Claude Code 适配器层；② 名字含下划线违反命名规则，而**改名会破坏 `import agent_harness`**（目录名即包名） |

`agent_harness` 若将来要上，正确路径是**拆一个纯指令版另起目录名**（如 `agent-orchestration`），而不是把现有目录改名。

## 关于 P0 误判

`agent_harness/core/sentinel.py:43` 含一串危险模式字符串：

```
"rm -rf /", "dd if=", "mkfs.", ":(){ :|:& };:", "> /dev/sda"
```

**这是自研安全哨兵在拦截这些模式，属防御代码**（`tests/test_unit.py:896` 有对应测试用例佐证），但自动化扫描按字面命中会判 P0。

**由于 `agent_harness` 已不在上架集合内，此项不构成提交阻塞。** 上架的 2 个技能经全文扫描，无任何 P0 模式。
（若将来上架 `agent_harness`，需在技能介绍中显式说明并附测试用例。）

## 验证

```bash
bash workbuddy/pack.sh        # 产出 workbuddy/dist/{smart-loop,tech-reserve-finder}.zip
```

产物为 `dist/`，已在 `.gitignore` 中，不进版本库。
