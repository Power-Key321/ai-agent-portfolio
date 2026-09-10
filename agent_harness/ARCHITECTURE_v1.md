# Agent Harness 乐高架构 — 模块IO协议 v2

> **v2 核心升级**：从线性管道升级为螺旋收敛模型。约束逐层逼近用户真实意图，收敛速度作为框架自优化的第一性指标。

## 0. 总览：双层架构 + 螺旋收敛

```
┌──────────────────────────────────────────────────────┐
│                 Loop 层 (控制面 / 上位循环)             │
│  跨轮次管理目标逼近，可调用多个技能/agent               │
│  决定"是否继续螺旋"、"是否切换策略"                    │
│                                                      │
│  ┌────────────────────────────────────────────┐     │
│  │         螺旋收敛环 (Spiral Refiner)          │     │
│  │                                             │     │
│  │  第N轮: 当前理解 → 装配执行 → 差距评估        │     │
│  │     ↓  收敛半径 r > ε ?                     │     │
│  │  第N+1轮: 精炼理解 → 重新装配 → 再评估        │     │
│  │     ↓                                       │     │
│  │  r < ε → 交付                               │     │
│  │                                             │     │
│  │  收敛指标: c = 解空间缩小率 / 所需轮次         │     │
│  └────────────────────────────────────────────┘     │
│                         │                            │
│            ┌────────────▼────────────┐               │
│            │  Envelope 层 (数据面)     │               │
│            │  轮次内模块间数据载体      │               │
│            └────────────┬────────────┘               │
└─────────────────────────┼────────────────────────────┘
                          │
    ┌─────────────────────▼────────────────────────────┐
    │              六模块乐高池 (自组装)                  │
    │                                                   │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
    │  │ 预处理    │  │  拆解    │  │  执行    │        │
    │  │ Preproc  │  │ Decomp   │  │ Execute  │        │
    │  └──────────┘  └──────────┘  └──────────┘        │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
    │  │  上下文   │  │  调度    │  │  交付    │        │
    │  │ Context  │  │ Schedule │  │ Deliver  │        │
    │  └──────────┘  └──────────┘  └──────────┘        │
    └───────────────────────────────────────────────────┘
                          │
    ┌─────────────────────▼────────────────────────────┐
    │     反馈闭环 (Feedback Loop) + 动态阈值引擎        │
    │  用户行为 → 信号 → 权重更新 → 阈值自适应           │
    └───────────────────────────────────────────────────┘
```

**关键关系：Loop 与 Envelope 是分层的，不冲突。**
- Loop = 控制面：外层循环，管理跨轮次的目标逼近，可调用多个技能/agent
- Envelope = 数据面：单轮次内 6 模块间的数据载体
- Loop 可以发起多轮 Envelope 管道，每轮结果反馈给 Loop 决定是否继续螺旋

---

## 1. 通用消息信封 (Standard Envelope)

所有模块间通信使用统一信封。模块内部 payload 各异，但信封结构不变。

```jsonc
// Envelope v2 — 新增螺旋收敛字段
{
  "envelope": {
    "version": "2.0",
    "trace_id": "uuid",              // 全链路追踪ID，贯穿整个任务(跨轮次不变)
    "span_id": "uuid",               // 当前模块调用ID
    "parent_span_id": "uuid|null",   // 上游模块span_id
    "intent_class": "string",        // 意图分类(每轮可精炼)
    "strategy_id": "string",         // 当前装配策略ID(每轮可切换)
    "timestamp_created": "iso8601",
    "module_from": "string",         // 发送方模块名
    "module_to": "string",           // 接收方模块名
    "sequence_index": 0,             // 模块在当前装配链中的位置(0-based)

    // === v2新增: 螺旋收敛字段 ===
    "spiral_iteration": 0,           // 当前螺旋轮次(0起始)
    "spiral_max_iterations": 5,      // 最大螺旋轮次(防止无限循环)
    "convergence_radius": 1.0,       // 收敛半径 1.0(初始/发散) → 0.0(精确命中用户意图)
    "convergence_target": 0.05       // 收敛阈值 ε，r < ε 时交付
  },

  // === 三个核心载荷区 ===

  "task": {
    "original_input": "string",        // 用户原始输入(不变)
    "normalized_intent": "string",     // 当前轮次标准化后的意图(每轮可精炼)
    "intent_history": [],              // v2新增: 历轮意图演变链，用于收敛度量
    "entities": {},                    // 抽取的实体(每轮可丰富)
    "constraints": {},                 // 显式+推断约束(每轮可增加)
    "constraints_added_this_round": [],// v2新增: 本轮新增约束，用于收敛度量
    "complexity_score": 0.0,           // 0-1
    "current_state": "string"          // 状态机节点
  },

  "context": {
    // v2: 混合方案 — 轻量指针 + LazyCache
    "refs": ["memory://user_role", "memory://project/...", "file://src/auth/"],
    "cache": {},                       // LazyCache: 首次resolve()加载，后续命中缓存
    "window_budget_total": 200000,
    "window_budget_allocated": {},
    "window_used_so_far": 0,
    "priority": "normal|high|low"
  },

  "feedback": {
    "accepted": null,
    "modified": null,
    "retry_triggered": false,
    "retry_count": 0,
    "failure_class": null,
    "self_heal_applied": null,

    // v2新增: 收敛度量字段
    "convergence_score": null,         // 本轮收敛评分 c = 解空间缩小率 / 轮次
    "steps_to_converge": null          // 达到收敛所需轮次(任务完成后回填)
  }
}
```

