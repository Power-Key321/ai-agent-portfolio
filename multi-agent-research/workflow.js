export const meta = {
  name: 'adversarial-research',
  description: '多智能体对抗验证式深度研究 v6.8 — 前置制宪会议约束 + 跨队融合合成 + 多轮修补循环 + E4 实际执行永恒硬约束(代码/市场/混合任务所有策略/算法类 claim 必须附可重跑脚本+sha256+真实实跑stdout+落盘数据+falsification; 缺一即被 Verify 阶段分轨; 评委必须独立重跑同脚本验证). ConstitutionForge(议长意图分析→4议员提案→委员会整合→逐条2/3表决→复议→颁布唯一约束法) → ProblemForge问题分解 → 4队并行求解(共享URL去重+违宪自检+E4缺失降权) → 每条claim N票三轨对抗验证(违宪票计入refuted+多数约束+quorum守卫+E4三态重跑) → 计分排行 → 跨队融合综合结论合成 → PatchLoop多轮修补(各队提patch→3票验证→≤3轮+轮内去重). 约束法刚性锁死+日落失效. v6.8 执行层硬化: Verify评委effort→medium + E4重跑三态分级(SHA不符/环境不可复现→PROBE不误杀真claim) + agent退避重试(429指数退避×2) + totalAgentBudget全局配额熔断(Verify动态预留synthesis预算) + E4缺失降权排序. v6.7 三轨裁决(DEPLOYABLE/PROBE/REJECTED, 修复Round5实证的诚实护城河40评委0淘汰)+评委五视角+宪法decidableTest(游戏内可判定条款)+Synthesis收PROBE清单+REJECTED异见. v6.6 新增E4永恒条款+ARTIFACT_SCHEMA+Verify独立重跑. v6.5 P0修复(CASCADE+N1-EDGE). 自动适配工具集.',
  whenToUse: '当用户想把目标任务转化为求解竞赛，且要求先通过模拟立法流程(制宪会议)产出唯一约束范围、再让多队伍在约束内竞争+对抗验证得出高质量综合结论报告时。当目标任务是技能/工作流审计时, 启用 patchLoop 让各队对发现的致命漏洞提议修补并多轮验证. 也可当作 deep-research 的约束竞争化变体.',
  phases: [
    { title: 'Constitution', detail: '制宪会议: 议长议程→4议员提案→委员会整合(相关性审查)→逐条2/3表决→1轮复议→颁布constitution.json(刚性+日落)' },
    { title: 'ProblemForge', detail: '目标任务+约束宪法 → 问题清单(主问题/子问题/规则/计分/工具集)' },
    { title: 'Compete', detail: '4队按策略在宪法约束内并行搜索→共享URL去重→抓取提取(claims带队伍归属,越界即弃)' },
    { title: 'Verify', detail: '每条claim N票三轨对抗验证(DEPLOYABLE/PROBE/REJECTED; 五视角评委effort=medium; 违宪票+E4三态重跑; DEPLOYABLE须严格多数; totalAgentBudget配额熔断)' },
    { title: 'Score', detail: '按队伍聚合计分→排行榜(领先制)' },
    { title: 'Synthesis', detail: 'v6.1 跨队融合: 全部幸存claims(标注队伍归属)+宪法依据 → 最终报告' },
    { title: 'PatchLoop', detail: 'v6.1 M6 兑现: 各队对致命漏洞提patch→3票验证→≤3轮迭代(默认关, CONFIG.patchLoop=true 启用)' },
  ],
}

// adversarial-research v6.7: Constitution(制宪会议 + E4 实际执行永恒硬约束 + decidableTest游戏内可判定条款) → ProblemForge → Compete(4 teams pipeline w/ shared URL dedup + per-team quota + 余数分配) → Verify(N-vote 三轨对抗验证 DEPLOYABLE/PROBE/REJECTED + 五视角评委 + 违宪票计入refuted + 严格多数 + quorum守卫 + E4 artifact 独立重跑检查) → Score(F0 过滤 + PROBE不计分不扣分) → Synthesis(跨队融合 + PROBE清单 + REJECTED异见 + c.quote兜底) → PatchLoop(多轮修补 + 轮内去重 + title maxLength)
// v6.7 修复(Round5 实证审计 2026-08-23: 40评委仅4票反驳/8策略全幸存/Verify被'诚实护城河'中和成恒真式):
//   P1 三轨裁决(VERDICT_SCHEMA.track: 诚实标注'理论值'不再自动幸存 → 归 PROBE 轨; DEPLOYABLE 须严格多数票)
//   P2 评委五视角(JUDGE_LENSES: 数据完整性/逻辑数学/证据可达性/合宪性/对抗逆向选择 — 消灭克隆评委相关投票)
//   P3 宪法 decidableTest(每条条款必须附游戏内可判定检验, 禁止把判定标准锚定在博弈结束后才存在的证据上)
//   P5 Synthesis 显式接收 PROBE 清单 + REJECTED 异见证据(少数意见是资产, 最锋利分析常来自反驳票)
//   S5c.4 修订: erroredOverflow 归 unverified(基础设施失败) 而非 isRefuted — 与 summary 的基础设施故障分支对齐
// 前置约束机制模拟人类法律制定流程(三读程序/2/3超多数/相关性规则/reconsideration/日落条款/永恒条款).
// v6.6 新增 E4 永恒条款 + ARTIFACT_SCHEMA: 对 taskType ∈ {code, market, hybrid} 的任务, 任何策略/算法类 claim 必须附 (i) 实际编写的脚本路径+SHA256 (ii) 真实实跑 stdout 输出 (iii) 落盘数据路径+SHA256 (iv) falsification 条件. Verify 阶段评委必须独立重跑相同脚本验证真实性. 缺一即被 refuted (E4 单独否决).
// v6.5 P0 修复: CASCADE-1(VERIFY_PROMPT 三分支重构)+N1-EDGE(每队 ≥ 1 slot)
// v6.5 P1 修复: M6-ver.1(全字段 maxLength)+NEW-8(索引语义)+CONFIG(0 吞掉+浮点规范化)
// v6.5 P2 优化: CONF_RANK 抽常量 + bestVerdict() helper + SYNTHESIS claim 截断
// v6.4 P0 修复: NEW-7(prompt id 同步)+NEW-8(ballot 端 id fallback)+META(元数据完整化)
// v6.4 P1 修复: M6-ver.1(PATCH_SCHEMA maxLength 防 8KB DoS)+S7(c.quote 兜底)+N2(违宪指标 > 0)+CONFIG(clamp)+S3(minority_report 截断+转义)+S9(N1 余数分配 + S9.2 dupes 扣 slot)+S5c(quorum + errored 穿透)+S1×S5c(cascade 联动)+M2-cmp(F0 过滤)+NEW-2(PatchLoop dedup)
// v6.3 修复: M4(永恒条款 id 化)+S3(minority_report 进 block)+S7(verdict 最佳 evidence)+元数据
// v6.2 修复: S1(空宪法降级)+S5c(claim-level hard veto)+S9(per-team 配额)+M6-ctx(prevPatches 累积)+M6-ver(prevPatches 传参)
// v6.1 修复: M1(teamDefs补id)+M2(跨队融合 + 守卫改confirmed.length)+S5(违宪票数学化)+S6(多数约束)+M6(多轮修补循环兑现)
// args = {task, config} or a plain string task. config.constitution === false 退回无宪法; config.patchLoop === false 跳过修补; config.maxPatchRounds ≤3; votes 1-10; maxFetch 1-100; maxVerify 1-200. config.enforceArtifact 默认 true; 显式 false 可关闭 E4 强制(只对 research 类型有意义).

// ─── Runtime config (args can be a string task or {task, config}) ───
const OBJ = (typeof args === "object" && args && !Array.isArray(args)) ? args : {}
const TASK = (typeof args === "string" ? args : OBJ.task || "").trim()
const CONFIG = (OBJ.config && typeof OBJ.config === "object") ? OBJ.config : {}
const VOTES_PER_CLAIM = Math.min(Math.max(Number(CONFIG.votes ?? 5), 1), 10)
const REFUTATIONS_REQUIRED = Math.min(Math.max(Number(CONFIG.refuteRequired ?? 3), 1), VOTES_PER_CLAIM)
const MAX_FETCH = Math.min(Math.max(Math.floor(Number(CONFIG.maxFetch ?? 15)), 1), 100)
const MAX_VERIFY_CLAIMS = Math.min(Math.max(Number(CONFIG.maxVerify ?? 25), 1), 200)
const ENABLE_CONSTITUTION = CONFIG.constitution !== false
// v6.6 E4: 默认强制"实际执行+真实实跑+落盘数据"硬约束; 仅 research 任务可显式关闭
const ENFORCE_ARTIFACT = CONFIG.enforceArtifact !== false
const TEAM_IDS = (CONFIG.teams && Array.isArray(CONFIG.teams) && CONFIG.teams.length >= 2)
  ? CONFIG.teams
  : ["T0", "T1", "T2", "T3"]

// ─── v6.8 P0-4 全局配额熔断 + P0-3 退避重试 ───
// 背景: Round 5 中途 41/46 agent 因 API 429 失败, filter(Boolean) 静默丢票; claims×VOTES 可冲爆全局配额
const TOTAL_AGENT_BUDGET = Math.min(Math.max(Math.floor(Number(CONFIG.totalAgentBudget ?? 250)), 10), 2000)
const MAX_PATCH_ROUNDS = Math.min(Math.max(Math.floor(Number(CONFIG.maxPatchRounds) || 1), 1), 3)
let agentsUsed = 0
const sleep = ms => new Promise(resolve => { if (typeof setTimeout === "function") setTimeout(resolve, ms); else resolve() })
async function retryAgent(prompt, opts, retries = 2) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (agentsUsed >= TOTAL_AGENT_BUDGET) {
      log("⚠️ 配额熔断: 已达 totalAgentBudget=" + TOTAL_AGENT_BUDGET + ", 跳过后续 agent")
      return null
    }
    agentsUsed++
    let r = null
    try { r = await agent(prompt, opts) } catch (e) { r = null }
    if (r !== null && r !== undefined) return r
    if (attempt < retries) {
      log("agent 调用返回空, 退避重试 " + (attempt + 1) + "/" + retries)
      await sleep(4000 * Math.pow(2, attempt)) // 4s, 8s 指数退避
    }
  }
  return null
}

// ─── Teams: 4 independent attack strategies ───
const TEAM_DEFS = {
  T0: { name: "主攻手", strategy: "权威/主流/一手", directive: "优先官方文档、机构报告、学术论文、一手数据与基准测试；覆盖任务主线事实。" },
  T1: { name: "逆势者", strategy: "怀疑/反证", directive: "寻找反驳证据、攻击常见假设、挖掘反例、质疑权威说法；找出容易被忽略的否定性事实。" },
  T2: { name: "实务派", strategy: "落地/实操", directive: "聚焦真实案例、实现细节、从业人员视角、具体数字与可操作性；关注成本与约束。" },
  T3: { name: "前沿哨", strategy: "最新/边界", directive: "优先近期新闻、前沿论文、极端情形与被忽视的边缘维度；追踪最新动向。" },
}

