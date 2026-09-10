# 安装 / Install

四个技能，三个工具，**装法只有一条：把目录复制到指定位置。**

> ✅ **Claude Code 上开箱即用。** 四个技能都符合 Claude Code 的技能约定（目录名 = `SKILL.md` 里的 `name`），复制进去即可生效——**不需要改文件名、改目录名或改任何配置**。
> 下面第一段命令装完，Claude Code 就能直接用了。

[中文](#中文) ｜ [English](#english)

---

<a id="中文"></a>
## 中文

### 一句话版本

**复制到两个目录，三个工具全覆盖。**

```bash
git clone https://github.com/Power-Key321/ai-agent-portfolio
cd ai-agent-portfolio

# ① Claude Code 和 Cursor 都读这里
mkdir -p ~/.claude/skills
cp -r agent_harness              ~/.claude/skills/agent_harness
cp -r multi-agent-research       ~/.claude/skills/multi-agent-research
cp -r tools/smart-loop           ~/.claude/skills/smart-loop
cp -r tools/tech-reserve-finder  ~/.claude/skills/tech-reserve-finder

# ② Codex 读这里
mkdir -p ~/.codex/skills
cp -r ~/.claude/skills/*         ~/.codex/skills/
```

只要 Claude Code，跑完 ① 就结束了。只想用 Codex，把 ① 的目标目录换成 `~/.codex/skills` 即可。Windows PowerShell 用这个：

```powershell
git clone https://github.com/Power-Key321/ai-agent-portfolio
cd ai-agent-portfolio
New-Item -ItemType Directory -Force "$HOME\.claude\skills", "$HOME\.codex\skills" | Out-Null
Copy-Item agent_harness, multi-agent-research "$HOME\.claude\skills\" -Recurse -Force
Copy-Item tools\smart-loop, tools\tech-reserve-finder "$HOME\.claude\skills\" -Recurse -Force
Copy-Item "$HOME\.claude\skills\*" "$HOME\.codex\skills\" -Recurse -Force
```

> ⚠️ **不要改目录名。** `agent_harness/` 既是技能目录、也是 Python 包目录——改名会让 `import agent_harness` 失败。四个目录名已经和各自的 `name` 字段一致，原样复制即可。

---

### 为什么是这两个目录

三个工具读的技能目录不一样，但**没有冲突**，所以复制两份最省事：

| 目录 | Claude Code | Codex | Cursor |
|---|---|---|---|
| `~/.claude/skills/` | ✅ 原生 | ❌ | ✅ 兼容读取 |
| `~/.codex/skills/` | ❌ | ✅ 原生 | ✅ 兼容读取 |
| `~/.cursor/skills/` | ❌ | ❌ | ✅ 原生 |

**所以：**
- 只用 Claude Code → 只装 `~/.claude/skills/`
- 只用 Codex → 只装 `~/.codex/skills/`
- 只用 Cursor → 装哪个都行
- 三个都用 → 两个都装

（Cursor 还会读 `~/.agents/skills/` 和 `~/.grok/skills/`，但上面两个已经够了，不用管。）

也可以只给**单个项目**装：把目录放进项目里的 `.claude/skills/` 或 `.codex/skills/`，效果一样，只对那个项目生效。

---

### 装完怎么用

| 工具 | 怎么触发 |
|---|---|
| **Claude Code** | 自动加载——描述匹配到 `SKILL.md` 里的 `description` 就会用上。也可以直接说 `/agent_harness <任务>` |
| **Codex** | 输入 `/skills` 查看已装载的技能，用 `$技能名` 显式调用 |
| **Cursor** | 自动加载，和 Claude Code 一样按 `description` 匹配 |

`SKILL.md` 的 `description` 写得好不好，决定了它会不会被自动用上——这是唯一需要理解的概念。

---

### 四个技能的实际可用度（说实话版）

| 技能 | Claude Code | Codex | Cursor | 依赖 |
|---|---|---|---|---|
| `tools/smart-loop` | ✅ | ✅ | ✅ | 无，纯指令 |
| `tools/tech-reserve-finder` | ✅ | ✅ | ✅ | 无，纯指令 |
| `agent_harness` | ✅ | ⚠️ 部分 | ⚠️ 部分 | Python 3.10+，先 `pip install -r requirements.txt` |
| `multi-agent-research` | ✅ | ❌ | ❌ | 需要 Claude Code 的 Workflow 引擎 |

两点说明：

- **`agent_harness`** 的 `SKILL.md` 会告诉 Agent 去 `python` 调用 `agent_harness.adapters.claude_code`。Codex 和 Cursor 没有这个 adapter，Agent 会读得懂规则、但跑不起来那套 Python 适配器层。三个工具都能读这个技能的**方法论**，只有 Claude Code 能跑通**完整链路**。
- **`multi-agent-research`** 的 `workflow.js` 是 Claude Code Workflow 引擎的脚本（确定性地派生上百个子 agent）。在 Codex / Cursor 里它只是一份可读的框架文档，**不是可执行技能**。

---

### 出问题了

| 现象 | 原因 |
|---|---|
| 技能没被自动加载 | 目录名和 `SKILL.md` 里的 `name` 不一致——按上面的命令原样复制不会出现这个问题 |
| Codex 里 `/skills` 是空的 | 装到了 `~/.claude/skills/`。Codex 不读那个目录，要装到 `~/.codex/skills/` |
| `agent_harness` 报 `ModuleNotFoundError` | 没装依赖，或者忘了 `pip install -r requirements.txt` |

问题请开 [Issue](https://github.com/Power-Key321/ai-agent-portfolio/issues)。

---
---

<a id="english"></a>
## English

> ✅ **Works out of the box on Claude Code.** All four skills follow the Claude Code convention (directory name = the `name` field in `SKILL.md`). Copy them in and they work — **no renaming, no configuration.**
> The first block below is all Claude Code needs.

### The short version

**Two directories cover all three tools.**

```bash
git clone https://github.com/Power-Key321/ai-agent-portfolio
cd ai-agent-portfolio

# (1) Read by both Claude Code and Cursor
mkdir -p ~/.claude/skills
cp -r agent_harness              ~/.claude/skills/agent_harness
cp -r multi-agent-research       ~/.claude/skills/multi-agent-research
cp -r tools/smart-loop           ~/.claude/skills/smart-loop
cp -r tools/tech-reserve-finder  ~/.claude/skills/tech-reserve-finder

# (2) Read by Codex
mkdir -p ~/.codex/skills
cp -r ~/.claude/skills/*         ~/.codex/skills/
```

Claude Code only? Block (1) is all you need. Codex only? Point block (1) at `~/.codex/skills` instead. On Windows PowerShell, use the script in the Chinese section above.

> ⚠️ **Do not rename the directories.** `agent_harness/` is both the skill directory and the Python package directory — renaming it breaks `import agent_harness`. All four directory names already match their `name` fields, so copy them as-is.

---

### Why these two directories

The three tools scan different skill roots, but there is no conflict — so copying twice is the simplest option:

| Directory | Claude Code | Codex | Cursor |
|---|---|---|---|
| `~/.claude/skills/` | ✅ native | ❌ | ✅ reads it for compatibility |
| `~/.codex/skills/` | ❌ | ✅ native | ✅ reads it for compatibility |
| `~/.cursor/skills/` | ❌ | ❌ | ✅ native |

**So:**
- Claude Code only → install to `~/.claude/skills/` only
- Codex only → install to `~/.codex/skills/` only
- Cursor only → either works
- All three → install to both

(Cursor also reads `~/.agents/skills/` and `~/.grok/skills/`, but the two above are enough.)

You can also install for a **single project**: drop the directories into the project's `.claude/skills/` or `.codex/skills/`. Same effect, scoped to that project.

---

### How to use them after installing

| Tool | How to trigger |
|---|---|
| **Claude Code** | Auto-loaded — matches the `description` field in `SKILL.md`. You can also type `/agent_harness <task>` |
| **Codex** | Type `/skills` to list what's loaded, then `$skill-name` to invoke explicitly |
| **Cursor** | Auto-loaded, matched on `description` just like Claude Code |

The quality of the `description` field is what decides whether the skill gets used automatically. That is the only concept you need to understand.

---

### What actually works where (honest version)

| Skill | Claude Code | Codex | Cursor | Dependencies |
|---|---|---|---|---|
| `tools/smart-loop` | ✅ | ✅ | ✅ | None — pure instructions |
| `tools/tech-reserve-finder` | ✅ | ✅ | ✅ | None — pure instructions |
| `agent_harness` | ✅ | ⚠️ partial | ⚠️ partial | Python 3.10+, then `pip install -r requirements.txt` |
| `multi-agent-research` | ✅ | ❌ | ❌ | Requires Claude Code's Workflow engine |

Two caveats:

- **`agent_harness`** — its `SKILL.md` instructs the agent to call `agent_harness.adapters.claude_code` via `python`. Codex and Cursor have no such adapter: the agent will understand the rules but cannot run the Python adapter layer. All three tools can read the **methodology**; only Claude Code runs the **full pipeline**.
- **`multi-agent-research`** — its `workflow.js` is a Claude Code Workflow script (it deterministically spawns hundreds of subagents). On Codex / Cursor it is readable framework documentation, **not an executable skill**.

---

### Troubleshooting

| Symptom | Cause |
|---|---|
| Skill isn't auto-loaded | Directory name doesn't match the `name` field in `SKILL.md` — copying as shown above avoids this entirely |
| `/skills` is empty in Codex | You installed to `~/.claude/skills/`. Codex doesn't read that — use `~/.codex/skills/` |
| `agent_harness` raises `ModuleNotFoundError` | Dependencies not installed — run `pip install -r requirements.txt` |

Open an [Issue](https://github.com/Power-Key321/ai-agent-portfolio/issues) if something doesn't work.