**Envelope 设计原则（v2 更新）：**
- Envelope 始终轻量：`context.refs` 只传指针，实际数据通过 `context.cache` 按需懒加载
- 任何模块可以直接 `envelope.context.cache.resolve("memory://user_role")` 获取数据
- 同一轮次内多次 resolve 同一指针 → 命中缓存，不重复检索
- 跨轮次时 cache 清空，但 `refs` 保留（新一轮重新检索）

---

## 2. 各模块 IO 协议

### 2.1 预处理模块 (Preprocessor)

职责：清洗原始输入，提取实体，检测歧义，估算复杂度。

```
INPUT:  Envelope (module_to: "preproc")
        Envelope.task.original_input 已填充
        Envelope.context 已填充(refs指向对话历史、用户记忆)

OUTPUT: Envelope (module_from: "preproc")
        + task.normalized_intent  填充
        + task.entities           填充
        + task.complexity_score   填充
        + task.constraints        填充(从输入推断)
```

```jsonc
// Preprocessor.output.task 增量
{
  "normalized_intent": "实现REST API的用户认证中间件",
  "entities": {
    "language": "python",
    "framework": "fastapi",
    "auth_method": "jwt",
    "scope": ["middleware", "token_validation"]
  },
  "complexity_score": 0.45,          // 中等复杂度
  "constraints": {
    "existing_codebase": true,       // 需读取现有代码
    "test_required": null,           // 未明确
    "deadline_implied": null
  },
  "ambiguity_flags": [               // 歧义标记 → 后续模块可据此要求澄清
    "auth_method_jwt_implied_not_explicit"
  ]
}
```

**模块变体（同一接口，不同实现）：**
- `preproc.simple` — 直接透传，用于简单查询
- `preproc.full` — 完整实体抽取+歧义检测
- `preproc.code` — 代码任务专用，提取文件路径/函数名/依赖

---

### 2.2 拆解模块 (Decomposer)

职责：将标准化意图拆解为有依赖关系的子任务DAG。

```
INPUT:  Envelope (module_to: "decomp")
        task.normalized_intent + entities + complexity_score 已填充

OUTPUT: Envelope (module_from: "decomp")
        + task.subtasks[]          填充
        + task.dag_edges[]         填充
```

```jsonc
// Decomposer.output.task 增量
{
  "subtasks": [
    {
      "id": "s1",
      "description": "读取现有项目结构和认证相关代码",
      "type": "explore",
      "estimated_tokens": 5000,
      "dependencies": []
    },
    {
      "id": "s2",
      "description": "设计中间件接口和token验证流程",
      "type": "design",
      "estimated_tokens": 8000,
      "dependencies": ["s1"]
    },
    {
      "id": "s3",
      "description": "实现JWT验证中间件",
      "type": "code_gen",
      "estimated_tokens": 15000,
      "dependencies": ["s2"]
    },
    {
      "id": "s4",
      "description": "编写中间件单元测试",
      "type": "code_gen",
      "estimated_tokens": 10000,
      "dependencies": ["s3"]
    },
    {
      "id": "s5",
      "description": "验证现有端点集成中间件后行为正确",
      "type": "verify",
      "estimated_tokens": 8000,
      "dependencies": ["s4"]
    }
  ],
  "dag_edges": [
    {"from": "s1", "to": "s2"},
    {"from": "s2", "to": "s3"},
    {"from": "s3", "to": "s4"},
    {"from": "s4", "to": "s5"}
  ],
  "decomp_strategy": "linear_dependency_chain"  // 本次使用的拆解策略
}
```

**模块变体：**
- `decomp.linear` — 简单线性拆解
- `decomp.dag` — 完整DAG拆解（含并行分支）
- `decomp.single` — 不拆解，单步任务

---

### 2.3 调度模块 (Scheduler)

职责：接收DAG，考虑资源和优先级，产出执行计划。

```
INPUT:  Envelope (module_to: "scheduler")
        task.subtasks[] + dag_edges[] 已填充

OUTPUT: Envelope (module_from: "scheduler")
        + task.execution_plan      填充
```