// ─── Delegates: 制宪议员团(v6.0, 制宪权与参赛权分离 = pouvoir constituant ≠ pouvoir constitué) ───
const DELEGATE_IDS = ["D0", "D1", "D2", "D3"]
const DELEGATE_DEFS = {
  D0: { name: "聚焦派", interest: "收窄范围，防止无限拓展", directive: "约束法必须把模糊命题切成可回答的明确边界。警惕范围蔓延——边界外的内容再好也不是本次博弈目标。优先提交 scope(范围) 条款。" },
  D1: { name: "扩张派", interest: "保留探索空间，防止过度约束", directive: "约束过死会漏掉非显而易见的正解。反对不必要的排除条款，为非常规路径保留通道。你的职责是攻击其他议员的过度收窄倾向。" },
  D2: { name: "务实派", interest: "资源/深度/成本边界", directive: "约束法必须限定投入边界——来源数量、时间深度、工具范围。防止无底洞式研究。优先提交 resource(资源) 条款。" },
  D3: { name: "质疑派", interest: "可证伪性/证据标准/终止条件", directive: "约束法必须规定证据标准(什么来源算数)与终止条件(什么情况判定无解并停手)。防止不可证伪的废话条款。优先提交 evidence(证据)/termination(终止) 条款。" },
}
const ARTICLE_TYPES = ["scope", "exclusion", "resource", "evidence", "termination"]
const SUPERMAJORITY = 3   // 4 议员的 2/3 超多数(向上取整)——阿罗定理: ~64% 超多数可防孔多塞循环
const ETERNITY_QUORUM = 4 // 永恒条款须全票——布坎南: 高外部成本决策须一致同意

// ─── Schemas ───
const SPEAKER_SCHEMA = {
  type: "object", required: ["intentSummary", "agenda"],
  properties: {
    intentSummary: { type: "string" },
    agenda: { type: "array", minItems: 2, maxItems: 6, items: {
      type: "object", required: ["issue", "whyConstrain"],
      properties: {
        issue: { type: "string" },
        whyConstrain: { type: "string" },
      },
    }},
  },
}
const DELEGATE_SCHEMA = {
  type: "object", required: ["articles"],
  properties: {
    articles: { type: "array", minItems: 1, maxItems: 4, items: {
      type: "object", required: ["type", "text", "rationale"],
      properties: {
        type: { type: "string", enum: ARTICLE_TYPES },
        text: { type: "string" },
        rationale: { type: "string" },
      },
    }},
  },
}
const COMMITTEE_SCHEMA = {
  type: "object", required: ["consolidated", "rejected"],
  properties: {
    consolidated: { type: "array", minItems: 1, maxItems: 10, items: {
      type: "object", required: ["id", "type", "text", "contested"],
      properties: {
        id: { type: "string" },
        type: { type: "string", enum: ARTICLE_TYPES },
        text: { type: "string" },
        rationale: { type: "string" },
        contested: { type: "boolean" },
        decidableTest: { type: "string" },
      },
    }},
    rejected: { type: "array", items: {
      type: "object", required: ["text", "reason"],
      properties: { text: { type: "string" }, reason: { type: "string" } },
    }},
    eternityProposal: { type: "array", maxItems: 3, items: {
      type: "object", required: ["id", "text"],
      properties: { id: { type: "string" }, text: { type: "string" }, rationale: { type: "string" } },
    }},
  },
}
const AMEND_SCHEMA = {
  type: "object", required: ["amended"],
  properties: {
    amended: { type: "array", items: {
      type: "object", required: ["id", "text"],
      properties: {
        id: { type: "string" },
        text: { type: "string" },
        amendmentNote: { type: "string" },
      },
    }},
  },
}
const VOTE_SCHEMA = {
  type: "object", required: ["votes"],
  properties: {
    votes: { type: "array", items: {
      type: "object", required: ["id", "approve", "reason"],
      properties: {
        id: { type: "string" },
        approve: { type: "boolean" },
        reason: { type: "string" },
      },
    }},
    eternityVotes: { type: "array", items: {
      type: "object", required: ["id", "approve", "reason"],
      properties: {
        id: { type: "string" },
        approve: { type: "boolean" },
        reason: { type: "string" },
      },
    }},
  },
}
const PROBLEMFORGE_SCHEMA = {
  type: "object", required: ["task", "taskType", "mainFlag", "subProblems", "rules", "scoring"],
  properties: {
    task: { type: "string" },
    taskType: { type: "string", enum: ["research", "market", "code", "hybrid"] },
    mainFlag: { type: "string" },
    toolset: {
      type: "object", properties: {
        web: { type: "boolean" }, market: { type: "boolean" }, code: { type: "boolean" },
      },
    },
    subProblems: { type: "array", minItems: 2, maxItems: 6, items: {
      type: "object", required: ["id", "question", "difficulty", "points"],
      properties: {
        id: { type: "string" },
        question: { type: "string" },
        difficulty: { type: "string", enum: ["easy", "medium", "hard"] },
        points: { type: "integer", minimum: 1 },
      },
    }},
    rules: { type: "array", items: { type: "string" } },
    scoring: { type: "string" },
  },
}
const SEARCH_SCHEMA = {
  type: "object", required: ["results"],
  properties: {
    results: { type: "array", maxItems: 6, items: {
      type: "object", required: ["url", "title", "relevance"],
      properties: {
        url: { type: "string" },
        title: { type: "string" },
        snippet: { type: "string" },
        relevance: { type: "string", enum: ["high", "medium", "low"] },
      },
    }},
  },
}
const EXTRACT_SCHEMA = {
  type: "object", required: ["claims", "sourceQuality"],
  properties: {
    sourceQuality: { type: "string", enum: ["primary", "secondary", "blog", "forum", "unreliable"] },
    publishDate: { type: "string" },
    claims: { type: "array", maxItems: 5, items: {
      type: "object", required: ["claim", "quote", "importance", "subProblemId"],
      properties: {
        claim: { type: "string" },
        quote: { type: "string" },
        importance: { type: "string", enum: ["central", "supporting", "tangential"] },
        subProblemId: { type: "string" },
        // v6.6 E4 ARTIFACT: 策略/算法类 claim 必须填 artifact 字段(由 Fetch 阶段根据 ENFORCE_ARTIFACT + manifest.taskType 提示)
        // 缺 artifact 在 Verify 阶段触发 E4 独立否决(refuted=true, evidence="E4 artifact missing")
        artifact: { type: "object", required: ["scriptPath", "sha256", "stdout", "dataPath", "falsification"],
          properties: {
            scriptPath: { type: "string", maxLength: 500, description: "实际编写的脚本文件绝对/相对路径" },
            sha256: { type: "string", minLength: 64, maxLength: 64, description: "脚本文件的 SHA256 校验和" },
            stdout: { type: "string", description: "实际实跑 stdout 关键输出(<8KB 摘要或落盘路径)" },
            dataPath: { type: "string", maxLength: 500, description: "落盘数据文件路径" },
            dataSha256: { type: "string", minLength: 64, maxLength: 64, description: "数据文件 SHA256" },
            falsification: { type: "string", maxLength: 500, description: "失败条件(若 X 发生则策略失效)" },
            reproduceCommand: { type: "string", maxLength: 500, description: "独立验证者可执行的重跑命令" },
          },
        },
      },
    }},
  },
}
const VERDICT_SCHEMA = {
  type: "object", required: ["track", "refuted", "evidence", "confidence"],
  properties: {
    // v6.7 P1: 三轨裁决 — DEPLOYABLE(证据在博弈内闭合,可交付) / PROBE(核心证据博弈内不可得,诚实标注≠幸存) / REJECTED(被反驳/违宪/E4失败)
    track: { type: "string", enum: ["DEPLOYABLE", "PROBE", "REJECTED"] },
    refuted: { type: "boolean" },
    evidence: { type: "string" },
    confidence: { type: "string", enum: ["high", "medium", "low"] },
    counterSource: { type: "string" },
    unconstitutional: { type: "boolean" },
  },
}
const PATCH_SCHEMA = { // v6.1 M6: 多轮修补
  type: "object", required: ["patches"],
  properties: {
    patches: { type: "array", maxItems: 3, items: {
      type: "object", required: ["flawId", "title", "description", "diff"],
      properties: {
        flawId: { type: "string", maxLength: 50 },
        title: { type: "string", maxLength: 200 },
        description: { type: "string", maxLength: 2000 },
        diff: { type: "string", maxLength: 2000 },
        targetFile: { type: "string", maxLength: 200 },
        targetLines: { type: "string", maxLength: 100 },
        riskNote: { type: "string", maxLength: 1000 },
      },
    }},
  },
}
const PATCH_VERIFY_SCHEMA = {
  type: "object", required: ["approved", "evidence", "regression"],
  properties: {
    approved: { type: "boolean" },
    evidence: { type: "string" },
    regression: { type: "string" },
  },
}
const SYNTHESIS_SCHEMA = {
  type: "object", required: ["summary", "synthesisAnswer", "findings", "caveats"],
  properties: {
    summary: { type: "string" },
    synthesisAnswer: { type: "string" },
    findings: { type: "array", items: {
      type: "object", required: ["subProblemId", "claim", "confidence", "sources", "evidence", "vote"],
      properties: {
        subProblemId: { type: "string" },
        claim: { type: "string" },
        confidence: { type: "string", enum: ["high", "medium", "low"] },
        sources: { type: "array", items: { type: "string" } },
        evidence: { type: "string" },
        vote: { type: "string" },
      },
    }},
    caveats: { type: "string" },
    probeList: { type: "array", items: { type: "string" } },
    openQuestions: { type: "array", items: { type: "string" } },
  },
}

