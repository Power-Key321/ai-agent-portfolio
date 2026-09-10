# AI Agent Portfolio

**Bo Wang · AI Agent / LLM Application Product Manager**

[中文](#中文) ｜ [English](#english)

---

<a id="中文"></a>
## 中文

这里收录我设计并构建的三套 AI Agent 系统——一套编排框架、一套多智能体研究框架、一组自动化工具。它们不是代码练习，而是**真实跑起来过**的系统，解决的是我在长期实践中反复遇到的真实问题。

**我不是传统意义上的程序员。** 这些系统是我完成产品设计、架构定义和全部需求拆解后，借助 Claude Code 等 AI 编程工具实现并调试出来的。这个协作过程本身，就是我认为 AI 产品经理最该具备的能力——**知道模型能做什么、编排层该做什么、用户真正需要什么，然后把它们组织成能跑的系统。**

对一个 Agent 产品岗位来说，我认为这比"会写代码"更接近岗位本质：我不需要亲手敲每一行，但我必须能判断哪一行该存在。

---

### 仓库内容

| 项目 | 一句话 | 规模 |
|---|---|---|
| **[agent_harness](./agent_harness/)** | 乐高式 Agent 编排框架 | 24 个可插拔模块 / 6 类任务策略 / 21.7K 行 |
| **[multi-agent-research](./multi-agent-research/)** | 多智能体对抗验证研究框架 | 7 阶段工作流 / 1,134 行引擎 / 6 轮自审计 |
| **[tools](./tools/)** | 自动化工具集 | 跨产业技术储备发现器、通用任务循环 |

---

### 1. harness — 乐高式 Agent 编排框架

**核心问题**：写代码和做调研对流程的要求完全不同，但大多数 Agent 编排都是一条固定流水线。

**解法**：把编排结构本身参数化。编排系统拆成六大层（预处理 → 拆解 → 调度 → 上下文 → 执行 → 交付）共 **24 个可插拔模块**，按任务类型自动装配不同模块链。

- **6 类任务策略**，各自配置模块链、模型与螺旋收敛参数
- **三层意图路由**：学习正则 → 内置正则 → 模型判定，绝大多数请求在前两层零成本确定
- **量化门检 + 退化检测**：连续 3 轮无推进即触发降级，单点失败不污染整条链路
- **反馈自优化闭环**：以用户行为（接受/修改/重来）作为隐式评分，反哺策略权重——与多因子量化模型同构
- **否定结论外部对照**：得出"不可能/已穷尽"类结论时自动触发外部验证，防止把内部局限误判成问题极限

→ [详细文档](./agent_harness/README.md)

---

### 2. multi-agent-research — 多智能体对抗验证研究框架

**核心问题**：复杂研究任务里，模型给出的结论**无法判断真假**——分不清哪条有据可查、哪条是编的、哪条虽真但超出问题边界。

**解法**：把约束和验证变成流程的结构性环节，而不是靠 prompt 里写一句"请确保准确"。

**7 阶段工作流**：制宪会议 → 问题分解 → 4 队并行求解 → 对抗验证 → 评分 → 综合合成 → 多轮修补

- **前置制宪会议**：独立议员团博弈出本次任务专用的约束宪法（范围/排除/资源/证据/终止条款），刚性锁死 + 日落失效。立法程序借鉴真实制度：相关性审查、2/3 超多数逐条表决、永恒条款全票通过、一轮复议、少数意见记录
- **三轨裁决**：每条结论必须归入 `DEPLOYABLE`（证据闭合）/ `PROBE`（依赖未来证据，诚实标注）/ `REJECTED` 之一，不允许模糊地带
- **专职反驳验证**：评委的职责是反驳而非确认；违宪票为硬否决，结论即使为真也淘汰
- **可复现证据约束**：结论必须附带可重跑命令与落盘证据

**实测规模**：单轮完整流程调度 250 个 agent、消耗 410 万 token、1,134 次工具调用、约 79 分钟。
在一次 300 agent 规模的引用审计中，定位出 1 处严重幻觉引用与 1 处数字失真，修复后达成引用与数字双 100% 准确。

→ [详细文档](./multi-agent-research/README.md) ｜ [完整框架文档](./multi-agent-research/FRAMEWORK.md) ｜ [实测记录](./multi-agent-research/RESULTS.md)

---

### 3. tools — 自动化工具集

**[tech-reserve-finder](./tools/tech-reserve-finder/)** — 跨产业技术储备发现器

面对一个技术难题时，按三步法（功能分解 → 能力匹配 → 差距评估）扫描 41 个工业大类，找出那个"已经在做同样物理操作"的产业，给出跨产业替代路径。核心洞见：全产业链的广度本身就是最大的隐性技术库。含 A/B/C 三级分级框架与已验证的 A 级案例。

**[smart-loop](./tools/smart-loop/)** — 通用任务循环执行器

面向长周期、可迭代任务：演绎式意图理解（不问废话）→ 熵减链分解 → 每轮量化门检 → 失败自动降级。解决的是"任务跑到一半卡住"和"跑了很久但不知道有没有进展"的问题。

---

### 我在这些项目里做了什么

说清楚边界，避免误解：

**我负责的：**
- 全部产品定义、问题拆解与架构设计
- 每个模块的职责边界划分与取舍决策
- 质量控制机制的设计（三轨裁决、证据约束、否决规则）
- 失败模式分析——每轮迭代要修什么、为什么修
- 成本与预算控制策略
- 全部版本迭代的决策与验收

**AI 工具承担的：**
- 具体代码实现与语法细节
- 大规模重复性编写
- 调试协助

六轮自审计中共修复 40+ 项问题——**这些 bug 是怎么发现的、该修哪里、修完是否真的修好了，是我判断的。** 我认为这才是产品经理在这类系统里的核心价值。

---

### 技术栈

**Agent 与 LLM**：Claude Code、多智能体编排、Agent Loop、Tool Use、Context Engineering、MCP、Prompt Engineering

**工程**：Python、FastAPI、YAML 配置驱动、pytest、Git、REST API

**产品**：需求拆解、PRD、系统架构设计、交互流程设计、Axure / Visio / XMind

---

交流 Agent 产品的设计取舍，欢迎开 [Issue](https://github.com/Power-Key321/ai-agent-portfolio/issues)。

---
---

<a id="english"></a>
## English

This repository collects three AI agent systems I designed and built: an orchestration framework, a multi-agent research framework, and a set of automation tools. They are not coding exercises — all three have **actually been run**, and each solves a problem I kept running into in practice.

**I am not a programmer in the conventional sense.** These systems are the result of my product definition, architecture design, and full requirements decomposition — implemented and debugged with the help of AI coding tools such as Claude Code. That collaboration process is itself the core skill I believe an AI product manager needs: **knowing what the model can do, what the orchestration layer should do, and what the user actually needs — then organizing all three into a system that runs.**

For an agent product role, I think this is closer to the essence of the job than "can write code." I don't need to type every line myself, but I do need to judge which lines should exist.

---

### What's in This Repository

| Project | In one line | Scale |
|---|---|---|
| **[agent_harness](./agent_harness/)** | A LEGO-style agent orchestration framework | 24 pluggable modules / 6 task strategies / 21.7K LOC |
| **[multi-agent-research](./multi-agent-research/)** | An adversarial-verification multi-agent research framework | 7-stage workflow / 1,134-line engine / 6 self-audit rounds |
| **[tools](./tools/)** | Automation toolkit | Cross-industry technology reserve finder, general-purpose task loop |

---

### 1. harness — A LEGO-Style Agent Orchestration Framework

**The problem**: Writing code and doing research demand completely different processes, yet most agent orchestration is a single fixed pipeline.

**The approach**: Make the orchestration structure itself parameterized. The system is split into six layers (preprocess → decompose → schedule → context → execute → deliver) with **24 pluggable modules**, assembled automatically into different module chains depending on the task type.

- **6 task strategies**, each with its own module chain, model, and spiral-convergence parameters
- **Three-tier intent routing**: learned regex → built-in regex → model judgment. The vast majority of requests resolve in the first two tiers at zero cost
- **Quantitative gates + degradation detection**: three consecutive rounds without progress trigger automatic downgrade; a single point of failure never contaminates the whole chain
- **Feedback self-optimization loop**: user behavior (accept / modify / retry) serves as an implicit score that feeds back into strategy weights — structurally analogous to multi-factor quantitative models
- **External cross-check for negative conclusions**: when the system concludes "impossible" or "exhausted," it automatically triggers external verification, preventing an internal limitation from being mistaken for the problem's true limit

→ [Documentation](./agent_harness/README.md)

---

### 2. multi-agent-research — Adversarial Verification for Multi-Agent Research

**The problem**: In complex research tasks, you **cannot tell whether a model's conclusion is true** — which claim is backed by evidence, which is fabricated, and which is true but outside the problem's boundary.

**The approach**: Make constraints and verification structural parts of the workflow, rather than writing "please be accurate" in a prompt.

**7-stage workflow**: Constitutional convention → problem decomposition → 4 teams solving in parallel → adversarial verification → scoring → synthesis → multi-round patching

- **Upfront constitutional convention**: an independent assembly of delegates negotiates a task-specific constraint constitution (scope / exclusions / resources / evidence / termination clauses), rigidly locked with sunset expiry. The legislative procedure borrows from real institutions: relevance review, line-by-line voting at a two-thirds supermajority, unanimous consent for entrenchment clauses, one round of reconsideration, and a record of minority opinions
- **Three-track verdict**: every conclusion must be classified as `DEPLOYABLE` (evidence closed), `PROBE` (depends on future evidence, honestly labeled), or `REJECTED`. No gray zone is allowed
- **Dedicated refutation**: reviewers are charged with refuting, not confirming. A constitutional violation is a hard veto — a conclusion is eliminated even if it is true
- **Reproducible evidence constraint**: every conclusion must ship with a re-runnable command and persisted evidence

**Measured scale**: a single full run dispatched 250 agents, consumed 4.1M tokens across 1,134 tool calls in roughly 79 minutes.
In a citation audit at 300-agent scale, it located one severe hallucinated citation and one numerical distortion; after the fix, citations and figures both reached 100% accuracy.

→ [Documentation](./multi-agent-research/README.md) ｜ [Full Framework](./multi-agent-research/FRAMEWORK.md) ｜ [Run Records](./multi-agent-research/RESULTS.md)

---

### 3. tools — Automation Toolkit

**[tech-reserve-finder](./tools/tech-reserve-finder/)** — Cross-industry technology reserve finder

Given a hard technology problem, this tool applies a three-step method (function decomposition → capability matching → gap assessment) to scan 41 industrial categories and locate the industry that is "already performing the same physical operation," yielding a cross-industry alternative. The core insight: the breadth of the full industrial chain is itself the largest hidden technology reserve. Includes an A/B/C classification framework and validated A-tier cases.

**[smart-loop](./tools/smart-loop/)** — General-purpose task loop runner

Built for long-horizon, iterative tasks: deductive intent understanding (no unnecessary questions) → entropy-reduction decomposition → per-round quantitative gates → automatic downgrade on failure. It solves "the task stalls halfway through" and "it ran for a long time but I can't tell if anything progressed."

---

### What I Actually Did on These Projects

To be explicit about the boundary:

**What I owned:**
- All product definition, problem decomposition, and architecture design
- Responsibility boundaries and trade-off decisions for every module
- Design of the quality-control mechanisms (three-track verdict, evidence constraints, veto rules)
- Failure-mode analysis — what to fix each iteration and why
- Cost and budget control strategy
- Decision-making and acceptance for every version iteration

**What the AI tools handled:**
- Concrete code implementation and syntax details
- Large-scale repetitive writing
- Debugging assistance

Across six self-audit rounds, 40+ issues were fixed — **how each bug was found, where the fix belonged, and whether the fix truly worked were all my calls.** I believe that is the core value of a product manager in systems like these.

---

### Tech Stack

**Agent & LLM**: Claude Code, multi-agent orchestration, agent loops, tool use, context engineering, MCP, prompt engineering

**Engineering**: Python, FastAPI, YAML-driven configuration, pytest, Git, REST APIs

**Product**: requirements decomposition, PRDs, system architecture design, interaction flow design, Axure / Visio / XMind

---

Happy to discuss design trade-offs in agent products — feel free to open an [Issue](https://github.com/Power-Key321/ai-agent-portfolio/issues).