```jsonc
// Scheduler.output.task 增量
{
  "execution_plan": {
    "strategy": "sequential",         // sequential | parallel_window | dependency_driven
    "batches": [
      {
        "batch_id": "b1",
        "subtask_ids": ["s1"],
        "parallel": false,
        "allocated_tokens": 5000,
        "timeout_ms": 30000
      },
      {
        "batch_id": "b2",
        "subtask_ids": ["s2"],
        "parallel": false,
        "allocated_tokens": 8000,
        "timeout_ms": 30000
      },
      {
        "batch_id": "b3",
        "subtask_ids": ["s3", "s4"],  // 可以并行(s4依赖s3但可流水线)
        "parallel": true,
        "allocated_tokens": 25000,
        "timeout_ms": 60000
      },
      {
        "batch_id": "b4",
        "subtask_ids": ["s5"],
        "parallel": false,
        "allocated_tokens": 8000,
        "timeout_ms": 60000
      }
    ],
    "estimated_total_tokens": 46000,
    "estimated_total_time_ms": 180000
  }
}
```

**模块变体：**
- `schedule.sequential` — 严格顺序
- `schedule.parallel_eager` — 最大化并行
- `schedule.context_aware` — 根据上下文窗口余量动态决定并行度

---

### 2.4 上下文模块 (Context) — v2 混合方案

职责：按查询检索上下文，通过 LazyCache 实现"指针传递 + 按需加载 + 缓存复用"。

**混合方案核心机制：**
```
Envelope.context.refs = ["memory://user_role", "file://src/auth/"]
                        ↑ 只传指针，Envelope 保持轻量（几十字节）

Envelope.context.cache = LazyCache()
                        ↑ 缓存层

模块内使用时：
  data = envelope.context.cache.resolve("memory://user_role")
  # 首次调用 → Context模块检索 → 写入cache → 返回
  # 后续调用(同轮次) → 直接从cache返回，不重复检索
  # 跨轮次 → cache清空，refs保留，下一轮重新加载
```

```
INPUT:  Envelope (module_to: "context")
        task.entities + subtask(当前正在执行的) 已填充
        context.refs[] 已填充(需解析的指针列表)
        context.window_budget_total 已填充

OUTPUT: Envelope (module_from: "context")
        + context.cache 已预热(指针→数据映射)
        + context.window_used_so_far 更新
```

```jsonc
// Context.output — cache结构
{
  "cache": {
    "memory://user_role": {
      "source": "memory://user_role",
      "relevance_score": 0.92,
      "content_hash": "sha256...",
      "token_count": 150,
      "content": "用户是资深Python后端开发者，偏好FastAPI...",
      "loaded_at": "spiral_iteration_1"
    },
    "memory://project/auth_decision_record": {
      "source": "memory://project/auth_decision_record",
      "relevance_score": 0.87,
      "content_hash": "sha256...",
      "token_count": 340,
      "content": "之前决定使用JWT而非session，因为..."
    },
    "file://src/auth/": {
      "source": "file://src/auth/",
      "relevance_score": 0.95,
      "content_hash": "sha256...",
      "token_count": 2300,
      "content": "现有auth模块代码..."
    }
  },
  "retrieval_strategy": "relevance_ranked_topk",
  "cache_policy": "lazy_load_per_iteration",  // 每轮懒加载，跨轮清空
  "window_used_so_far": 2790,
  "window_remaining": 197210
}
```

**方案对比（已在讨论中确认）：**

| | 纯指针方案 | 纯数据方案 | **混合方案（v2采用）** |
|---|---|---|---|
| Envelope重量 | 轻(几十字节) | 重(可能上万token) | 轻(指针)+按需膨胀 |
| 模块自主性 | 低，必须回调Context | 高，直接读数据 | 高，首次触发加载，后续命中缓存 |
| 上下文一致性 | 好，单一数据源 | 差，多副本可能不一致 | 好，缓存层保证一致性 |
| 调试难度 | 中(需追踪指针解析) | 低(数据在Envelope里直接看) | 低(缓存层可dump) |

**模块变体：**
- `context.minimal` — 只取用户记忆，适合简单任务
- `context.full` — 全量检索(记忆+代码+文档)
- `context.incremental` — 在已有上下文基础上增量补充(螺旋每轮追加新约束相关上下文)

---

### 2.5 执行模块 (Executor)

职责：实际调用模型/工具，执行单个子任务，产出结果+错误分类。

```
INPUT:  Envelope (module_to: "executor")
        task.subtasks[当前] 填充
        context.retrieved[] 填充

OUTPUT: Envelope (module_from: "executor")
        + task.execution_result   填充
        + feedback.failure_class  填充(若失败)
```

```jsonc
// Executor.output.task 增量
{
  "execution_result": {
    "subtask_id": "s3",
    "status": "success",              // success | partial | failed | cancelled
    "output_type": "code_diff",       // code_diff | text | artifact_ref | error
    "artifacts": [
      {
        "type": "file_edit",
        "path": "src/auth/middleware.py",
        "diff_hash": "sha256...",
        "token_count": 2800
      }
    ],
    "tool_calls_made": 4,             // 本次执行调用的工具次数
    "actual_tokens_used": 14200,       // 实际消耗
    "duration_ms": 24500
  },
  // 如果status != success:
  "failure": null                     // 见下方失败分类
}
```

