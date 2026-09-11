# WorkBuddy 上架说明

> 本目录在 `workbuddy` 分支上，**不合并回 `main`**。
> `main` 保持「Claude Code / Codex / Cursor 三端通用」形态；WorkBuddy 有专属契约，单独维护。
>
> 本说明的契约部分**直接摘自 `open.workbuddy.cn/docs/skill`**（通过本机代理抓取后解析），不再依赖二手资料。

---

## 一、先上哪个：试水顺序

| 顺序 | 技能 | 为什么是这个顺序 |
|---|---|---|
| **🥇 先上** | `smart-loop`<br>长任务循环推进器 | 单文件、零依赖、全文零敏感内容 → **审核风险最低**；场景通用（长任务、多轮迭代）；名字一看就懂 |
| **🥈 再上** | `tech-reserve-finder`<br>跨产业技术平替发现器 | 已完成脱敏，但受众窄（技术路线/供应链调研），正文涉及具体产业方向 → 放流程跑通之后 |
| **⏸ 暂不上** | `multi-agent-research` | 真能力在 `workflow.js`，依赖 Claude Code Workflow 引擎。传上去只是一份读得懂、跑不动的说明书 |
| **⏸ 暂不上** | `agent_harness` | ① 依赖 Python 3.10+ 与 Claude Code 适配器层；② 名字含下划线违反命名规则，而**改名会破坏 `import agent_harness`**（目录名即包名） |

`smart-loop` 是试水首选——试水的目的不在冲量，在于**用最低风险把流程跑通**。

### 关于架构级 harness 和 CTF

流程跑通后再上，但两者的准备成本不一样：

- **`agent_harness`**：需要**拆一个纯指令版**，另起目录名（如 `agent-orchestration`），去掉 Python 调用路径只留编排方法论。**不要改现有目录名**，`main` 分支还要靠它跑。
- **CTF 研究框架**：方法论层（对抗验证 + 证据约束 + 三轨裁决）本身是干净的，但**表述要整体重写**——把落脚点从"破解"移到"结论可信度"。这一步不做，内容审核过不去。该技能目前**不在这个仓库里**，要先决定是否公开。

---

## 二、frontmatter 契约（官方文档原文）

**摘自 `open.workbuddy.cn/docs/skill`**，两个字段是必填，其他都是可选：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | **必填** | 技能标识（kebab-case：小写字母 + 数字 + 连字符，**目录名必须完全一致**） |
| `description` | **必填** | 一句话描述技能功能 |
| `description_zh` | 可选 | 简短中文介绍 |
| `description_en` | 可选 | 简短英文介绍 |
| `display_name` | 可选 | **中文显示名**（用户在 SkillHub 列表页看到的名字） |
| `display_name_en` | 可选 | 英文显示名 |
| `category` | 可选 | 分类（如 `writing`，完整列表在上传表单的分类下拉框里） |
| `allowed-tools` | 可选 | 工具白名单，**多个用逗号分隔**（如 `Read, Write, Bash`） |
| `version` | 可选 | 版本号 |
| `author` | 可选 | 作者/开发者名 |
| `license` | 可选 | 许可证（文档示例里没出现，但放上是标准做法） |
| `disable-model-invocation` | 可选 | `true` 时 AI 不自动触发，只能用户手动调用 |
| `user-invocable` | 可选 | `false` 时从 `/` 菜单隐藏，仅供 AI 内部使用 |

### 文档里**没有**的字段（不要写）

- ❌ `when_to_use` —— 文档 0 命中。本机客户端二进制里读到这个字段，可能是分支或未公开的特性，**上传版别写**，被审核卡住不划算
- ❌ `metadata:` 块 —— 文档里完全没有嵌套结构
- ❌ `tags:` —— 文档里没有
- ❌ `references` / `scripts` / `templates` 是**目录**不是 frontmatter 字段（`references/xxx.md`、`scripts/xxx.py`），引用语法是 `@references/xxx.md`

### 文档里**没明说**的事项

- 正文行数 / token 上限 —— 此页未提及。建议自约束在 **500 行 / 5000 token 以内**（来自社区资料，未在文档原文核对）
- 安全分级（P0/P1/P2 词表）—— 此页 **0 命中**。"P0 硬禁止"是社区说法，不是官方文档原文
- 实名认证的具体流程 —— 此页未涉及

### 实际做法（`smart-loop` 为例）