// ─── URL/label hardening (ported from deep-research) ───
const URL_HOST_PATTERN = /^[a-z][a-z0-9+.-]*:\/\/(?:[^/?#\\]*@)?(?:www\.)?([^/:?#@\\]+)(?::\d+)?([^?#]*)/i
const normURL = u => {
  const m = String(u).match(URL_HOST_PATTERN)
  return m ? (m[1] + m[2].replace(/\/$/, "")).toLowerCase() : String(u).toLowerCase()
}
const LABEL_CAP = 40
const LABEL_STRIP = /[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿"“-‟″‶❝❞〝〞＂]/g
const STRICT_HOST = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/
const stripLabelChars = s => String(s).replace(LABEL_STRIP, "")
const quotedLabel = s => {
  const cps = Array.from(stripLabelChars(s))
  return '"' + cps.slice(0, LABEL_CAP).join("").trim() + (cps.length > LABEL_CAP ? "…" : "") + '"'
}
// v6.5 DRY-1: confidence 排序权重常量(消除重复 magic number)
const CONF_RANK = { high: 3, medium: 2, low: 1 }
// v6.5 DRY-2: bestVerdict helper(消除 c.verdicts.filter/sort 重复)
const bestVerdict = c => c.verdicts && c.verdicts.length
  ? c.verdicts.filter(v => !v.refuted).sort((a, b) => (CONF_RANK[b.confidence] || 0) - (CONF_RANK[a.confidence] || 0))[0]
  : null
const seen = new Map()
const dupes = []
const budgetDropped = []
const relRank = { high: 0, medium: 1, low: 2 }
// v6.5 S9 修复: 余数分配 + 保证每队 ≥ 1 slot(原 v6.4 N1 砖化边界: 16 队+15 fetch 时 1 队仍 0 slot)
const baseSlots = Math.max(1, Math.floor(MAX_FETCH / Math.max(TEAM_IDS.length, 1)))
const remainder = MAX_FETCH - baseSlots * Math.max(TEAM_IDS.length, 1)
const fetchSlotsByTeam = new Map(TEAM_IDS.map((id, idx) => [id, baseSlots + (idx < remainder ? 1 : 0)]))

if (!TASK) {
  return { error: "No task provided. Pass it as args: Workflow({scriptPath, args: {task: '<目标任务>'}})." }
}

// ─── Prompts ───
const toolsetHint = (toolset) => {
  const parts = ["WebSearch/WebFetch 始终可用。"]
  if (toolset && toolset.market) parts.push("若相关，可使用公开市场数据接口获取行情等一手数据。")
  if (toolset && toolset.code) parts.push("若相关，可执行代码验证计算。")
  return parts.join(" ")
}

// ─── Phase 0 prompts: ConstitutionForge 制宪会议 ───
const SPEAKER_PROMPT =
  "## 制宪会议 — 议长意图分析(阶段0a)\n\n" +
  "命题: \"" + TASK + "\"\n\n" +
  "你是本次制宪会议的议长，拥有议程设置权。人类宪法史表明：谁控制议程谁就控制结果，因此你的议程必须中立、完备、可被议员挑战。\n\n" +
  "## 任务\n" +
  "1. **intentSummary**: 用 2-3 句提炼命题的真实意图(要回答什么/交付什么)。\n" +
  "2. **agenda**: 2-6 个本次博弈**必须立法约束**的议题。每个议题:\n" +
  "   - issue: 议题名(如\"检索范围边界\"/\"排除方向\"/\"来源质量标准\")\n" +
  "   - whyConstrain: 不约束会怎样(范围蔓延/资源无底洞/不可证伪/无法终止等)\n\n" +
  "议程议题应覆盖: 范围边界 / 排除方向 / 资源上限 / 证据标准 / 终止条件 中与本命题真正相关的维度，不相关的不要硬凑。\n\nStructured output only."

const DELEGATE_PROMPT = (delegate, agenda) =>
  "## 制宪会议 — 议员提案(阶段0b)\n\n" +
  "命题: \"" + TASK + "\"\n\n" +
  "议长议程:\n" + agenda.map((a, i) => (i + 1) + ". " + a.issue + " — " + a.whyConstrain).join("\n") + "\n\n" +
  "你是议员 **" + delegate.name + "**。\n" +
  "你代表的利益: " + delegate.interest + "\n" +
  "你的立场指引: " + delegate.directive + "\n\n" +
  "## 任务\n针对议程提交 1-4 条约束条款草案(articles)。每条:\n" +
  "- type: scope(范围) / exclusion(排除) / resource(资源) / evidence(证据) / termination(终止)\n" +
  "- text: 条款正文——必须**具体、可执行、可裁决**(\"检索仅限X类来源\"而非\"注意来源质量\")\n" +
  "- rationale: 立法理由(从你的立场出发)\n\n" +
  "## 规则\n" +
  "- 相关性规则(germaneness): 条款必须与命题直接相关，无关条款将被委员会退回并记录\n" +
  "- 你只能提案，不能自批——入法需要 4 名议员中 ≥3 票赞成(2/3 超多数)\n\nStructured output only."

const COMMITTEE_PROMPT = (agenda, proposals) =>
  "## 制宪会议 — 委员会整合(阶段0c)\n\n" +
  "命题: \"" + TASK + "\"\n\n" +
  "议长议程:\n" + agenda.map((a, i) => (i + 1) + ". " + a.issue).join("\n") + "\n\n" +
  "你是制宪委员会(参照1787年费城会议 Committee of Detail：把辩论成果整合为精确文本)。\n\n" +
  "4 位议员提交的条款草案:\n" +
  proposals.map(p =>
    "### " + p.delegate.name + " (" + p.delegate.interest + ")\n" +
    p.articles.map(a => "- [" + a.type + "] " + a.text + "\n  理由: " + a.rationale).join("\n")
  ).join("\n\n") + "\n\n" +
  "## 任务\n" +
  "1. **合并**语义重复条款(保留最强、最具体的表述)，消解直接冲突(无法调和的标 contested: true)。\n" +
  "2. **相关性审查**: 与命题无直接关系的条款(立法 rider/夹带私货)退回 rejected 并注明理由——参照希腊宪法74条/捷克宪法法院对\"野骑手\"的否定立场。\n" +
  "3. 把保留条款重写为**最终立法语言**: 具体、可执行、可裁决，编号 A1..An，标注 type/rationale/contested。总条款数 ≤10。\n" +
  "4. **eternityProposal**: 提炼 0-3 条\"永恒条款\"候选——博弈中途**绝不可修改**的元规则(如\"所有 claim 必须可证伪且带来源\")。宁缺毋滥。\n" +
  "5. **E4 硬约束(若任务可能涉及算法/代码/可执行验证)**: 如果命题包含可被脚本实现/实跑验证的算法(典型: 数值计算/工程实现/数据科学/自动化决策), 必须提出永恒条款 **E4**: " +
  "\"任何算法/可执行类 claim 必须附 (i) 实际编写的脚本路径+SHA256 (ii) 真实运行的 stdout 关键输出 (iii) 落盘数据路径+SHA256 (iv) falsification 条件 (v) 独立验证者可重跑的命令. " +
  "缺一即被 Verify 阶段视为 refuted=true(E4 单独否决). 评委必须独立重跑同脚本验证真实性, 失败=不通过.\" " +
  "不适用则可在 eternityProposal 中显式说明'本任务为纯文献研究, 不需要 E4'。\n" +
  "6. **decidableTest(游戏内可判定性, v6.7 P3)**: 每条保留条款必须附 decidableTest — 裁决者在博弈进行期间用可获得的证据(引文/来源质量/artifact重跑结果)即可判定合规或违规的具体检验方法。**禁止把判定标准锚定在博弈结束后才存在的证据上**(如\"上线后的真实运行记录\"): 若核心约束只能靠未来证据判定, 必须改写为博弈内可判定的代理形式(如\"凡声称X但无博弈内证据者, 一律归 PROBE 轨, 不得作为交付结论\")。立法教训(Round5 实证): 证据门槛不可达 = 验证阶段空转(40 评委 0 淘汰)。\n\n" +
  "Structured output only."

const VOTE_PROMPT = (delegate, articles, eternity, round) =>
  "## 制宪会议 — 逐条表决(阶段0d" + (round === 2 ? "，复议轮/最后机会" : "") + ")\n\n" +
  "命题: \"" + TASK + "\"\n\n" +
  "你是议员 **" + delegate.name + "**(立场: " + delegate.directive + ")\n\n" +
  "## 表决规则(源自真实宪法制度)\n" +
  "- 普通条款: 4 名议员中 ≥3 票赞成(2/3 超多数)方可入法——社会选择理论证明 ~64% 超多数门槛可防止孔多塞投票循环\n" +
  "- 永恒条款: 4/4 全票方可入法(布坎南宪法经济学: 高外部成本决策须一致同意)\n" +
  "- 协商民主铁律: **每票必须附实质理由**，不允许裸投票\n" +
  (round === 2 ? "- 本条款第一轮未达门槛，已由委员会修正。这是最后表决机会，再不过将进入少数意见记录(minority_report)。\n" : "- 未达门槛的条款将获得一次修正后复议的机会(1787年制宪会议 reconsideration 规则)。\n") +
  "\n## 待表决条款\n" +
  articles.map(a => "**" + a.id + "** [" + a.type + "] " + a.text + "\n  立法理由: " + (a.rationale || "(修正条款)")).join("\n") +
  (eternity && eternity.length
    ? "\n\n## 永恒条款候选(须全票,id 在 e.id 字段原样照抄)\n" + eternity.map((e, i) => "**" + (e.id || "E" + (i + 1)) + "**: " + e.text + (e.rationale ? "\n  理由: " + e.rationale : "")).join("\n")
    : "") +
  "\n\n## 任务\n对每条条款投 approve true/false + reason(从你的立场实质权衡，而非盲从立场——协商民主要求认真权衡对方论点)。" +
  (eternity && eternity.length ? "\n永恒条款投 eternityVotes({id: <上面 E 编号原样>, approve: true/false, reason: <实质理由>})。注意: id 字段填上面显示的 E 编号(如 E1/E2/E3),不要填 text。" : "\n无永恒条款时 eternityVotes 省略。") +
  "\n\nStructured output only."

const AMEND_PROMPT = (failed) =>
  "## 制宪会议 — 僵局修正(阶段0e，1787 reconsideration 规则)\n\n" +
  "命题: \"" + TASK + "\"\n\n" +
  "以下条款第一轮表决未达 2/3 门槛。你是制宪委员会，参照各议员的反对理由**修正措辞**，使其有机会获得超多数——但不能阉割条款的核心约束意图，也不能加入与命题无关的内容(相关性规则仍适用)。\n\n" +
  "未过条款与表决记录:\n" +
  failed.map(f =>
    "### " + f.id + " [" + f.type + "] " + f.text + "\n表决: " + f.vote + "\n反对理由:\n" +
    f.noReasons.map(r => "- " + r).join("\n")
  ).join("\n\n") +
  "\n\n## 任务\n输出 amended: 每条 {id, text(修正后正文), amendmentNote(你改了什么、为何能化解反对)}。不修正无法挽救的条款可以不返回。\n\nStructured output only."

const PROBLEMFORGE_PROMPT = (constitutionBlock) =>
  "## ProblemForge — 把目标任务转化为求解任务\n\n" +
  "## 目标任务\n" + TASK + "\n\n" +
  (constitutionBlock ? constitutionBlock + "\n**铁律: 你设计的每个子问题必须完全处于上述约束宪法的 scope 条款之内，且不得触碰任何 exclusion 条款。rules 数组第一条必须是\"所有检索/声明/报告不得违反约束宪法 A1-An\"。**\n\n" : "") +
  "## 任务\n把目标任务分解为一场求解竞赛：\n" +
  "1. **taskType**: 判断任务类型 research(纯网络调研) / market(市场/金融数据分析) / code(代码/实现) / hybrid(混合)。\n" +
  "2. **mainFlag**: 主问题 —— 该任务的最终答案/交付物是什么(一句话)。\n" +
  "3. **subProblems**: 2-6 个子问题 —— 必须逐个攻下的关键子问题。每个子问题有难度(easy=5分, medium=10分, hard=20分)和分值。子问题必须互相独立、共同覆盖主问题。\n" +
  "4. **rules**: 3-5 条竞赛规则(证据必须可证伪、必须引用来源、禁止臆测、跨来源交叉验证等)。\n" +
  "5. **scoring**: 计分规则说明。\n" +
  "6. **toolset**: 根据 taskType 自动适配工具集(market→market:true, code→code:true)。\n\n" +
  "子问题问题必须是具体的、可被证据回答的，不能是笼统废话。\n\nStructured output only."

const TEAM_SEARCH_PROMPT = (team, manifest, constitutionBlock) =>
  "## 求解竞赛 — 搜索阶段\n\n" +
  "任务: \"" + manifest.task + "\"\n主问题: " + manifest.mainFlag + "\n\n" +
  (constitutionBlock ? constitutionBlock + "\n**违宪警告: 触碰 exclusion 条款或超出 scope 条款的检索方向浪费全队预算且产出的 claim 会被宪法法院票淘汰。**\n\n" : "") +
  "子问题清单:\n" + manifest.subProblems.map(f => "- " + f.id + " [" + f.difficulty + "/" + f.points + "分] " + f.question).join("\n") + "\n\n" +
  "你的队伍: **" + team.name + "** (" + team.strategy + ")\n" +
  "你的进攻方向: " + team.directive + "\n" +
  "可用工具: " + toolsetHint(manifest.toolset) + "\n\n" +
  "## 任务\n按你的队伍策略，针对子问题进行 WebSearch(可多次搜索，覆盖 3-5 个不同查询角度)。\n" +
  "返回最相关的 4-6 条结果，按与原任务的相关性排序。跳过 SEO 内容农场。\n" +
  "每条结果附简短 snippet 说明为何与子问题相关。\n\nStructured output only."

const FETCH_PROMPT = (source, team, manifest, constitutionBlock) =>
  "## 求解竞赛 — 来源提取\n\n" +
  "任务: \"" + manifest.task + "\"\n" +
  (manifest.taskType ? "任务类型: " + manifest.taskType + " — " + (manifest.taskType === "research" ? "纯文献研究, 不强制 E4 artifact" : "**E4 永恒条款生效: 策略/算法/可执行类 claim 必须附 artifact, 缺一即被 Verify 阶段 refuted**") + "\n" : "") +
  "\n" +
  (constitutionBlock ? constitutionBlock + "\n" : "") +
  "子问题ID清单:\n" + manifest.subProblems.map(f => "- " + f.id + ": " + f.question).join("\n") + "\n\n" +
  "抓取来源:\n**URL:** " + source.url + "\n**Title:** " + source.title + "\n**发现队伍:** " + team.name + " (" + team.strategy + ")\n\n" +
  "## 任务\n1. 用 WebFetch 抓取页面。\n" +
  "2. 评估来源质量: primary(一手/机构) / secondary(二手报道) / blog / forum / unreliable。" +
  (constitutionBlock ? " 若来源违反宪法的 evidence(证据标准)条款，直接降级为 unreliable。" : "") + "\n" +
  "3. 提取 2-5 条**可证伪**的 claims。每条必须:\n" +
  "   - 具体可检验，非泛泛而谈\n" +
  "   - 带直接引文作为证据\n" +
  "   - 标注重要性 central/supporting/tangential\n" +
  "   - **subProblemId**: 该 claim 支持哪个子问题(从清单中选择最贴切的一个; 若不属于任何子问题用 \"F0\")。\n" +
  (constitutionBlock ? "   - **合宪性**: 触碰 exclusion 条款或超出 scope 条款的 claim 直接丢弃，不要提交。\n" : "") +
  (ENFORCE_ARTIFACT && manifest.taskType && manifest.taskType !== "research"
    ? "   - **E4 实际执行硬约束**: 如果 claim 提出/描述/推荐一个**可被脚本实现或实跑验证的策略/算法/参数/阈值**, 你必须**实际编写脚本 → 实际运行实跑 → 实际落盘数据**, 然后在 claim 字段下附加 **artifact** 对象, 包含: \n" +
      "     * `scriptPath`: 你用 Write/Edit 工具创建的脚本文件路径\n" +
      "     * `sha256`: 脚本文件的 SHA256(可用 `certutil -hashfile <path> SHA256` 或 `sha256sum` 算)\n" +
      "     * `stdout`: 实际实跑的 stdout 关键输出(<8KB, 截取含数字的部分)\n" +
      "     * `dataPath`: 落盘数据/日志/订单的路径\n" +
      "     * `dataSha256`: 落盘数据的 SHA256(可选但强烈建议)\n" +
      "     * `falsification`: 失败条件(若 X 发生则策略失效, 用于反证自己)\n" +
      "     * `reproduceCommand`: 独立验证者可一行重跑的命令(如 `python script.py --config X`)\n" +
      "     ⚠️ 缺 artifact = Verify 阶段 E4 单独否决(refuted=true, unconstitutional=eternity-E4). 没有真实脚本/实跑就不要提策略类 claim, 改提观察性 claim。\n"
    : "") +
  "4. 标注发布/更新时间(若有)。\n\n" +
  "抓取失败/无关/paywalled → claims: [] 且 sourceQuality: \"unreliable\"。\n\nStructured output only."

// v6.7 P2: 评委五视角(修复克隆评委: Round5 五个相同 prompt → 投票高度相关 → 每策略最多 1 张异见票, 40 票仅 4 反驳)
const JUDGE_LENSES = [
  { id: "data", name: "数据完整性", focus: "引文是否真实支持 claim？来源数据是否有缺陷/伪影/口径错误？关键数字能否独立复算？" },
  { id: "math", name: "逻辑与数学", focus: "概率/统计/EV 推断是否成立？样本量、置信区间、生存者偏差、过拟合、多重比较？" },
  { id: "reach", name: "证据可达性", focus: "claim 的关键证据在本场博弈内是否可获得？若必须依赖博弈外/未来证据(上线后数据/未发生事件) → PROBE。你是'诚实护城河'守门员：标注'理论值/未验证'不构成豁免。" },
  { id: "constitution", name: "合宪性", focus: "是否违反 scope/exclusion/evidence/termination/永恒条款？越界即 REJECTED 且 unconstitutional=true，引用条款号。" },
  { id: "adversarial", name: "对抗与逆向选择", focus: "什么现实情形下此 claim 系统性失效？逆向选择、对手行为、均值回归、edge 衰减、队列位置？" },
]

const VERIFY_PROMPT = (claim, v, constitutionBlock) => {
  const lens = JUDGE_LENSES[v % JUDGE_LENSES.length]
  return (
  "## 对抗验证 — 评委 " + (v + 1) + "/" + VOTES_PER_CLAIM + " · 专属视角: " + lens.name + "\n\n" +
  "任务: \"" + TASK + "\"\n\n" +
  "你的专属审查视角: **" + lens.name + "** — " + lens.focus + "\n" +
  "其余评委从其他视角审查同一 claim；请专注你的视角深挖，不要泛泛复核。\n\n" +
  (constitutionBlock ? constitutionBlock + "\n" : "") +
  "## 待验证 claim\n\"" + claim.claim + "\"\n\n" +
  "**来源:** " + claim.sourceUrl + " (" + claim.sourceQuality + ")\n" +
  "**支持引文:** \"" + claim.quote + "\"\n" +
  (claim.artifact
    ? "**E4 Artifact 提交:**\n" +
      "  - scriptPath: " + (claim.artifact.scriptPath || "(未填)") + "\n" +
      "  - sha256: " + (claim.artifact.sha256 || "(未填)") + "\n" +
      "  - stdout: " + ((claim.artifact.stdout || "").slice(0, 1500)) + "\n" +
      "  - dataPath: " + (claim.artifact.dataPath || "(未填)") + "\n" +
      "  - falsification: " + (claim.artifact.falsification || "(未填)") + "\n" +
      "  - reproduceCommand: " + (claim.artifact.reproduceCommand || "(未填)") + "\n"
    : ENFORCE_ARTIFACT ? "**E4 警告: 此 claim 未附 artifact(策略/算法类必须附)**\n" : ""
  ) +
  "\n## 检查清单\n" +
  (constitution && constitutionBlock
    ? "0. **违宪审查(宪法法院)**: 该 claim 是否超出 scope 条款 / 触碰 exclusion 条款 / 违反 evidence 条款？越界即 refuted=true 且 unconstitutional=true，evidence 引用具体条款号(A1/An)。**为真但越界的 claim 照样淘汰**。\n"
    : constitution === null
      ? "0. **基础审查**(无宪法模式 — S1 降级触发,无宪法约束): claim 是否被引文支持? unconstitutional 字段请保持 false (无宪法 = 无违宪审查)。\n"
      : "0. **基础审查**(无宪法模式,CONFIG.constitution === false 关闭): claim 是否被引文支持? unconstitutional 字段忽略。\n"
  ) +
  (ENFORCE_ARTIFACT && claim.artifact
    ? "0.5. **E4 实际执行独立验证(v6.8 三态)**: 评委必须**真正独立重跑**提交者提供的 `reproduceCommand`(若不可用则用 `python <scriptPath>`), 然后: \n" +
      "   - (a) 脚本 SHA256 是否匹配提交的 `sha256`?\n" +
      "   - (b) 实际 stdout 是否与提交的 `stdout` 一致(允许合理浮动, 如时间戳/随机数)?\n" +
      "   - (c) 落盘数据 `dataPath` 是否存在? dataSha256 是否匹配(若有)?\n" +
      "   - (d) `falsification` 条件是否被此次实跑违反(违反 = claim 失效)?\n" +
      "   **三态判定(v6.8, 区分基础设施失败与证据造假, 避免误杀真 claim):**\n" +
      "   - **重跑成功 + (b)(d) 通过** → E4 证据闭合, 该项可支撑 DEPLOYABLE。\n" +
      "   - **重跑成功但 (b) 结果不符 或 (d) falsification 被违反** → 硬证伪: track=REJECTED, evidence 写明哪一项失败, counterSource='E4-self-check-failed'。\n" +
      "   - **(a) SHA256 不符 / (c) dataPath 缺失 / 无法独立重跑(Bash 不通/超时/沙箱拒绝)** → 证据无法在博弈内闭合: 该项记 track=PROBE(不是 REJECTED, 不据此淘汰; 可能是提交者笔误或环境限制), evidence 写明具体原因, counterSource='E4-unverifiable'。**不要让\"无法重跑\"杀死可能是真的 claim。**\n" +
      "   **若 (b)(d) 之外你仍要投 REJECTED, 必须给出独立于 E4 的实质反驳理由。**\n"
    : ENFORCE_ARTIFACT
      ? "0.5. **E4 artifact 缺失**: 策略/算法类 claim 必须附 artifact(脚本+SHA256+实跑 stdout+落盘数据+falsification+reproduceCommand)。本 claim 未附 → track=PROBE(证据缺失可后续补, 不据此 REJECTED), evidence='E4 artifact missing for executable claim'。仅当你能独立找到该 claim 被证伪的实质反证时才 REJECTED。\n"
      : ""
  ) +
  "1. [你的视角深挖] " + lens.focus + "\n" +
  "2. claim 是否真的被引文支持，还是过度解读/误读？\n" +
  "3. WebSearch 寻找矛盾证据 — 是否有可信来源反驳或严重限定？\n" +
  "4. 来源质量是否匹配 claim 强度？(惊人之论需要一手来源)\n" +
  "5. claim 是否过时？(快变领域的老说法可疑)\n" +
  "6. 是否是营销话术/新闻稿/挑数据/论坛猜测？\n\n" +
  "## 三轨裁决(v6.7, 不再是二元反驳)\n" +
  "你必须对这条 claim 投出**三轨之一**(track 字段):\n" +
  "- **DEPLOYABLE**: claim 的证据在本场博弈内已闭合 — 被引文支持、来源质量匹配、" + (ENFORCE_ARTIFACT ? "E4 artifact 独立重跑通过、" : "") + (constitutionBlock ? "合宪、" : "") + "你的视角下找不到实质反驳。可作为最终结论交付。\n" +
  "- **PROBE**: claim 的核心断言依赖本场博弈内**不存在的证据**(未来运行数据/未发生事件/博弈外实验)。⚠️ **诚实标注\"理论值/未验证\"不能让 claim 自动幸存——它只是让 claim 进 PROBE 轨而非 REJECTED 轨。** 这是对 Round5 '诚实护城河'(40 评委 0 淘汰)的修复。\n" +
  "- **REJECTED**: 不被引文支持/被矛盾证据反驳/来源质量不足/过时/营销废话" + (constitutionBlock ? "/违宪" : "") + (ENFORCE_ARTIFACT ? "/E4 artifact 缺失或独立重跑失败" : "") + "。\n\n" +
  "**refuted 字段 = (track === \"REJECTED\")**。\n" +
  "裁决指引: 证据在游戏内存在且充分 → DEPLOYABLE; 证据在游戏内存在但不足/需未来数据 → PROBE; 有反证或违规 → REJECTED。不确定时: 证据在游戏内存在但你不确定 → 深入查; 证据在游戏内不存在 → PROBE; 有反证 → REJECTED。\n\nStructured output only. Evidence 必须具体。"
  )
}

const SYNTHESIS_PROMPT = (manifest, allConfirmed, leaderboard, constitutionBlock, probes, killed) => {
  // v6.1 M2: 跨队融合(不再只取领先队) — 每条 claim 标注队伍归属
  const blocks = allConfirmed.map((c, i) =>
    "### [" + i + "] " + (c.claim || "").slice(0, 500) + (c.claim && c.claim.length > 500 ? "…" : "") + "\n" +
    "子问题: " + c.subProblemId + " · 队伍: " + (c.team && c.team.name ? c.team.name : "?") + " · Vote: " + (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes +
    " · Source: " + c.sourceUrl + " (" + c.sourceQuality + ")\n" +
    "Quote: \"" + c.quote + "\"\nEvidence: " + (c.verdicts && c.verdicts.length ? (c.verdicts.filter(v => !v.refuted).sort((a, b) => (CONF_RANK[b.confidence] || 0) - (CONF_RANK[a.confidence] || 0))[0]?.evidence || c.quote || "(无证据)") : c.quote || "(无证据)") + "\n"
  ).join("\n")
  // v6.7 P5: PROBE 清单 + REJECTED 异见证据(少数意见是资产 — Round5 最锋利分析来自反驳票)
  const probeBlock = probes && probes.length
    ? "\n## 探针轨 claims(PROBE ×" + probes.length + " — 博弈内证据未闭合, ⚠️禁止当作已证实结论写入 findings, 应整理为下一步博弈外验证清单 probeList):\n" +
      probes.slice(0, 15).map((c, i) =>
        "- [P" + i + "] " + (c.claim || "").slice(0, 300) + " (队:" + (c.team && c.team.name ? c.team.name : "?") + " · 轨票 D" + (c.trackVotes ? c.trackVotes.DEPLOYABLE : "?") + "/P" + (c.trackVotes ? c.trackVotes.PROBE : "?") + "/R" + (c.trackVotes ? c.trackVotes.REJECTED : "?") + ")"
      ).join("\n") + "\n"
    : ""
  const dissentBlock = killed && killed.length
    ? "\n## 异见证据(REJECTED ×" + killed.length + " — 少数意见是资产: 这些反驳理由是 caveats 的一手素材, 必须在 caveats 中吸收):\n" +
      killed.slice(0, 10).map((c, i) => {
        const refuteV = c.verdicts && c.verdicts.length ? c.verdicts.filter(v => v.refuted || v.unconstitutional || v.track === "REJECTED").sort((a, b) => (CONF_RANK[b.confidence] || 0) - (CONF_RANK[a.confidence] || 0))[0] : null
        return "- [R" + i + "] " + (c.claim || "").slice(0, 200) + " → 反驳: " + ((refuteV && refuteV.evidence ? refuteV.evidence : "(无理由)").slice(0, 300))
      }).join("\n") + "\n"
    : ""
  const topTeam = leaderboard[0]
  const teamCount = new Set(allConfirmed.map(c => c.team && c.team.id).filter(Boolean)).size
  return (
    "## 综合结论合成 — 最终报告（v6.7 跨队融合 + 三轨）\n\n" +
    "任务: \"" + manifest.task + "\"\n主问题: " + manifest.mainFlag + "\n\n" +
    (constitutionBlock ? constitutionBlock + "\n**报告开头必须声明本报告依据的约束宪法版本与条款范围。**\n\n" : "") +
    "🏆 领先队伍: **" + topTeam.name + "** (" + topTeam.strategy + ") 得分 " + topTeam.score + "（按其幸存claims数+质量胜出，但本报告融合所有队伍幸存证据以最大化覆盖率）\n\n" +
    "可部署 claims(DEPLOYABLE ×" + allConfirmed.length + ", 跨 " + teamCount + " 队):\n" + blocks + "\n" +
    probeBlock + dissentBlock + "\n" +
    "## 排行榜\n" +
    leaderboard.map(t => "- " + t.rank + ". " + t.name + " (" + t.strategy + "): " + t.score + "分 · 求解" + t.capturedFlags + " · 幸存" + t.survived + "/探针" + (t.probed || 0) + "/被驳" + t.refuted).join("\n") + "\n\n" +
    "## 竞赛规则\n" + manifest.rules.join("; ") + "\n\n" +
    "## 任务\n" +
    "1. 写出 3-5 句执行摘要直接回答主问题(summary)。若 DEPLOYABLE 证据不足, 摘要必须明说'博弈内证据未闭合', 禁止用 PROBE 内容冒充结论。\n" +
    "2. synthesisAnswer: 主问题的直接答案(详尽、自包含)。\n" +
    "3. findings: 按子问题组织，合并语义重复项。**findings 只能使用 DEPLOYABLE claims**。每条带来源引用、验证票数、置信度。\n" +
    "4. probeList: 把 PROBE 轨 claims 整理为下一步博弈外验证清单(每条一句话: 验什么/怎么验/什么结果会证伪)。\n" +
    "5. caveats: 不确定项、弱来源、时效性、**异见证据(REJECTED 反驳理由)的正面吸收**" + (constitutionBlock ? "、约束宪法导致的覆盖缺口(少数意见中可能有线索)" : "") + "。\n" +
    "6. openQuestions: 2-4 个未解答的开放问题。\n\nStructured output only."
  )
}

// v6.1 M6: 多轮修补循环(兑现 SKILL.md 机制3/4/6 — 攻防一体/多轮修补/对手修补)
const PATCH_PROMPT = (team, manifest, winnerClaims, prevPatches, round) =>
  "## PatchLoop — 多轮修补(第 " + round + " 轮)\n\n" +
  "任务: \"" + manifest.task + "\"\n主问题: " + manifest.mainFlag + "\n\n" +
  "你的队伍: **" + team.name + "** (" + team.strategy + ")\n\n" +
  "## 修补目标\n" +
  "针对已确认的 findings 提交 0-3 条修补提案(patches)。\n" +
  "- 当本任务为\"技能审计\"型时(主问题提到 skill/wf.js/致命漏洞/可优化): 修补=对 skill 本身(`.agents/skills/adversarial-research/{adversarial-research.wf.js, SKILL.md}`)已发现 fatal flaw 的代码/文档修复\n" +
  "- 当本任务为常规研究时: 修补=对 winnerClaims 中可疑/弱证据/不完整结论的深化方案或交叉验证补充\n\n" +
  "## 已确认发现(供你参考作为修补对象)\n" +
  winnerClaims.slice(0, 12).map((c, i) => "[" + i + "] " + c.claim.slice(0, 200) + (c.claim.length > 200 ? "…" : "") + " (Vote " + (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes + ", 队:" + (c.team && c.team.name ? c.team.name : "?") + ")").join("\n") + "\n\n" +
  (prevPatches && prevPatches.length
    ? "## 上一轮已采纳的修补(不要重复, 改提补丁的补丁或新flaw的修补)\n" + prevPatches.map(p => "- " + p.flawId + ": " + p.title + " (队:" + p.team + ", 评 " + p.approved + "/3)").join("\n") + "\n\n"
    : "") +
  "## 轮次策略\n" +
  (round === 1 ? "第 1 轮 = 决胜修补. 优先修补 fatal/高优先级 flaw, 改法具体可粘贴." : "第 " + round + " 轮 = 修补的修补. 修补修补引入的回归/副作用, 或修补第 1 轮未覆盖的边缘 case.") + "\n\n" +
  "## 输出\n每条 patch: {flawId, title, description, diff, targetFile, targetLines, riskNote}\n" +
  "  - diff 必须具体可粘贴(伪diff/自然语言改动说明均可, 但要能让工程师照着改)\n" +
  "  - targetFile/targetLines: 指出改动落在哪个文件的哪几行\n" +
  "  - riskNote: 副作用/回归风险\n\nStructured output only."

const PATCH_VERIFY_PROMPT = (patch, v, task, prevPatches) =>
  "## 修补验证 — 评委 " + (v + 1) + "/3\n\n" +
  "任务: \"" + task + "\"\n\n" +
  "## 待验证 patch\n" +
  "目标 flaw: " + patch.flawId + "\n" +
  "标题: " + patch.title + "\n" +
  "描述: " + patch.description + "\n" +
  "目标: " + (patch.targetFile || "?") + ":" + (patch.targetLines || "?") + "\n" +
  "改动: " + patch.diff + "\n" +
  "风险: " + (patch.riskNote || "(未注明)") + "\n\n" +
  (prevPatches && prevPatches.length
    ? "## 已采纳的修补(检查此 patch 是否与已采纳冲突/重复)\n" + prevPatches.map(p => "- " + p.flawId + ": " + p.title + " (队:" + p.team + ", 评 " + p.approved + "/3)").join("\n") + "\n\n"
    : "") +
  "## 检查清单\n" +
  "1. 改动是否真正解决 flawId 指出的问题? (未解决 → approved=false, evidence 写明缺什么)\n" +
  "2. 是否引入新回归? 与已采纳的 patches 冲突吗?\n" +
  "3. 改动是否最小化、具体、可执行?\n" +
  "4. 是否存在更简单的修法被忽略?\n\n" +
  "approved=true 仅当: 修复有效 + 无明显回归 + 改动具体可执行\n" +
  "approved=false 当: 未解决 / 引入回归 / 改动模糊 / 复杂度高于必要\n" +
  "不确定时默认 approved=false.\n\nStructured output only."

// ─── Phase 0: Constitution — 制宪会议 ───
// 制度设计依据: 三读程序(提案→委员会→表决) / 2/3超多数(阿罗定理防循环) / 永恒条款全票(布坎南一致同意)
//              / 相关性规则(germaneness) / 1轮复议(1787 reconsideration) / 刚性锁死(Tsebelis零否决玩家) / 日落条款
let constitution = null
let constitutionBlock = ""
let constitutionCalls = 0

if (ENABLE_CONSTITUTION) {
  phase("Constitution")

  // 0a 议长意图分析(议程设置)
  const speaker = await retryAgent(SPEAKER_PROMPT, { label: "speaker:议长", phase: "Constitution", schema: SPEAKER_SCHEMA })
  constitutionCalls++
  if (!speaker) {
    log("⚠️ 议长议程失败 — 降级为无宪法模式继续")
  } else {
    log("议长议程: " + speaker.agenda.length + " 议题 — " + speaker.agenda.map(a => a.issue).join(" / "))

    // 0b 议员团提案(4 议员并行)
    const delegateDefs = DELEGATE_IDS.map(id => ({ id, ...DELEGATE_DEFS[id] }))
    const proposals = (await parallel(
      delegateDefs.map(d => () =>
        retryAgent(DELEGATE_PROMPT(d, speaker.agenda), { label: "提案:" + d.name, phase: "Constitution", schema: DELEGATE_SCHEMA })
          .then(r => r ? { delegate: d, articles: r.articles } : null)
      )
    )).filter(Boolean)
    constitutionCalls += delegateDefs.length
    log("议员提案: " + proposals.map(p => p.delegate.name + p.articles.length + "条").join(" | "))

    if (proposals.length === 0 || proposals.every(p => p.articles.length === 0)) {
      log("⚠️ 无有效提案 — 降级为无宪法模式继续")
    } else {
      // 0c 委员会整合(合并/冲突消解/相关性审查/永恒条款提炼)
      const committee = await retryAgent(COMMITTEE_PROMPT(speaker.agenda, proposals), { label: "committee:整合", phase: "Constitution", schema: COMMITTEE_SCHEMA })
      constitutionCalls++
      if (!committee || !committee.consolidated || committee.consolidated.length === 0) {
        log("⚠️ 委员会整合失败 — 降级为无宪法模式继续")
      } else {
        log("委员会: " + committee.consolidated.length + " 条入表决, " + (committee.rejected || []).length + " 条退回(rider), " + (committee.eternityProposal || []).length + " 条永恒候选")

        // 0d 逐条表决(2/3 超多数; 永恒条款全票; 每票附理由)
        const runVoteRound = (articles, eternity, round) =>
          parallel(
            delegateDefs.map(d => () =>
              retryAgent(VOTE_PROMPT(d, articles, eternity, round), { label: (round === 2 ? "复议:" : "表决:") + d.name, phase: "Constitution", schema: VOTE_SCHEMA })
            )
          )

        let ballots = (await runVoteRound(committee.consolidated, committee.eternityProposal || [], 1)).filter(Boolean)
        constitutionCalls += delegateDefs.length

        const tallyArticles = (articles, ballotsIn) => articles.map(a => {
          const votes = ballotsIn.map(b => (b.votes || []).find(v => v.id === a.id)).filter(Boolean)
          const yes = votes.filter(v => v.approve)
          const noReasons = votes.filter(v => !v.approve).map(v => v.reason || "(无理由)")
          return { ...a, yes: yes.length, total: votes.length, vote: yes.length + "-" + (votes.length - yes.length), passed: yes.length >= SUPERMAJORITY, noReasons }
        })

        let tallied = tallyArticles(committee.consolidated, ballots)
        let passed = tallied.filter(a => a.passed)
        let failed = tallied.filter(a => !a.passed)

        // 永恒条款: 全票(4/4)方可入法(委员会提交id,议员按id投票 — 修复 v6.0 M4 text严格匹配静默蒸发)
        // v6.5 NEW-8 修复: ballot 端 fallback 用 eternity 索引 (eIdx+1) 而非 ballot 索引 (bIdx+1),防 4 议员全偏离 schema 时 fallback 散落到 4 个不同 eternity
        const eternityTallied = (committee.eternityProposal || []).map((e, eIdx) => {
          const eId = e.id || "E" + (eIdx + 1)
          const votes = ballots.map(b => (b.eternityVotes || []).find(v => (v.id || "E" + (eIdx + 1)) === eId)).filter(Boolean)
          const yes = votes.filter(v => v.approve).length
          return { id: eId, text: e.text, rationale: e.rationale || "", vote: yes + "-" + (votes.length - yes), yes, total: votes.length, passed: yes >= ETERNITY_QUORUM && votes.length >= ETERNITY_QUORUM }
        })
        const eternityPassed = eternityTallied.filter(e => e.passed)
        const eternityFailed = eternityTallied.filter(e => !e.passed)

        log("第一轮表决: " + passed.length + " 过 / " + failed.length + " 未过 · 永恒条款 " + eternityPassed.length + "过/" + eternityFailed.length + "未过 / " + (committee.eternityProposal || []).length + "提议")

        // 0e 僵局修正 + 复议(仅 1 轮 — cloture 思想: 辩论必须有终结)
        if (failed.length > 0) {
          const amend = await retryAgent(AMEND_PROMPT(failed), { label: "committee:修正", phase: "Constitution", schema: AMEND_SCHEMA })
          constitutionCalls++
          const amended = (amend && amend.amended) || []
          if (amended.length > 0) {
            const revoteArticles = amended.map(m => {
              const orig = failed.find(f => f.id === m.id)
              return { id: m.id, type: orig ? orig.type : "scope", text: m.text, rationale: "修正: " + (m.amendmentNote || ""), contested: true }
            })
            const reballots = (await runVoteRound(revoteArticles, [], 2)).filter(Boolean)
            constitutionCalls += delegateDefs.length
            const retallied = tallyArticles(revoteArticles, reballots)
            const rescued = retallied.filter(a => a.passed)
            const dead = retallied.filter(a => !a.passed)
            passed = passed.concat(rescued)
            failed = failed.map(f => {
              const re = retallied.find(r => r.id === f.id)
              return re ? { ...f, text: re.text, vote: re.vote + " (复议)", amended: true, passed: re.passed } : f
            }).filter(f => !f.passed)
            log("复议: " + rescued.length + " 条救回, " + dead.length + " 条进入少数意见")
          } else {
            log("委员会放弃修正 — " + failed.length + " 条进入少数意见")
          }
        }

        // v6.2 S1 修复: 空宪法降级守卫(议会团灭不颁布0条款宪法,避免下游假性"严格")
        if (passed.length === 0 && eternityPassed.length === 0) {
          log("⚠️ 宪法空集降级 — 议会团灭,0条款颁布,本场降级为无约束模式")
          constitution = null
          constitutionBlock = ""
        } else {
        // 0f 颁布 constitution.json(刚性 locked + 日落 sunset)
        constitution = {
          version: 1,
          rigidity: "locked — 颁布后本次博弈内不可修正(Tsebelis: 零中途否决者=约束可信)",
          sunset: "本次博弈结束即失效(日落条款); 下次任务须重新制宪",
          intentSummary: speaker.intentSummary,
          eternity_articles: eternityPassed,
          articles: passed.map(a => ({ id: a.id, type: a.type, text: a.text, vote: a.vote, rationale: a.rationale || "", decidableTest: a.decidableTest || "" })),
          minority_report: failed.map(f => ({ id: f.id, type: f.type, text: (f.text || "").slice(0, 500), vote: f.vote, note: "未达 2/3 门槛" })).concat(eternityFailed.map(e => ({ id: e.id, type: "eternity", text: (e.text || "").slice(0, 500), vote: e.vote, note: "永恒条款未达 4/4 全票 — id 化匹配后落选静默已消除" }))),
          rejected_riders: (committee.rejected || []),
          quorum: { articles: "≥3/4 (2/3 超多数)", eternity: "4/4 (一致同意)" },
        }
        constitutionBlock =
          "## 约束宪法(constitution v1, 刚性+日落)\n" +
          "本博弈的唯一约束法，由制宪会议 4 名议员表决产生。你**必须**遵守，无例外。\n" +
          (constitution.eternity_articles.length
            ? "\n### 永恒条款(全票通过, 不可违反)\n" + constitution.eternity_articles.map(e => "- **" + e.id + "**: " + e.text).join("\n")
            : "") +
          "\n### 约束条款(2/3 超多数通过)\n" +
          constitution.articles.map(a => "- **" + a.id + "** [" + a.type + "] (" + a.vote + "通过) " + a.text + (a.decidableTest ? "\n  判定: " + a.decidableTest : "")).join("\n") +
          (constitution.minority_report.length
            ? "\n\n### 少数意见(2-2 条款 + 永恒条款落选, 下次制宪参考)\n" + constitution.minority_report.map(m => "- **" + m.id + "** " + (m.type === "eternity" ? "[永恒] " : "") + "(" + m.vote + ") " + m.text + (m.note ? " — " + m.note : "")).join("\n")
            : "")
        log("✅ 宪法颁布: " + constitution.articles.length + " 条款 + " + constitution.eternity_articles.length + " 永恒条款 + " + constitution.minority_report.length + " 少数意见")
        } // v6.2 S1: end of else (constitution != null)
      }
    }
  }
} else {
  log("制宪会议已禁用(config.constitution=false) — 无约束模式")
}

// ─── Phase 1: ProblemForge — 问题分解 ───
phase("ProblemForge")
const manifest = await retryAgent(PROBLEMFORGE_PROMPT(constitutionBlock), { label: "problemforge", phase: "ProblemForge", schema: PROBLEMFORGE_SCHEMA })
if (!manifest) {
  return { error: "ProblemForge agent returned no result — cannot build the flag manifest.", constitution }
}
log("TaskType: " + manifest.taskType + " · " + manifest.subProblems.length + " 子问题")
log("子问题: " + manifest.subProblems.map(f => f.id + "[" + f.difficulty + "/" + f.points + "]").join(", "))
log("主问题: " + manifest.mainFlag.slice(0, 60) + (manifest.mainFlag.length > 60 ? "…" : ""))

const problemPoints = {}
for (const f of manifest.subProblems) problemPoints[f.id] = f.points

// ─── Phase 2: Compete — 4 队竞争(共享 URL 去重, 宪法约束内) ───
// v6.1 M1 修复: teamDefs 补 id 字段(对照 :431 delegateDefs 写法), 否则 c.team.id === team.id = undefined===undefined 恒真 → 计分全坍塌综合结论恒T0
const teamDefs = TEAM_IDS.map(id => ({ id, ...TEAM_DEFS[id] })).filter(t => t.name)

const competeResults = await pipeline(
  teamDefs,

  team => retryAgent(TEAM_SEARCH_PROMPT(team, manifest, constitutionBlock), {
    label: "search:" + team.name, phase: "Compete", schema: SEARCH_SCHEMA,
  }).then(r => {
    if (!r) return null
    log(team.name + ": " + r.results.length + " URLs")
    return { team, results: r.results }
  }),

  searchResult => {
    if (!searchResult) return null
    const sorted = [...searchResult.results].sort((a, b) => relRank[a.relevance] - relRank[b.relevance])
    const novel = sorted.filter(r => {
      const key = normURL(r.url)
      if (seen.has(key)) {
        dupes.push({ ...r, team: searchResult.team.name, dupOf: seen.get(key) })
        // v6.4 S9.2 修复: dupes 也扣 slot(否则 1 队刷 dupes 占满其他队实际预算)
        const teamSlotsD = fetchSlotsByTeam.get(searchResult.team.id) ?? 0
        if (teamSlotsD > 0) fetchSlotsByTeam.set(searchResult.team.id, teamSlotsD - 1)
        return false
      }
      // v6.2 S9 修复: per-team 配额(取本队剩余 slots,无 global 池); 去掉 high 豁免
      const teamSlots = fetchSlotsByTeam.get(searchResult.team.id) ?? 0
      if (teamSlots <= 0) {
        budgetDropped.push({ ...r, team: searchResult.team.name, reason: "team quota exhausted" })
        return false
      }
      seen.set(key, { team: searchResult.team.name, title: r.title })
      fetchSlotsByTeam.set(searchResult.team.id, teamSlots - 1)
      return true
    })
    if (novel.length < searchResult.results.length) {
      log(searchResult.team.name + ": " + novel.length + " novel (" + (searchResult.results.length - novel.length) + " dedup/budget)")
    }
    return parallel(
      novel.map(source => () => {
        const capturedHost = String(source.url).match(URL_HOST_PATTERN)?.[1] ?? ""
        const host = capturedHost.toLowerCase()
        const cleanHost = stripLabelChars(host)
        const isCleanBareHost = cleanHost === host && host !== "" && Array.from(host).length <= LABEL_CAP && STRICT_HOST.test(host)
        const hostLabel = cleanHost === "" ? "" : isCleanBareHost ? host : quotedLabel(host)
        const sourceLabel = hostLabel || (stripLabelChars(source.title).trim() && quotedLabel(source.title)) || "unknown"
        return retryAgent(FETCH_PROMPT(source, searchResult.team, manifest, constitutionBlock), {
          label: "fetch:" + sourceLabel,
          phase: "Compete",
          schema: EXTRACT_SCHEMA,
        }).then(ext => {
          if (!ext) return null
          return {
            url: source.url, title: source.title, team: searchResult.team,
            sourceQuality: ext.sourceQuality, publishDate: ext.publishDate,
            claims: ext.claims.map(c => ({ ...c, sourceUrl: source.url, sourceQuality: ext.sourceQuality })),
          }
        }).catch(e => {
          log("fetch failed: " + source.url + " — " + (e.message || e))
          return { url: source.url, title: source.title, team: searchResult.team, sourceQuality: "unreliable", claims: [] }
        })
      })
    )
  }
)

const allSources = competeResults.flat().filter(Boolean)
const allClaims = allSources.flatMap(s => (s.claims || []).map(c => ({ ...c, team: s.team })))

const impRank = { central: 0, supporting: 1, tangential: 2 }
const qualRank = { primary: 0, secondary: 1, blog: 2, forum: 3, unreliable: 4 }
// v6.8 P1-5: E4 artifact 缺失降权 — ENFORCE_ARTIFACT 时无 artifact 的 claim 排最后, Verify 预算优先给有 artifact 的(缺 artifact 在 Compete 不拦, 但不再占验证配额)
const artifactRank = c => (ENFORCE_ARTIFACT && !c.artifact) ? 1 : 0
const rankedClaims = [...allClaims]
  .sort((a, b) => (artifactRank(a) - artifactRank(b)) || (impRank[a.importance] - impRank[b.importance]) || (qualRank[a.sourceQuality] - qualRank[b.sourceQuality]))
  .slice(0, MAX_VERIFY_CLAIMS)

log("Fetch " + allSources.length + " sources → " + allClaims.length + " claims → 验证 top " + rankedClaims.length)

if (rankedClaims.length === 0) {
  return {
    task: TASK, taskType: manifest.taskType, mainFlag: manifest.mainFlag,
    constitution,
    summary: "无 claims 可验证。抓取 " + allSources.length + " 来源，全部为空/失败。" + dupes.length + " URL 去重, " + budgetDropped.length + " 预算裁掉。",
    findings: [], refuted: [], unverified: [], sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality })),
    stats: { teams: teamDefs.length, sources: allSources.length, claims: 0, dupes: dupes.length, constitutionCalls },
  }
}

// ─── Phase 3: Verify — N 票对抗验证(含宪法法院票) ───
// v6.8 P0-4: Verify 配额熔断 — 动态计算可验证 claims 数, 预留 synthesis(synthesis+patchloop)预算
const reserveSynthesis = (CONFIG.patchLoop !== false ? 1 + TEAM_IDS.length * MAX_PATCH_ROUNDS * (1 + 3) : 1)
const votableCount = Math.max(1, Math.min(rankedClaims.length, Math.floor((TOTAL_AGENT_BUDGET - agentsUsed - reserveSynthesis) / VOTES_PER_CLAIM)))
const votableClaims = rankedClaims.slice(0, votableCount)
log("Verify 预算: 已用 " + agentsUsed + "/" + TOTAL_AGENT_BUDGET + " agents, 预留 synthesis " + reserveSynthesis + " → 可验证 " + votableCount + "/" + rankedClaims.length + " claims")
phase("Verify")
const voted = (await parallel(
  votableClaims.map(claim => () =>
    parallel(
      Array.from({ length: VOTES_PER_CLAIM }, (_, v) => () =>
        retryAgent(VERIFY_PROMPT(claim, v, constitutionBlock), {
          label: "v" + v + ":" + quotedLabel(claim.claim),
          phase: "Verify",
          schema: VERDICT_SCHEMA,
          effort: "medium", // v6.8 P0-1: low→medium 提升对抗深度(Round 5 40评委0淘汰部分源于 effort=low)
        })
      )
    ).then(verdicts => {
      const valid = verdicts.filter(Boolean)
      // v6.1 S5: 违宪票计入refuted | v6.7 P1: REJECTED 轨票也计入(三轨裁决)
      const refuted = valid.filter(v => v.refuted || v.unconstitutional || v.track === "REJECTED").length
      const unconstitutional = valid.filter(v => v.unconstitutional).length
      // v6.4 S5c.1: quorum 守卫(≥ceil(VOTES/2) 票 unconstitutional 才触发 hard veto,防 1 票独裁)
      const quorumUnconstitutional = Math.ceil(VOTES_PER_CLAIM / 2)
      const hasUnconstitutional = unconstitutional >= quorumUnconstitutional
      const errored = VOTES_PER_CLAIM - valid.length
      const erroredOverflow = errored > VOTES_PER_CLAIM / 2
      // v6.7 P1: 三轨统计(track 缺失时按 refuted 回退, 兼容异常输出)
      const trackVotes = { DEPLOYABLE: 0, PROBE: 0, REJECTED: 0 }
      for (const v of valid) {
        const t = v.track || (v.refuted || v.unconstitutional ? "REJECTED" : "PROBE")
        if (trackVotes[t] !== undefined) trackVotes[t]++
      }
      const isRefuted = hasUnconstitutional || refuted >= REFUTATIONS_REQUIRED
      // v6.7 S5c.4 修订: erroredOverflow 归 unverified(基础设施失败), 不再算作反驳 — 与 summary 的基础设施故障分支对齐
      const isUnverifiable = !isRefuted && erroredOverflow
      // v6.7 P1: DEPLOYABLE 须严格多数(>valid/2) — 修复 Round5 '诚实护城河'(标注'理论值'即自动幸存, 40票仅4反驳, 8/8全幸存)
      const isDeployable = !isRefuted && !isUnverifiable && trackVotes.DEPLOYABLE > valid.length / 2
      const isProbe = !isRefuted && !isUnverifiable && !isDeployable
      const survives = isDeployable
      const mark = isDeployable ? "✓" : isRefuted ? "✗" : isUnverifiable ? "?" : "◐"
      log(quotedLabel(claim.claim).slice(0, 30) + ": D" + trackVotes.DEPLOYABLE + "/P" + trackVotes.PROBE + "/R" + trackVotes.REJECTED + (unconstitutional > 0 ? " [违宪票x" + unconstitutional + "]" : "") + (errored > 0 ? " (" + errored + " errored)" : "") + " " + mark)
      return { ...claim, verdicts: valid, refutedVotes: refuted, unconstitutionalVotes: unconstitutional, erroredVotes: errored, trackVotes, survives, isDeployable, isProbe, isRefuted }
    })
  )
)).filter(Boolean)

const confirmed = voted.filter(c => c.isDeployable)
const killed = voted.filter(c => c.isRefuted)
const probes = voted.filter(c => c.isProbe)
const unverified = voted.filter(c => !c.isDeployable && !c.isRefuted && !c.isProbe)
log("Verify: " + voted.length + " claims → " + confirmed.length + " 可部署, " + probes.length + " 探针(博弈内不可验证), " + killed.length + " 被反驳(含违宪), " + unverified.length + " 无法判定")

// ─── Phase 4: Score — 按队伍聚合计分 ───
phase("Score")
const impW = { central: 3, supporting: 2, tangential: 1 }
const confW = { high: 1, medium: 0.6, low: 0.3 }
const bestConfidence = c => {
  const best = bestVerdict(c)
  return best ? best.confidence : "low"
}

const teamScores = teamDefs.map(team => {
  const surv = confirmed.filter(c => c.team.id === team.id)
  const rej = killed.filter(c => c.team.id === team.id)
  const prob = probes.filter(c => c.team.id === team.id) // v6.7: PROBE 不计分不扣分(诚实标注不再换免费幸存, 也不惩罚诚实)
  let score = 0
  for (const c of surv) {
    // v6.4 M2-cmp 修复: F0 兜底不再刷分(无效/未分类子问题不计分,防"专攻模糊边缘 claim 刷分"通道)
    if (!c.subProblemId || c.subProblemId === "F0" || !problemPoints[c.subProblemId]) continue
    const pts = problemPoints[c.subProblemId]
    score += pts * (impW[c.importance] ?? 1) * (confW[bestConfidence(c)] ?? 0.3)
  }
  for (const c of rej) {
    if (!c.subProblemId || c.subProblemId === "F0" || !problemPoints[c.subProblemId]) continue
    const pts = problemPoints[c.subProblemId]
    score -= pts * 0.5
  }
  const capturedFlags = new Set(surv.map(c => c.subProblemId).filter(id => id && id !== "F0")).size
  return {
    team: team.id, name: team.name, strategy: team.strategy, score: Math.round(score * 10) / 10,
    capturedFlags, survived: surv.length, refuted: rej.length, probed: prob.length,
  }
}).sort((a, b) => b.score - a.score)

const leaderboard = teamScores.map((t, i) => ({ rank: i + 1, ...t }))
log("排行榜: " + leaderboard.map(t => t.rank + "." + t.name + " " + t.score).join(" | "))

// ─── 综合结论 ───
const winner = leaderboard[0]
// v6.1 M2 修复: 合成跨队融合(不再垄断领先队, 与机制7"跨队融合"对齐) — 标注队伍归属
const winnerClaims = [...confirmed]
  .sort((a, b) => (problemPoints[b.subProblemId] ?? 0) - (problemPoints[a.subProblemId] ?? 0) || (a.team.name || "").localeCompare(b.team.name || ""))

const toRefuted = c => ({ claim: c.claim, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, unconstitutionalVotes: c.unconstitutionalVotes || 0, source: c.sourceUrl, team: c.team.name })
const toUnverified = c => ({ claim: c.claim, erroredVotes: c.erroredVotes, validVotes: c.verdicts.length, source: c.sourceUrl })
const baseStats = () => ({
  teams: teamDefs.length,
  sourcesFetched: allSources.length,
  claimsExtracted: allClaims.length,
  claimsVerified: voted.length,
  confirmed: confirmed.length,
  probed: probes.length,
  killed: killed.length,
  unverified: unverified.length,
  // v6.4 N2 修复: 违宪击杀指标用 > 0(原 v6.1 S8 用 >= REFUTE 漏统 1-2 票 unconstitutional kills)
  unconstitutionalKills: killed.filter(c => (c.unconstitutionalVotes || 0) > 0).length,
  urlDupes: dupes.length,
  budgetDropped: budgetDropped.length,
  constitutionCalls,
})

const toProbe = c => ({ claim: c.claim, trackVotes: c.trackVotes, source: c.sourceUrl, team: c.team.name, note: "博弈内证据未闭合 — 需博弈外验证(如线上数据/实验), 禁止当作已证实结论" })

if (confirmed.length === 0) {
  // 无任何可部署结论 —— 区分"全部待验证(PROBE)" / "全被反驳" / "验证器基础设施失败"
  let summary
  if (probes.length > 0) {
    summary = "无可部署结论 —— " + probes.length + " 条 claims 的核心证据在博弈内不可获得(归 PROBE 轨), " + killed.length + " 条被反驳。这不是失败而是诚实的边界: 下一步应按 PROBE 清单做博弈外验证(线上数据/实验), 禁止把探针当结论交付。"
  } else if (killed.length === 0 && unverified.length > 0) {
    summary = "无法验证任何 claim —— 全部 " + unverified.length + " 个评委面板失败(可能是限流/API错误)。这是基础设施故障,非研究结论。原始 claims 如下,建议重试或人工验证。"
  } else if (unverified.length > 0) {
    summary = killed.length + " 条 claims 被对抗验证反驳, " + unverified.length + " 条无法验证(评委失败)。无 claims 幸存,研究无定论。"
  } else {
    summary = "全部 " + killed.length + " 条 claims 被对抗验证反驳。研究无定论 —— 来源质量低或 claims 夸大。"
  }
  return {
    task: TASK, taskType: manifest.taskType, mainFlag: manifest.mainFlag,
    constitution,
    summary, findings: [],
    leaderboard,
    probes: probes.map(toProbe),
    refuted: killed.map(toRefuted), unverified: unverified.map(toUnverified),
    sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality, team: s.team.name, claimCount: s.claims.length })),
    stats: { ...baseStats(), confirmed: 0, agentCalls: constitutionCalls + 1 + teamDefs.length + allSources.length + (voted.length * VOTES_PER_CLAIM) },
  }
}