**失败分类 (feedback.failure_class)：**
```jsonc
// 失败类型 — 来自smart-loop v6.1实践验证的三类分法
{
  "failure_class": "none",            // none | ambiguous_intent | tool_error | model_hallucination
                                        // | context_overflow | timeout | dependency_fail

  // 自愈策略 (由调度引擎读取并执行)
  "self_heal_strategy": null          // null | retry_same | retry_refined | escalate_to_user
                                      // | re_decompose | expand_context | switch_model
}
```

**失败类型 → 自愈策略映射表（来自你的实践）：**
| failure_class | self_heal_strategy | 说明 |
|---|---|---|
| `ambiguous_intent` | `retry_refined` | 精炼术语后重试，委托loop管理迭代 |
| `tool_error` | `retry_same` (最多3次) | 工具瞬时失败，直接重试 |
| `context_overflow` | `expand_context` or `re_decompose` | 压缩/摘要旧上下文 或 拆成更小子任务 |
| `model_hallucination` | `re_decompose` + `retry_refined` | 不存在的API/文件，重新拆解 |
| `timeout` | `re_decompose` | 拆成更小子任务 |
| `dependency_fail` | `escalate_to_user` | 上游失败，无法自愈 |

---

### 2.6 交付模块 (Deliverer)

职责：汇总所有子任务结果，按格式组装最终交付物。

```
INPUT:  Envelope (module_to: "deliverer")
        task.execution_results[]  全部子任务结果收集完毕

OUTPUT: Envelope (module_from: "deliverer")
        + task.final_deliverable   填充
```

```jsonc
// Deliverer.output.task 增量
{
  "final_deliverable": {
    "format": "diff_patch",             // diff_patch | report | artifact_list | text_response
    "summary": "实现了JWT认证中间件，修改3个文件，新增2个测试",
    "artifacts": [
      {"path": "src/auth/middleware.py", "change": "new_file", "diff_hash": "..."},
      {"path": "src/auth/__init__.py", "change": "modified", "diff_hash": "..."},
      {"path": "tests/test_auth_middleware.py", "change": "new_file", "diff_hash": "..."}
    ],
    "quality_self_assessment": {
      "completeness": 1.0,              // 所有子任务完成
      "test_coverage": "added",
      "known_gaps": []
    }
  }
}
```

**模块变体：**
- `deliver.diff` — 代码变更以diff形式输出
- `deliver.report` — 分析报告格式
- `deliver.composite` — 混合格式(代码+文档+数据)

---

## 3. 路由层：螺旋精炼器 (Spiral Refiner)

v2 核心升级：路由不再是**一次判定**，而是**螺旋收敛**。每轮精炼意图、增加约束、缩小解空间，直到收敛半径低于阈值。

### 3.1 螺旋收敛模型

```
用户输入: "帮我做个登录"
    │
    ▼
第0轮 (r=1.00): intent_class="code_feature", entities={scope:"登录"}
    │  解空间: 前端登录/后端登录/全栈/OAuth/JWT/Session/...
    │  装配: preproc.code → decomp.single → execute → (试探性输出)
    │  用户反馈: "后端JWT"
    │  新增约束: {layer:"backend", auth:"jwt"}
    │  r = 0.60 (解空间缩小40%)
    ▼
第1轮 (r=0.60): intent_class="code_feature", entities={..., layer:"backend", auth:"jwt"}
    │  解空间: FastAPI JWT / Express JWT / Go JWT / ...
    │  装配: preproc.code → decomp.linear → context.full → execute → deliver.diff
    │  用户反馈: "FastAPI，需要refresh token"
    │  新增约束: {framework:"fastapi", feature:"refresh_token"}
    │  r = 0.25 (解空间再缩小58%)
    ▼
第2轮 (r=0.25): entities={..., framework:"fastapi", feature:"refresh_token"}
    │  解空间: 具体文件结构 / 中间件设计 / token刷新策略
    │  装配: preproc.code → decomp.dag → schedule.sequential → context.full → execute → deliver.diff
    │  用户反馈: 接受 ✓
    │  r = 0.03 < ε=0.05 → 交付
    ▼
收敛完成，总轮次=3，c = 0.97/3 = 0.323
```

### 3.2 策略表（冷启动版本 — 规则驱动）

