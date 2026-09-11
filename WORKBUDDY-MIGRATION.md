# WorkBuddy 技能迁移记录

> **本文件在 `workbuddy` 分支上，不合并回 `main`。**
> `main` 保持「Claude Code / Codex / Cursor 三端通用」的形态；WorkBuddy 有专属契约，单独维护。
>
> **上架操作指南见 [`workbuddy/README.md`](workbuddy/README.md)** — 本文只记录「改了什么、为什么」。

## 为什么单独拉分支

WorkBuddy（腾讯，2026-09-02 开放平台上线）的 Skill 基于同一套 **Agent Skills 标准**，但有一层自己的硬约束。这些约束和三端通用形态**不完全兼容**，混在一起会互相污染：

- frontmatter 只认 **5 个字段**，多写的会被判为不规范
- `allowed-tools` 是**安全审查核心项**，缺失影响过审
- 技能名规则是**小写字母 + 数字 + 连字符**，与 `agent_harness` 的下划线冲突

## 改了什么

### 1. frontmatter 收敛到 5 字段白名单（4 个技能）

原先散落在顶层的 `version` / `author` / `tags` 全部收进 `metadata:` 下，并补上 `license` 与 `allowed-tools`。

```diff
 ---
 name: smart-loop
 description: ...
-version: 6.1.0
-tags: [loop, 任务分解, 量化执行, 中断恢复, 降级策略]
+license: MIT
+allowed-tools: Read Write Edit WebFetch WebSearch
+metadata:
+  version: 6.1.0
+  author: Bo Wang
+  tags: [loop, 任务分解, 量化执行, 中断恢复, 降级策略]
 ---
```

各技能补的 `allowed-tools`：

| 技能 | allowed-tools |
|---|---|
| `smart-loop` | `Read Write Edit WebFetch WebSearch` |
| `tech-reserve-finder` | `Read Write WebFetch WebSearch` |
| `multi-agent-research` | `Read Write WebFetch WebSearch` |
| `agent_harness` | `Read Write Bash`（保留 Python 调用路径需显式列 Bash） |

> `metadata:` 是 Agent Skills 标准里 `version`/`author`/`tags` 的正规位置，Claude Code / Codex / Cursor 同样接受——**这次改动对三端是纯增益，不是妥协**。

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