// ─── Phase 5: Synthesis — 综合结论合成 ───
phase("Synthesis")
const synthesis = await retryAgent(SYNTHESIS_PROMPT(manifest, winnerClaims, leaderboard, constitutionBlock, probes, killed), {
  label: "synthesis:" + winner.name, phase: "Synthesis", schema: SYNTHESIS_SCHEMA,
})

if (!synthesis) {
  // 合成失败 —— 保留验证后的幸存 claims 原始返回
  return {
    task: TASK, taskType: manifest.taskType, mainFlag: manifest.mainFlag,
    constitution,
    summary: "综合结论合成步骤失败 —— 返回 " + confirmed.length + " 条已验证幸存 claims(未合并)。",
    synthesisAnswer: null,
    findings: confirmed.map(c => ({ subProblemId: c.subProblemId, claim: c.claim, source: c.sourceUrl, quote: c.quote, vote: (c.verdicts.length - c.refutedVotes) + "-" + c.refutedVotes, team: c.team.name })),
    leaderboard,
    probes: probes.map(toProbe),
    refuted: killed.map(toRefuted), unverified: unverified.map(toUnverified),
    sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality, team: s.team.name, claimCount: s.claims.length })),
    stats: { ...baseStats(), afterSynthesis: 0, agentCalls: constitutionCalls + 1 + teamDefs.length + allSources.length + (voted.length * VOTES_PER_CLAIM) + 1 },
  }
}