```jsonc
{
  "strategies": {
    "code_feature": {
      "intent_patterns": ["实现*", "添加*功能", "开发*", "写一个*", "create*", "add*feature*"],
      "assembly": ["preproc.code", "decomp.dag", "schedule.context_aware", "context.full", "execute", "deliver.diff"],
      "max_parallel_subtasks": 3,
      "default_model": "opus",
      "retry_policy": "standard",
      "spiral_config": {
        "max_iterations": 5,
        "convergence_threshold": 0.05,
        "refinement_strategy": "add_constraints"  // add_constraints | narrow_scope | split_task
      }
    },
    "code_fix": {
      "intent_patterns": ["修复*", "fix*", "bug*", "报错*", "error*"],
      "assembly": ["preproc.code", "decomp.single", "schedule.sequential", "context.full", "execute", "deliver.diff"],
      "max_parallel_subtasks": 1,
      "default_model": "sonnet",
      "retry_policy": "aggressive",
      "spiral_config": {
        "max_iterations": 3,            // bug修复应更快收敛
        "convergence_threshold": 0.08,
        "refinement_strategy": "narrow_scope"
      }
    },
    "data_analysis": {
      "intent_patterns": ["分析*", "数据*", "统计*", "可视化*", "analy*", "report*"],
      "assembly": ["preproc.full", "decomp.dag", "schedule.parallel_eager", "context.minimal", "execute", "deliver.report"],
      "max_parallel_subtasks": 5,
      "default_model": "opus",
      "retry_policy": "standard",
      "spiral_config": {
        "max_iterations": 4,
        "convergence_threshold": 0.05,
        "refinement_strategy": "add_constraints"
      }
    },
    "research": {
      "intent_patterns": ["调研*", "搜索*", "查找*", "research*", "search*", "find*"],
      "assembly": ["preproc.full", "decomp.dag", "schedule.parallel_eager", "context.minimal", "execute", "deliver.report"],
      "max_parallel_subtasks": 8,
      "default_model": "haiku",
      "retry_policy": "conservative",
      "spiral_config": {
        "max_iterations": 3,
        "convergence_threshold": 0.10,  // 搜索任务阈值稍宽
        "refinement_strategy": "narrow_scope"
      }
    },
    "simple_query": {
      "intent_patterns": ["什么是*", "怎么*", "解释*", "what is*", "how to*"],
      "assembly": ["preproc.simple", "decomp.single", "schedule.sequential", "context.minimal", "execute", "deliver.report"],
      "max_parallel_subtasks": 1,
      "default_model": "haiku",
      "retry_policy": "conservative",
      "spiral_config": {
        "max_iterations": 1,            // 简单查询不需要螺旋
        "convergence_threshold": 0.20,
        "refinement_strategy": null
      }
    },
    "refactor": {
      "intent_patterns": ["重构*", "refactor*", "整理*", "优化结构*"],
      "assembly": ["preproc.code", "decomp.dag", "schedule.context_aware", "context.full", "execute", "deliver.diff"],
      "max_parallel_subtasks": 2,
      "default_model": "opus",
      "retry_policy": "standard",
      "spiral_config": {
        "max_iterations": 4,
        "convergence_threshold": 0.05,
        "refinement_strategy": "add_constraints"
      }
    }
  }
}
```

### 3.3 收敛半径计算

```
r = f(本轮新增约束数, 解空间剩余歧义度, 用户反馈确定性)

简化计算公式（冷启动版本）：
  r = r_prev × (1 - α × constraints_added_this_round / max_possible_constraints)
        × (1 - β × user_feedback_clarity)

其中:
  r_prev        = 上一轮收敛半径
  α             = 约束权重系数(默认0.4)
  β             = 反馈清晰度系数(默认0.3)
  user_feedback_clarity = 0(无反馈) / 0.5(隐式反馈) / 1.0(显式确认)

收敛速度 c = (r_initial - r_final) / spiral_iterations
           = (1.0 - r_final) / N

目标: c 越大越好 → 少轮次达到高收敛 → 框架自优化的核心指标
```

---

## 4. 反馈闭环 (Feedback Loop) — v2 动态阈值

### 4.1 信号 → 权重更新

```
用户行为               信号提取              权重更新
────────              ────────              ────────
接受结果    ──────►   accepted=1     ──►   当前策略权重 +δ
修改结果    ──────►   modified=1     ──►   当前策略权重 -δ/2
重新来      ──────►   retry=1        ──►   当前策略权重 -δ
                                            竞争策略权重 +δ/2 (explore)
静默不用    ──────►   ignored=1      ──►   当前策略权重 -2δ (强负信号)
```

```jsonc
// 反馈信号结构 (v2 增加螺旋相关字段)
{
  "feedback_event": {
    "trace_id": "uuid",
    "strategy_id": "code_feature",
    "signal_type": "accepted",         // accepted | modified | retried | ignored
    "signal_strength": 1.0,
    "spiral_iterations_used": 3,       // v2: 本次任务螺旋轮次
    "convergence_score": 0.323,        // v2: 收敛速度 c
    "context_note": null,
    "timestamp": "iso8601"
  }
}

// 权重更新规则
{
  "weight_update": {
    "strategy_id": "code_feature",
    "delta": 0.05,
    "new_weight": 0.78,
    "explore_triggered": false,
    "last_updated": "iso8601"
  }
}
```

### 4.2 动态阈值引擎（替代固定Phase切换）

**核心理念：阈值本身也是被优化的参数。** 系统根据用户行为的稳定性自动调整何时进入下一Phase。