```yaml
---
name: smart-loop                              # ← kebab-case，与目录名一致
description: 把多轮、周期长、中途可能失败的任务，拆成有量化指标的分阶段流程…
description_zh: 长任务循环推进器 — 先用最少信息推断真实目标，按「信息源→过滤→处理→产出→验证」链条分解…
description_en: Long-Task Loop Driver — break a multi-round, long-horizon…
display_name: 长任务循环推进器                # ← 用户在列表页看到的名字
display_name_en: Long-Task Loop Driver
allowed-tools: Read, Write, Edit, WebFetch, WebSearch   # ← 逗号分隔
version: 6.2.0
author: Bo Wang
license: MIT
---
```

`name` 是 ASCII 标识符，**不能写中文**；中文走 `display_name` + `description_zh` + 正文 H1。

### 中文名对照

| slug | display_name | display_name_en |
|---|---|---|
| `smart-loop` | 长任务循环推进器 | Long-Task Loop Driver |
| `tech-reserve-finder` | 跨产业技术平替发现器 | Cross-Industry Tech Substitute Finder |
| `multi-agent-research` | 多智能体对抗验证研究框架 | Multi-Agent Adversarial Research |
| `agent_harness` | 乐高式 Agent 编排框架 | Lego-Style Agent Orchestration |

`category` 在 `frontmatter` 里没写——这页文档只给了 `writing` 一个例子，没给完整分类列表。**上传时在表单的分类下拉框里选**（常见的有 `productivity` / `research` / `writing` 等，建议 `smart-loop` 选 productivity，`tech-reserve-finder` 选 research）。

---

## 三、案例脱敏

### 原始 11 个案例的敏感度分级

`tech-reserve-finder` 最初有 11 个 A 级案例，公开前筛过一轮。完整分级：

| # | 案例 | 判定 |
|---|---|---|
| A1 | 显示面板 → 光计算推理芯片 | 🔴 **禁**（AI + 半导体） |
| A2 | 稀土分离 → 原子层沉积工艺 | 🔴 **禁**（稀土 + 半导体） |
| A3 | 聚变氚增殖包层 → 退役电池回收 | 🔴 **禁**（核聚变） |
| A4 | 高能材料药柱界面 → 固态电池界面 | 🟡 军工背景，**本次撤下** |
| A5 | 单光子探测 → 光计算精度 | 🔴 **禁**（量子 + 半导体） |
| A6 | **轨道交通牵引变流 → 大型数据中心供配电** | 🟢 **本次新增** |
| A7 | 核电压力容器锻造 → 超高真空腔体 | 🟡 核电 + 被卡方是半导体，不用 |
| A8 | 磁浮控制 → 晶圆台运动控制 | 🔴 **禁**（半导体） |
| A9 | **深海耐压结构 → 超高压化工反应器** | 🟢 保留 |
| A10 | **中药连续提取 → 化学药连续制造** | 🟢 保留（最干净） |
| A11 | **煤化工碳化 → 下一代碳材料** | 🟢 保留 |

**最终 4 个，全部民用**。A6 是新补的——"大功率电能变换"这个物理原语跨到两个民用场景，最能体现方法的迁移力，敏感度零。

### 这一轮还改了什么（降"张扬"度）

| 原来 | 现在 | 原因 |
|---|---|---|
| 「卡脖子」「受制于」「追赶台积电」 | 中性描述 | 去掉对抗色彩 |
| A 级 =「全球范围内几乎没人想到」 | 「公开材料中少见直接连接」 | 不下无法证伪的强断言 |
| 案例里点名的企业/院所 | **全部去掉**，只留产业特征 | 不点名 |
| 硬数字（10-50x、全球唯一、全球独有） | 去除，改为能力描述 | 不张扬 |
| 「军工/重工是最大的隐性技术库」 | 「极端工况行业是最大的隐性技术库」 | 去掉军工指向 |
| 内部笔记引用 `[[中国全产业链…]]` | 删除 | 不带内部笔记标题 |
| 案例结尾 | 加「案例只作演示」 | 明确案例是方法演示不是结论清单 |

---

## 四、需要注册 / 认证吗

**需要，而且是实名认证。**

### 第 1 步：WorkBuddy 账号

手机号注册。这一步只让你**使用**平台。

### 第 2 步：开发者实名认证（发布技能的前置条件）

| 项 | 内容 |
|---|---|
| 材料 | 身份证 + 手机号 + 邮箱 + **扫脸** |
| 耗时 | 约 3 分钟 |
| 可跳过 | **不可** |
| 收费 | 否 |

认证通过后需**完善开发者主页**（头像 / 20–120 字简介 / 联系方式）——这是技能详情页上展示给用户的公开身份。

> ⚠️ 实名认证意味着真实身份与该账号**永久绑定**。上架内容若涉及敏感领域，责任归属是明确且可追溯的。

### 第 3 步：提交与审核