// ─── Phase 6: PatchLoop — 多轮修补循环(v6.1 M6 实现, 兑现 SKILL.md 机制3/4/6) ───
let patchResult = null
if (CONFIG.patchLoop !== false) {
  phase("PatchLoop")
  const allPatches = []
  let patchRound = 0
  let prevPatches = []

  while (patchRound < MAX_PATCH_ROUNDS) {
    patchRound++
    log("PatchLoop 第 " + patchRound + " 轮...")

    const proposals = (await parallel(
      teamDefs.map(team => () =>
        retryAgent(PATCH_PROMPT(team, manifest, winnerClaims, prevPatches, patchRound), {
          label: "patch:" + team.name + ":R" + patchRound, phase: "PatchLoop", schema: PATCH_SCHEMA, effort: "medium",
        }).then(r => r ? { team, patches: r.patches || [] } : null)
      )
    )).filter(Boolean)
    const flatPatches = proposals.flatMap(p => (p.patches || []).map(patch => ({ ...patch, team: p.team.name })))
    // v6.4 NEW-2 修复: PatchLoop 轮内去重(同 flawId+title 不重复计数,4 队协调刷量通道关闭)
    const seenPatches = new Set()
    const dedupedPatches = flatPatches.filter(p => {
      const k = (p.flawId || "?") + "|" + (p.title || "?").slice(0, 100)
      if (seenPatches.has(k)) return false
      seenPatches.add(k)
      return true
    })
    if (dedupedPatches.length === 0) {
      log("第 " + patchRound + " 轮无 patch 提案 — 退出循环")
      break
    }
    log("第 " + patchRound + " 轮: " + proposals.map(p => p.team.name + "(" + p.patches.length + ")").join(", ") + " = " + dedupedPatches.length + " patches (去重前 " + flatPatches.length + ")")
    const flatPatchesToUse = dedupedPatches

    const verified = (await parallel(
      flatPatchesToUse.map(patch => () =>
        parallel(
          Array.from({ length: 3 }, (_, v) => () =>
            retryAgent(PATCH_VERIFY_PROMPT(patch, v, TASK, prevPatches), {
              label: "patchV:" + patch.flawId, phase: "PatchLoop", schema: PATCH_VERIFY_SCHEMA, effort: "low",
            })
          )
        ).then(verdicts => {
          const valid = verdicts.filter(Boolean)
          const approved = valid.filter(vd => vd.approved).length
          const survives = approved >= 2
          return { ...patch, verdicts: valid, approved, survives }
        })
      )
    )).filter(Boolean)

    const accepted = verified.filter(p => p.survives)
    const rejected = verified.filter(p => !p.survives)
    allPatches.push(...accepted)
    // v6.2 M6-ctx 修复: 累积所有已采纳的 patches(原代码只保留最后一轮,多轮修补时Round 3看不到Round 1已采纳)
    prevPatches = [...prevPatches, ...accepted]
    log("第 " + patchRound + " 轮: 采纳 " + accepted.length + " / 驳回 " + rejected.length + " (累计 " + allPatches.length + ")")
  }

  patchResult = {
    rounds: patchRound,
    maxRounds: MAX_PATCH_ROUNDS,
    totalAccepted: allPatches.length,
    acceptedPatches: allPatches.map(p => ({
      flawId: p.flawId, title: p.title, team: p.team, diff: p.diff,
      targetFile: p.targetFile, targetLines: p.targetLines, riskNote: p.riskNote,
      approveVotes: p.approved + "/3"
    })),
  }
  log("PatchLoop 完成: " + patchResult.rounds + " 轮, 采纳 " + patchResult.totalAccepted + " patches")
}

return {
  task: TASK,
  taskType: manifest.taskType,
  mainFlag: manifest.mainFlag,
  constitution,
  subProblems: manifest.subProblems,
  rules: manifest.rules,
  scoring: manifest.scoring,
  toolset: manifest.toolset,
  synthesisTeam: { name: winner.name, strategy: winner.strategy, score: winner.score, capturedFlags: winner.capturedFlags },
  ...synthesis,
  leaderboard,
  probes: probes.map(toProbe),
  refuted: killed.map(toRefuted),
  unverified: unverified.map(toUnverified),
  sources: allSources.map(s => ({ url: s.url, quality: s.sourceQuality, team: s.team.name, claimCount: s.claims.length })),
  patchResult, // v6.1 M6: 多轮修补结果(可能为 null 当 CONFIG.patchLoop === false)
  stats: {
    ...baseStats(),
    afterSynthesis: synthesis.findings.length,
    agentCalls: constitutionCalls + 1 + teamDefs.length + allSources.length + (voted.length * VOTES_PER_CLAIM) + 1 + (patchResult ? patchResult.totalAccepted * 3 + teamDefs.length * patchResult.rounds : 0),
  },
}