```jsonc
// 动态阈值状态
{
  "dynamic_thresholds": {
    "θ_phase1_to_2": 0.15,             // 策略权重标准差阈值 → 触发从纯规则切换到开始学习
    "θ_phase2_to_3": 0.65,             // 最佳策略权重阈值 → 触发explore机制
    "learning_rate": 0.05,             // 权重更新步长(本身也可动态调整)

    // 自适应规则
    "adaptation_rules": {
      "user_frequent_manual_switch": {
        "condition": "用户在最近20次任务中手动切换策略 >= 5次",
        "action": "降低 θ_phase1_to_2 和 θ_phase2_to_3 各 20%",
        "reason": "系统不够自信，应更早开始学习和探索"
      },
      "user_consistent_accept": {
        "condition": "最近30次任务接受率 > 90%",
        "action": "提高 θ_phase2_to_3 10%",
        "reason": "系统已稳定，减少不必要的探索"
      },
      "strategy_weight_stagnant": {
        "condition": "某策略权重连续50次任务变化 < 0.01",
        "action": "临时降低 θ_phase2_to_3 至当前值×0.5，触发一轮explore",
        "reason": "可能陷入局部最优"
      },
      "high_convergence_consistently": {
        "condition": "最近20次任务平均收敛速度 c > 0.3",
        "action": "将当前策略标记为 verified，减少explore概率",
        "reason": "当前策略已验证有效，减少探索成本"
      },
      "low_convergence_spike": {
        "condition": "连续3次任务 c < 0.1",
        "action": "强制触发explore，尝试竞争策略",
        "reason": "当前策略可能失效，需要探索替代方案"
      }
    }
  }
}
```

**Phase 过渡条件（动态版）：**
```
Phase 1 → Phase 2:
  触发条件: σ(策略权重) > θ_phase1_to_2  (各策略权重开始有区分度)
  而非: 固定50次任务

Phase 2 → Phase 3:
  触发条件: max(策略权重) > θ_phase2_to_3  (某策略已足够可信)
  而非: 固定200次任务

每个Phase的阈值会根据adaptation_rules持续自动调整。
```

### 4.3 收敛速度反馈闭环

```
任务完成 → 计算 c = (1.0 - r_final) / spiral_iterations
         → 更新策略的 moving_avg_c
         → 如果 c 持续下降 → 触发策略重评估
         → 如果 c 持续上升 → 增强当前策略权重
```

---

## 5. 与外部CLI的对接接口 (Adapter Protocol)

这是回答你"能否对接到市面CLI"的关键部分。

```
┌──────────────────────────────────┐
│          Agent Harness            │
│  (独立Runtime，自己跑Agent Loop)   │
└──────────────┬───────────────────┘
               │ Adapter Protocol (标准接口)
       ┌───────┼───────┬───────────────┐
       ▼       ▼       ▼               ▼
   Claude    Codex   Cursor         其他
   Code      CLI     (VS Code)      CLI
```

```jsonc
// Adapter 接口定义 — 每个CLI只需实现这个接口
{
  "adapter_spec": {
    "name": "claude_code",
    "version": "1.0",

    // 1. 入口：CLI如何触发Harness
    "entry": {
      "type": "skill_or_slash_command",     // skill_or_slash_command | mcp_tool | custom_hook | stdin_pipe
      "trigger": "/harness",                // 用户在CLI中输入的命令
      "description": "启动Agent Harness处理当前任务"
    },

    // 2. 输入注入：Harness如何获取用户输入和上下文
    "input_bridge": {
      "user_message": "from_cli_stdin",     // 用户原始输入
      "conversation_history": "from_cli_api", // 对话历史(若CLI提供)
      "file_context": "from_workspace",     // 当前工作区文件
      "memory": "from_harness_own_store"    // Harness自带记忆系统
    },

    // 3. 执行：Harness如何调用模型和工具
    "execution_bridge": {
      "model_call": "via_cli_sdk",          // 通过CLI的SDK调用模型(保持统一计费/限流)
      "tool_call": "via_cli_tools",         // 使用CLI提供的工具集
      "sandbox": "via_cli_sandbox"          // 使用CLI的沙箱执行
    },

    // 4. 输出渲染：Harness结果如何呈现给用户
    "output_bridge": {
      "stream": "to_cli_stdout",            // 流式输出到CLI
      "diff_render": "to_cli_diff_view",    // 代码diff渲染
      "artifact_save": "to_workspace"       // 文件保存到工作区
    }
  }
}
```

**对接工作量估算（每个CLI）：**
- Claude Code: ~50行 (已有skill机制，直接注册为skill)
- Codex CLI: ~80行 (MCP server + custom command)
- Cursor: ~100行 (.cursorrules + MCP)
- 其他: ~100-200行

---

## 6. 目录结构草案 (v2)

