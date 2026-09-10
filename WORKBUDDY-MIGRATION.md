# WorkBuddy 技能迁移工作区

> **本文件在 `workbuddy` 分支上，不合并回 `main`。**
> `main` 保持「Claude Code / Codex / Cursor 三端通用」的形态；WorkBuddy 有专属契约，单独维护。

## 为什么单独拉分支

WorkBuddy（腾讯，2026-09-02 开放平台上线）的 Skill 虽然基于同一套 **Agent Skills 标准**，但有一层自己的硬约束。这些约束**和现有三端不完全兼容**，混在一起会互相污染：

| 维度 | Claude Code / Codex / Cursor | WorkBuddy |
|---|---|---|
| frontmatter 字段 | 宽松，额外字段被忽略 | **只认 5 个**：`name` / `description` / `license` / `allowed-tools` / `metadata` |
| `allowed-tools` | 可选 | **安全审查核心项**，缺失影响过审 |
| 安装路径 | `~/.claude/skills/`、`~/.codex/skills/` | `~/.workbuddy/skills/`，项目级 `.workbuddy/skills/`（项目级优先） |
| 变量占位符 | `${CLAUDE_SKILL_DIR}` | `${CODEBUDDY_SKILL_DIR}`（并兼容 Claude 别名）|
| 安全分级 | 无 | **P0 / P1 / P2** 三级；P0 硬禁止 |
| 分发 | 自建 marketplace / 官方目录 | **SkillHub**（审核 3–7 工作日） |
| 付费 | 无 | **SkillPay**（定价权+收款权归开发者） |

> ⚠️ 上表来自公开报道与社区文档的转述，**官方文档站被网络策略拦截，未能取得原文核对**。
> 动手前请登录 `open.WorkBuddy.cn` 核对 frontmatter 白名单与 P0 名单。

## 迁移清单

### 1. frontmatter 改造（必做）

四个技能当前字段全部超出白名单：

| 技能 | 现有字段 | 需处理 |
|---|---|---|
| `agent_harness` | name, description, **version, author, tags** | 3 个非法 |
| `multi-agent-research` | name, description, **version, author, tags** | 3 个非法 |
| `smart-loop` | name, description, **version, tags** | 2 个非法 |
| `tech-reserve-finder` | name, description, **version, author, tags** | 3 个非法 |

改造方式：把 `version` / `author` / `tags` 收进 `metadata` 下。

```yaml
---
name: smart-loop
description: ...
license: MIT
allowed-tools: Read Write WebFetch WebSearch
metadata:
  version: 6.1.0
  tags: [loop, 任务分解, 量化执行]
---
```

### 2. 补 `allowed-tools`（必做）

当前四个技能一个都没写。这是 SkillHub 安全审查的核心项——不写可能过不了审，或装上去调不动工具。

纯指令型（`smart-loop`、`tech-reserve-finder`）按实际需要列 `Read` / `Write` / `WebFetch` / `WebSearch` 即可；`agent_harness` 若要保留 Python 调用路径，需显式列 `Bash`。

### 3. P0 红线说明（必做，防误判）

`agent_harness/core/sentinel.py:43` 含以下字符串：

```
"rm -rf /", "dd if=", "mkfs.", ":(){ :|:& };:", "> /dev/sda"
```

**这是自研的安全哨兵在拦截这些模式，属防御代码，非违规代码。**
但自动化扫描按字面命中，会被判 P0。提交前必须在 README 中显式说明，必要时提供 `tests/test_unit.py:896` 的测试用例作为证据。

### 4. 目标与策略

**建议先只迁两个纯指令型技能**（`smart-loop`、`tech-reserve-finder`），理由：
- `agent_harness` 依赖 Python 3.10+ 与 Claude Code 适配器层，在 WorkBuddy 上跑不通完整链路
- `multi-agent-research` 的 `workflow.js` 依赖 Claude Code Workflow 引擎，**在 WorkBuddy 上不是可执行技能**

### 5. 披露边界（未决）

`tech-reserve-finder` 的 4 个 A 级案例，此前已在公开仓库曝光过一次。
上 SkillHub 意味着进入国内高可达渠道，**暴露面大于 GitHub**。此项需在提交前单独确认。

## 发布路径

```
个人实名认证（身份证 + 手机号 + 邮箱 + 扫脸，约 3 分钟）
  → 完善开发者主页（头像 / 20–120 字简介 / 联系方式）
  → 上传 SKILL.md，填写技能介绍
  → 安全扫描 + AI 审核 + 人工抽检
  → 上架（审核 3–7 个工作日，邮件通知）
  → 后台查看安装量 / 使用量 / 评分
```

## 待办

- [ ] 核对官方 frontmatter 白名单与 P0 名单（须登录 open.WorkBuddy.cn）
- [ ] frontmatter 改造（4 个技能）
- [ ] 补 `allowed-tools`
- [ ] P0 误判说明写入 README
- [ ] 决定 `tech-reserve-finder` 是否上架
- [ ] 实测安装：`~/.workbuddy/skills/<slug>/` 能否正确加载