```
上传 SKILL.md（zip 或目录结构）+ 填写技能介绍
  → 安全扫描 + AI 审核 + 人工抽检
  → 上架 / 驳回（邮件通知）
```

**审核 3–7 个工作日**（来自社区资料，文档原文未给具体数字）。上架后后台可看安装量 / 使用量 / 评分。

> 解析失败兜底：上传 zip 后解析失败可参考官方文档页（技能基础结构 / 子资源目录说明），定位问题仍失败可联系 **openworkbuddy@tencent.com**（文档原文给出的联系方式）。

---

## 五、上架能拿到什么

| 项 | 说明 |
|---|---|
| 曝光 | 进入 SkillHub，国内高可达渠道——**曝光量级大于 GitHub** |
| 调用 | 用户的 agent 可直接调用 |
| 收款 | SkillPay：定价权与收款权归开发者，按调用量结算，微信支付，**无企业规模门槛** |

**实际价值排序**：

1. **能力证明**——「国内主流 agent 平台有已上架技能」比 GitHub 链接更容易被国内 HR 与团队验证
2. **被动曝光**——技能详情页挂开发者主页，等于常驻公开名片
3. **收入**——两个技能都是方法论型，**不要当收入来源**

---

## 六、⚠️ 披露边界（提交前自己拍板）

`tech-reserve-finder` 的案例此前已在公开 GitHub 曝光过一次，但 **SkillHub 的暴露面大于 GitHub**：GitHub 要会翻会搜，SkillHub 是平台内点一下就能装；实名认证后内容与真实身份可追溯绑定。

**本轮已完成脱敏**（见 §三）。是否上架仍需你确认。三个选项：

| 选项 | 含义 |
|---|---|
| **A. 原样上架** | 接受上述暴露面 |
| **B. 只上方法论** | 摘掉 4 个案例，只留三步法 + 41 大类 + A/B/C 分级 |
| **C. 暂不上架** | 只上 `smart-loop` |

建议随顺序走：**先上 `smart-loop` 试水**，`tech-reserve-finder` 等流程跑通后再定 A 还是 B。

---

## 七、动手清单

- [ ] 注册 WorkBuddy 账号 + 完成实名认证
- [ ] 登录 `open.WorkBuddy.cn` 在上传页面确认分类下拉框（`category` 没在 frontmatter 写，要在这里选）
- [ ] 跑 `bash workbuddy/pack.sh` 出包
- [ ] 上传 `smart-loop`，提交审核
- [ ] 通过后回填开发者主页
- [ ] 观察 1–2 周安装量，再决定 `tech-reserve-finder` 走 A 还是 B

---

## 八、附：WorkBuddy vs 现有三端的契约差异

| 维度 | Claude Code / Codex / Cursor | WorkBuddy |
|---|---|---|
| frontmatter 必填 | 无 | `name` + `description` |
| frontmatter 字段 | 宽松，额外字段被忽略 | 文档列出 10 个可选字段；**未列出的字段建议不要写** |
| `allowed-tools` 分隔符 | 空格 / 逗号 / YAML 列表都吃 | **逗号**（文档明确说"多个用逗号分隔"） |
| `name` 命名规则 | 无限制 | kebab-case（小写字母 + 数字 + 连字符），与目录名一致 |
| `display_name` / `display_name_en` | 无 | 顶级字段，列表页显示用 |
| `description_zh` / `description_en` | 无 | 顶级字段，双语短介绍 |
| 技能根目录 | `~/.claude/skills/`、`~/.codex/skills/` | `~/.workbuddy/skills/` 与 `~/.codebuddy/skills/` **都会扫** |
| 变量占位符 | `${CLAUDE_SKILL_DIR}` | `${CODEBUDDY_SKILL_DIR}`（兼容 Claude 别名） |
| 安全分级 | 无 | 文档本节 0 命中 P0/P1/P2；该分级来自社区说法 |
| 正文限制 | 无硬限制 | 文档未给上限；社区资料说 500 行 / 5000 token |
| 子资源 | 无 | `references/` `scripts/` `templates/`（`@references/xxx.md` 引用） |
| 分发 | 自建 marketplace / 官方目录 | **SkillHub**（审核 3–7 工作日，社区资料） |
| 付费 | 无 | **SkillPay**（定价权 + 收款权归开发者） |

> 契约部分的字段清单 / 分隔符 / 目录名规则 / 子资源约定均来自 `open.workbuddy.cn/docs/skill` 原文（用本机代理 49150 抓取后解析）。
> 审核时长 / SkillPay 细节 / 安全分级词表 / 正文上限这些**文档原文未给**的事项仍标记为社区资料。