```
agent_harness/
├── core/
│   ├── envelope.py              # 通用消息信封 + LazyCache
│   ├── orchestrator.py          # 调度引擎(装配→执行→反馈)
│   ├── spiral_refiner.py        # v2新增: 螺旋收敛控制器
│   ├── router.py                # 路由层(意图→策略匹配, 支持多轮精炼)
│   ├── convergence.py           # v2新增: 收敛半径计算 + 收敛速度指标
│   └── feedback_engine.py       # 反馈信号处理+动态权重更新+动态阈值
├── modules/
│   ├── preproc/
│   │   ├── base.py
│   │   ├── simple.py
│   │   ├── full.py
│   │   └── code.py
│   ├── decomp/
│   │   ├── base.py
│   │   ├── single.py
│   │   ├── linear.py
│   │   └── dag.py
│   ├── schedule/
│   │   ├── base.py
│   │   ├── sequential.py        # MVP用这个
│   │   ├── parallel_eager.py
│   │   └── context_aware.py
│   ├── context/
│   │   ├── base.py
│   │   ├── lazy_cache.py        # v2新增: 混合指针+缓存实现
│   │   ├── minimal.py
│   │   ├── full.py
│   │   └── incremental.py
│   ├── execute/
│   │   ├── base.py
│   │   └── executor.py
│   └── deliver/
│       ├── base.py
│       ├── diff.py
│       ├── report.py
│       └── composite.py
├── adapters/
│   ├── base_adapter.py
│   ├── claude_code.py           # MVP优先实现
│   ├── codex_cli.py
│   └── cursor.py
├── strategies/
│   └── route_table.json         # 路由策略表(含spiral_config)
├── feedback/
│   ├── weights.json              # 策略权重
│   ├── convergence_history.json  # v2: 收敛速度历史
│   └── thresholds.json           # v2: 动态阈值状态
└── tests/
    └── ...
```

---

## 7. 第一版实现范围 (MVP)

| 组件 | 范围 | 原因 |
|---|---|---|
| Router | 规则匹配，6种意图 + 螺旋精炼 | 螺旋是v2核心，必须从MVP开始 |
| Preproc | `simple` + `code` 两个变体 | full版需要NER模型，先跳过 |
| Decomp | `single` + `linear` | DAG并行可以后加 |
| Schedule | `sequential` only | 先跑通串行链路 |
| Context | `full` + `LazyCache` | 混合方案是基础设施，MVP就得有 |
| Execute | 完整实现(含失败分类+自愈) | 你最有积累的模块，直接完整版 |
| Deliver | `diff` + `report` | 覆盖代码和文字两类输出 |
| SpiralRefiner | 收敛半径计算 + 轮次控制 | v2核心，先简单公式 |
| Convergence | 收敛速度记录(不优化) | 先收集数据 |
| Adapter | **仅 Claude Code** | 你最熟悉，最快验证 |
| Feedback | 记录但不更新权重 | 先收集数据，Phase 2再开 |

**MVP 验证路径：**
1. 用 Claude Code adapter 跑通 `简单查询` 任务（0螺旋，1轮到交付）
2. 跑通 `代码实现` 任务（2-3轮螺旋，验证收敛半径递减）
3. 跑通 `代码修复` 任务（验证失败分类+自愈+螺旋重装配）
4. 收集 c (收敛速度) 数据，为 Phase 2 动态阈值提供基线

**不在MVP范围的：**
- 并行调度（Schedule parallel_eager）
- DAG 拆解（Decomp dag）
- 动态阈值自动调整（Phase 2）
- Explore 机制（Phase 3）
- Codex / Cursor adapter

---

## 8. 关键设计决策(与量化类比的对应)

| 量化概念 | Harness v2 对应 | 状态 |
|---|---|---|
| 因子库 | 六模块 × N变体 = 模块池 | ✅ 已定义 |
| 因子组合 | 策略表中的 assembly pipeline | ✅ 已定义 |
| 因子IC | 每个模块变体对收敛速度 c 的边际贡献 | 🔲 需数据积累后计算 |
| 动态调仓 | 反馈闭环中的权重更新 | 🔲 Phase 2 |
| 市场环境分类 | 意图分类 (6类) | ✅ 冷启动规则 |
| 市场环境切换 | **螺旋精炼：每轮重新分类+重新装配** | ✅ v2核心机制 |
| Alpha 衰减 | **收敛速度 c: 少轮次达到交付 → c 高** | ✅ v2核心指标 |
| 离线回放 | 反馈信号回放 | 🔲 Phase 3 |
| 过拟合 | 策略对特定用户过度特化 | 🔲 需跨用户数据 |

---

## 9. Loop ↔ Harness 关系详解

这是对你第一个问题的完整回答。

