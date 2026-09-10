# Agent Harness Skill — Claude Code 入口

## 描述

Agent Harness 乐高框架 — 将编排系统拆为可插拔独立模块（预处理→拆解→调度→上下文→执行→交付），不同任务自动装配最优组合，螺旋收敛逼近用户真实意图。

**由你（Claude Code）负责意图分类，Harness 负责模块装配和螺旋执行。**

## 触发

```
/harness <任务描述>
```

## 指令

### 1. 意图分类（你来做）

分析用户的任务描述，映射到以下 6 种策略之一：

| 策略 | 适用场景 | 示例 |
|------|---------|------|
| `code_feature` | 实现新功能 | "帮我写一个JWT认证中间件" |
| `code_fix` | 修复 bug/错误 | "修复 src/auth.py 的空指针" |
| `data_analysis` | 数据分析/统计/图表 | "分析最近一周的用户增长" |
| `research` | 搜索/调研/查找信息 | "搜索 Python 异步最佳实践" |
| `simple_query` | 简单问答/概念解释 | "什么是闭包" |
| `refactor` | 重构代码/整理结构 | "重构用户认证模块" |

### 2. 加载 Harness 并执行

```python
import sys
sys.path.insert(0, "<项目根目录>")          # 例: /path/to/agent-skills/harness

from agent_harness.adapters.claude_code import get_adapter

adapter = get_adapter()
result = adapter.start("<用户任务>", intent_override="<你判断的策略>")
```

你将获得完整的框架执行结果。

### 3. 分析结果并汇报

结果包含：
- **deliverable**: 最终交付物（diff_patch / report）
- **convergence**: 收敛摘要（初始半径、最终半径、收敛速度）
- **execution_log**: 每个模块的执行状态（成功/失败/耗时）
- **spiral_iterations**: 螺旋收敛轮次
- **intent_class / strategy_id**: 验证你分类是否正确

**关键判断点：**

1. **收敛速度 c < 0.15** → 说明用户输入约束不足，建议他补充细节后重新执行
2. **execution_log 中有 FAIL** → 定位失败模块，分析失败原因（自愈是否生效？）
3. **分类与实际不符** → 如果装配链看起来不对（比如应该是 diff 交付却是 report），说明你分类错误，重新执行

### 4. 诊断模式（不执行，仅查看装配计划）

```python
result = adapter.diagnose("<用户任务>", intent_override="<策略>")
# 返回: intent, strategy, assembly（六层模块链）, spiral_config
```

适用场景：用户想先看装配计划再决定是否执行。

## 验证策略是否正确

检查 result 中以下信号判断你的分类是否合理：

| 信号 | 含义 |
|------|------|
| `spiral_iterations == 0` | simple_query 短路了，正常 |
| `deliverable.format == "diff_patch"` | 正确用于 code_feature/code_fix/refactor |
| `deliverable.format == "report"` | 正确用于 data_analysis/research/simple_query |
| 模块链含 `decomp.linear` | 复杂任务被拆解为多子任务 |
| 模块链含 `decomp.single` | 简单任务无需拆解 |

## 注意

- Harness 目前的 `execute` 模块只做占位执行（产出 `_artifacts` 标记），**真正的子任务执行由你（Claude Code）在收到交付物后完成**
- 螺旋收敛在当前 MVP 中默认运行 5 轮，`simple_query` 直接短路不进入螺旋
- 框架的核心价值在于 **自动化装配和收敛管理**，把你从"每次都要重新设计工作流"中解放出来