```
┌─────────────────────────────────────────────────────────┐
│                    Smart-Loop (控制面)                    │
│                                                         │
│  while convergence_radius > ε:                          │
│      envelope = harness.start_task(user_input)          │
│      result = harness.execute_one_spiral(envelope)      │
│      user_feedback = observe_user_behavior(result)      │
│      envelope = harness.refine(envelope, user_feedback) │
│                                                         │
│  harness.deliver(result)                                │
│                                                         │
│  Loop的职责:                                            │
│  - 决定是否继续螺旋                                      │
│  - 决定何时切换策略                                      │
│  - 管理跨轮次状态                                       │
│  - 可调用其他技能(非harness模块)做辅助任务               │
└──────────────────────┬──────────────────────────────────┘
                       │ 每轮调用
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Agent Harness (数据面 + 执行面)              │
│                                                         │
│  Envelope 在 6 模块间传递，Loop 不关心内部细节            │
│                                                         │
│  harness.start_task()     → 初始化 Envelope              │
│  harness.execute_spiral() → Router→Preproc→...→Execute  │
│  harness.refine()         → 更新 Envelope 约束+收敛半径   │
│  harness.deliver()        → Deliverer 格式化输出         │
└─────────────────────────────────────────────────────────┘
```

**关键原则：**
- Loop **不直接操作** Envelope 内部字段（收敛半径等由 SpiralRefiner 管理）
- Loop 只读取 `convergence_radius` 和 `feedback` 做控制决策
- 模块装配由 Router 决定，**Loop 可以建议但不可以强制定**
- 这样 Loop 和 Harness 可以独立演化

---

## 附录：Envelope 的线上形态 (v2)

```python
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
from uuid import uuid4


@dataclass
class LazyCache:
    """混合上下文方案：指针传递 + 按需加载 + 缓存复用"""
    _store: Dict[str, dict] = field(default_factory=dict)
    _resolver: Any = None  # Context模块的resolve函数引用

    def resolve(self, ref: str) -> Optional[dict]:
        if ref not in self._store:
            if self._resolver:
                self._store[ref] = self._resolver(ref)
        return self._store.get(ref)

    def preload(self, refs: List[str]) -> None:
        """批量预热缓存"""
        for ref in refs:
            self.resolve(ref)

    def clear(self) -> None:
        """跨轮次清空缓存(refs保留)"""
        self._store.clear()

    def dump(self) -> dict:
        """调试：导出当前缓存状态"""
        return {
            ref: {"relevance": v.get("relevance_score"), "tokens": v.get("token_count")}
            for ref, v in self._store.items()
        }


@dataclass
class Envelope:
    version: str = "2.0"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_span_id: Optional[str] = None
    intent_class: Optional[str] = None
    strategy_id: Optional[str] = None
    module_from: Optional[str] = None
    module_to: Optional[str] = None

    # v2 螺旋收敛字段
    spiral_iteration: int = 0
    spiral_max_iterations: int = 5
    convergence_radius: float = 1.0
    convergence_target: float = 0.05

    task: dict = field(default_factory=dict)
    context: dict = field(default_factory=lambda: {
        "refs": [],
        "cache": LazyCache(),
        "window_budget_total": 200000,
        "window_used_so_far": 0
    })
    feedback: dict = field(default_factory=dict)

    def spawn(self, module_to: str) -> "Envelope":
        """创建子span，用于模块间传递。缓存引用共享。"""
        return Envelope(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            module_from=self.module_to,
            module_to=module_to,
            intent_class=self.intent_class,
            strategy_id=self.strategy_id,
            spiral_iteration=self.spiral_iteration,
            spiral_max_iterations=self.spiral_max_iterations,
            convergence_radius=self.convergence_radius,
            convergence_target=self.convergence_target,
            task=dict(self.task),
            context=self.context,   # 共享同一个LazyCache引用
            feedback=dict(self.feedback),
        )

    def spawn_next_spiral(self) -> "Envelope":
        """创建下一轮螺旋的Envelope，缓存清空但refs保留"""
        next_env = Envelope(
            trace_id=self.trace_id,
            intent_class=self.intent_class,
            strategy_id=self.strategy_id,
            spiral_iteration=self.spiral_iteration + 1,
            spiral_max_iterations=self.spiral_max_iterations,
            convergence_radius=self.convergence_radius,
            convergence_target=self.convergence_target,
            task=dict(self.task),
            context={
                "refs": list(self.context.get("refs", [])),
                "cache": LazyCache(),
                "window_budget_total": self.context.get("window_budget_total", 200000),
                "window_used_so_far": 0
            },
            feedback=dict(self.feedback),
        )
        return next_env
```

---

## 10. v1 → v2 变更总结

| 变更点 | v1 | v2 |
|---|---|---|
| 运行范式 | 线性管道，一次判定 | **螺旋收敛**，每轮精炼意图 |
| Router | 一次性意图分类 | **多轮精炼器**，每轮缩小解空间 |
| 收敛度量 | 无 | **收敛半径 r + 收敛速度 c** |
| 上下文 | 纯指针方案 | **混合方案(指针+LazyCache)** |
| 反馈闭环 | 固定Phase阈值(50/200次) | **动态阈值引擎**(根据用户行为自适应) |
| Loop关系 | 未定义 | **双层架构**(Loop控制面 + Envelope数据面) |
| 优化目标 | 任务完成率 | **收敛速度 c** (少步骤逼近目标) |
| 自组装 | 策略表固定装配 | **每轮可重新装配**(收敛半径驱动) |
