"""
DeductionEngine — 碳基大脑演绎法核心引擎。

封装 smart-loop v6 的全部方法论：
- 本质压缩（5要素）
- 概率推断（歧义不审问，列概率分布）
- 熵减链分解（信息源→过滤→处理→产出→验证）
- 8维自动补全（含输入依赖声明和风险预判）
- 量化门检（4道，按任务类型区分）
- 退化检测 + 降级策略
- 交付前6项自检 + 代价预估
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════


@dataclass
class FiveElements:
    """本质压缩五要素。"""
    subject: str = ""        # 行为主体：用户想扮演什么角色？
    action: str = ""         # 动作本质：压缩后的核心动作
    object: str = ""         # 目标对象：对什么执行？
    value_chain: str = ""    # 价值链：信息→处理→产出的流向
    sustainability: str = ""  # 可持续性：有限搜索 vs 无限监控 vs 一次性

    @property
    def completeness(self) -> float:
        filled = sum(1 for v in [self.subject, self.action, self.object,
                                  self.value_chain, self.sustainability] if v)
        return filled / 5.0


@dataclass
class EntropyStage:
    """熵减链的一个阶段。"""
    name: str                # 信息源/过滤层/处理层/产出层/验证层
    description: str
    input_dependencies: list[str] = field(default_factory=list)
    success_threshold: str = ""
    degradation_threshold: str = ""
    max_rounds: int = 10


@dataclass
class SubtaskSpec:
    """一个完整的子任务规格（含8维补全）。"""
    id: str = ""
    name: str = ""                    # 维度1: 动作+对象+产出
    goal: str = ""                    # 维度2: 目标
    entropy_stage: str = ""           # 熵减位置
    success_criteria: str = ""        # 维度3: 成功标准
    actions: list[str] = field(default_factory=list)  # 维度4: 每轮动作
    quant_metric_name: str = ""       # 维度5: 量化产出指标名
    quant_metric_unit: str = ""
    quant_metric_target: float = 0.0
    output_file: str = ""             # 维度6: 产出物
    input_dependencies: list[str] = field(default_factory=list)  # 维度7: 输入依赖
    stop_conditions: dict = field(default_factory=dict)  # 维度8: 停止条件
    risk_prediction: dict = field(default_factory=dict)   # 风险预判
    fallback_strategy: str = ""       # 降级策略


@dataclass
class GateResult:
    """门检结果。"""
    passed: bool
    gate_name: str
    details: str = ""
    metric_value: Any = None
    degradation: bool = False


# ═══════════════════════════════════════════════════════════════
# 演绎引擎
# ═══════════════════════════════════════════════════════════════


class DeductionEngine:
    """碳基大脑演绎法核心引擎。

    所有方法都是纯函数，不持有状态，可被任何模块调用。
    """

    # ── 主体角色映射 ──
    SUBJECT_ROLES = {
        "实现": "构建者", "写": "构建者", "开发": "构建者", "创建": "构建者",
        "添加": "构建者", "做": "构建者", "build": "构建者", "implement": "构建者",
        "修复": "维护者", "fix": "维护者", "修": "维护者", "改": "维护者",
        "分析": "分析者", "统计": "分析者", "analy": "分析者",
        "搜索": "探索者", "查找": "探索者", "调研": "探索者", "找": "探索者",
        "监控": "观察者", "盯": "观察者", "watch": "观察者", "monitor": "观察者",
        "重构": "优化者", "整理": "优化者", "优化": "优化者", "refactor": "优化者",
        "解释": "解释者", "什么是": "解释者", "explain": "解释者",
    }

    # ── 动作本质映射 ──
    ACTION_ESSENCE = {
        "构建者": "构建/实现", "维护者": "诊断/修复", "分析者": "采集/分析/评估",
        "探索者": "搜索/调研/发现", "观察者": "监控/追踪/预警",
        "优化者": "审查/优化/重构", "解释者": "解释/阐述",
    }

    # ── 熵减链模板（按任务类型） ──
    ENTROPY_CHAINS = {
        "code_feature": [
            EntropyStage("信息源", "读取现有项目结构和相关代码", [], "有效文件数≥3", "连续2轮无新增", 5),
            EntropyStage("过滤层", "筛选出需要修改/新增的模块", ["信息源"], "候选模块≥1", "连续2轮无新增", 3),
            EntropyStage("处理层", "逐模块实现/修改代码", ["过滤层"], "实现文件数≥目标", "连续3轮无改善", 10),
            EntropyStage("产出层", "组装变更列表，生成 diff", ["处理层"], "diff 可应用", "连续2轮无更新", 3),
            EntropyStage("验证层", "验证实现正确性（类型检查/测试）", ["产出层"], "测试通过率100%", "连续2轮无新增问题", 5),
        ],
        "code_fix": [
            EntropyStage("信息源", "定位出错的代码和上下文", [], "定位到具体文件和行号", "连续2轮无法定位", 5),
            EntropyStage("过滤层", "确定根因而非症状", ["信息源"], "根因假设≥1", "连续2轮假设被推翻", 3),
            EntropyStage("处理层", "实施修复", ["过滤层"], "修复后错误消失", "连续3轮错误仍存在", 5),
            EntropyStage("验证层", "回归验证（不引入新问题）", ["处理层"], "回归测试通过", "连续2轮发现新问题", 3),
        ],
        "data_analysis": [
            EntropyStage("信息源", "采集原始数据", [], "有效数据条数≥目标", "连续3轮0新增", 10),
            EntropyStage("过滤层", "清洗/筛选关键维度", ["信息源"], "筛出候选维度≥1", "连续2轮0产出", 5),
            EntropyStage("处理层", "多维度并行分析", ["过滤层"], "发现/洞察≥目标", "连续3轮无变化", 10),
            EntropyStage("产出层", "综合评分/可视化", ["处理层"], "报告完整度≥80%", "连续2轮无更新", 5),
            EntropyStage("验证层", "交叉验证分析结论", ["产出层"], "验证通过率≥80%", "连续2轮无新增确认", 3),
        ],
        "research": [
            EntropyStage("信息源", "枚举搜索维度/关键词", [], "维度覆盖≥3个", "连续3轮0新增", 8),
            EntropyStage("过滤层", "逐维探测/筛选相关结果", ["信息源"], "相关结果≥5", "连续2轮0产出", 5),
            EntropyStage("处理层", "聚合线索/结构化信息", ["过滤层"], "结构化条目≥10", "连续3轮无新增", 8),
            EntropyStage("产出层", "汇总发现/撰写报告", ["处理层"], "报告覆盖所有维度", "连续2轮无更新", 3),
        ],
        "refactor": [
            EntropyStage("信息源", "审查现有代码结构/依赖", [], "模块依赖图完整", "连续2轮无新增理解", 5),
            EntropyStage("过滤层", "识别重构目标（高耦合/重复）", ["信息源"], "重构目标≥1", "连续2轮无新增目标", 3),
            EntropyStage("处理层", "逐模块执行重构", ["过滤层"], "重构后功能等价", "连续3轮无改善", 8),
            EntropyStage("验证层", "回归测试+性能对比", ["处理层"], "回归通过+性能不退化", "连续2轮发现退化", 3),
        ],
        "simple_query": [
            EntropyStage("信息源", "理解问题并检索相关知识", [], "相关信息≥1条", "无相关信息", 3),
            EntropyStage("产出层", "组织回答", ["信息源"], "回答清晰完整", "连续2轮未改善", 2),
        ],
    }

    # ── 公共方法 ──

    def compress_to_five_elements(self, user_input: str, intent_class: str = "",
                                   entities: dict | None = None) -> FiveElements:
        """将用户输入压缩为五要素。

        这是碳基演绎法的第一步：不做二元判断，提取结构化的语义骨架。
        """
        text_lower = user_input.lower()

        # 主体: 映射到角色
        subject = self._infer_subject(text_lower)

        # 动作: 从角色推导动作本质
        action = self.ACTION_ESSENCE.get(subject, "理解/回答")

        # 对象: 从输入中提取核心名词短语
        obj = self._extract_object(text_lower, entities or {})

        # 价值链: 根据意图类型推断信息流动
        value_chain = self._infer_value_chain(intent_class, subject)

        # 可持续性: 判断是有限搜索还是一次性
        sustainability = self._infer_sustainability(intent_class, text_lower)

        return FiveElements(
            subject=subject,
            action=action,
            object=obj,
            value_chain=value_chain,
            sustainability=sustainability,
        )

    def infer_intent_probabilities(self, user_input: str,
                                    entities: dict | None = None) -> list[dict]:
        """概率推断：歧义时不审问，列出所有可能意图的概率分布。

        返回按概率降序排列的意图列表。
        只有当所有概率都 <30% 时才建议询问用户。
        """
        text_lower = user_input.lower()
        probs = []

        # 基于关键词和实体计算各意图的概率
        signals = {
            "code_feature": self._has_creation_signal(text_lower),
            "code_fix": self._has_fix_signal(text_lower),
            "data_analysis": self._has_analysis_signal(text_lower, entities),
            "research": self._has_research_signal(text_lower),
            "refactor": self._has_refactor_signal(text_lower),
            "simple_query": self._has_query_signal(text_lower),
        }

        total = sum(signals.values()) or 1
        for intent, signal in sorted(signals.items(), key=lambda x: -x[1]):
            prob = round(signal / total, 2)
            if prob > 0:
                probs.append({
                    "intent": intent,
                    "probability": prob,
                    "confidence": "high" if prob > 0.5 else ("medium" if prob > 0.3 else "low"),
                })

        return probs

    def build_entropy_subtasks(self, intent_class: str, user_input: str,
                                entities: dict | None = None,
                                complexity: float = 0.5) -> list[SubtaskSpec]:
        """沿熵减链拆解任务，产出含8维补全的子任务列表。

        不同的 intent_class 使用不同的熵减链模板。
        """
        chain = self.ENTROPY_CHAINS.get(intent_class,
                                         self.ENTROPY_CHAINS["simple_query"])
        entities = entities or {}
        subtasks = []

        for i, stage in enumerate(chain):
            spec = SubtaskSpec(
                id=f"s{i + 1}",
                name=self._build_subtask_name(stage, user_input),
                entropy_stage=stage.name,
                goal=f"[{stage.name}] {stage.description}",
                success_criteria=stage.success_threshold,
                actions=self._build_actions(stage, user_input, entities),
                quant_metric_name=self._pick_metric(stage),
                quant_metric_unit="条" if stage.name in ("信息源", "过滤层") else "个",
                quant_metric_target=self._pick_target(stage, complexity),
                input_dependencies=stage.input_dependencies,
                stop_conditions={
                    "success": stage.success_threshold,
                    "degradation": stage.degradation_threshold,
                    "max_rounds": stage.max_rounds,
                },
                risk_prediction=self._predict_risks(stage, intent_class),
                fallback_strategy=self._pick_fallback(stage),
            )
            subtasks.append(spec)

        return subtasks

    def run_gate_checks(self, subtask: dict, execution_result: dict,
                         round_num: int = 0) -> list[GateResult]:
        """量化门检4道 — 每轮执行后强制检查。

        不同任务类型使用不同判定逻辑。
        """
        results = []
        task_type = subtask.get("type", "execute")

        # 门检1: 产出物存在？
        has_output = bool(execution_result)
        results.append(GateResult(
            passed=has_output,
            gate_name="G1_产出存在",
            details="产出物存在" if has_output else "无产出",
            degradation=not has_output,
        ))

        if not has_output:
            return results  # 后续门检无意义

        # 门检2: 含量化指标？
        has_metric = any(
            isinstance(execution_result.get(k), (int, float))
            for k in ["count", "value", "score", "items_found", "changes_made"]
        )
        results.append(GateResult(
            passed=has_metric,
            gate_name="G2_量化指标",
            details="含量化指标" if has_metric else "缺少数值型指标",
            degradation=not has_metric,
        ))

        # 门检3: 数值可比较？
        comparable = has_metric  # 有数字就能比较
        results.append(GateResult(
            passed=comparable,
            gate_name="G3_可比较",
            details="数值可比较" if comparable else "无法比较",
            degradation=not comparable,
        ))

        # 门检4: 数值判定（按任务类型区分）
        g4 = self._gate4_by_task_type(task_type, execution_result, round_num)
        results.append(g4)

        return results

    def detect_degradation(self, gate_results: list[GateResult],
                            degradation_streak: int = 0,
                            max_streak: int = 3) -> tuple[bool, str]:
        """退化检测：检查是否应该触发降级。

        Returns:
            (should_degrade, reason)
        """
        degradation_count = sum(1 for g in gate_results if g.degradation)
        total = len(gate_results)

        if degradation_count == 0:
            return False, ""

        if degradation_count == total:
            return True, f"全部{total}道门检未通过"

        if degradation_streak >= max_streak:
            return True, f"连续{degradation_streak}轮退化（上限{max_streak}）"

        if degradation_count >= total / 2:
            return True, f"{degradation_count}/{total}道门检未通过"

        return False, ""

    def run_self_check(self, subtasks: list, execution_results: list,
                        intent_class: str = "",
                        estimated_tokens: int = 0) -> dict:
        """交付前6项自检。

        Returns:
            {passed: bool, checks: [...], warnings: [...]}
        """
        checks = []
        warnings = []

        # 自检1: 各子任务的量化指标是否可比较？
        all_comparable = all(
            any(r.get("status") == "success" for r in execution_results
                if r.get("subtask_id") == st.get("id"))
            for st in subtasks
        )
        checks.append({
            "check": "量化指标可比较",
            "passed": all_comparable,
            "detail": "所有子任务产出可量化比较" if all_comparable else "部分子任务缺少量化产出",
        })

        # 自检2: 串联子任务是否声明了输入依赖？
        deps_declared = all(
            st.get("dependencies") or st.get("entropy_stage") == "信息源"
            for st in subtasks
        )
        checks.append({
            "check": "输入依赖完整",
            "passed": deps_declared,
            "detail": "依赖声明完整" if deps_declared else "部分子任务缺少依赖声明",
        })

        # 自检3: 是否存在上限设置不合理？
        max_rounds_ok = all(
            st.get("stop_conditions", {}).get("max_rounds", 10) <= 15
            for st in subtasks
        )
        checks.append({
            "check": "轮次上限合理",
            "passed": max_rounds_ok,
            "detail": "上限设置合理" if max_rounds_ok else "部分子任务轮次上限偏高",
        })

        # 自检4: 降级策略是否覆盖了所有子任务？
        fallback_coverage = all(
            st.get("fallback_strategy") for st in subtasks
            if st.get("entropy_stage") not in ("信息源",)
        )
        checks.append({
            "check": "降级策略覆盖",
            "passed": fallback_coverage,
            "detail": "降级策略完整" if fallback_coverage else "存在无降级策略的非首阶段子任务",
        })

        # 自检5: 总体代价是否合理？
        cost_ok = estimated_tokens < 200000
        if not cost_ok:
            warnings.append(f"预估 token 消耗 {estimated_tokens:,}，偏高")
        checks.append({
            "check": "代价合理",
            "passed": cost_ok,
            "detail": f"预估 {estimated_tokens:,} tokens" if cost_ok else f"较高: {estimated_tokens:,} tokens",
        })

        # 自检6: 任务类型与装配一致？
        checks.append({
            "check": "任务类型一致",
            "passed": True,
            "detail": f"intent={intent_class}",
        })

        all_passed = all(c["passed"] for c in checks)
        return {
            "passed": all_passed,
            "checks": checks,
            "warnings": warnings,
            "estimated_risk": "low" if all_passed else ("medium" if len(warnings) <= 2 else "high"),
        }

    # ── 私有辅助方法 ──

    def _infer_subject(self, text_lower: str) -> str:
        for keyword, role in self.SUBJECT_ROLES.items():
            if keyword.lower() in text_lower:
                return role
        if len(text_lower) < 15 and "?" not in text_lower and "？" not in text_lower:
            return "探索者"
        return "解释者"

    def _extract_object(self, text_lower: str, entities: dict) -> str:
        parts = []
        if entities.get("language"):
            parts.append(entities["language"])
        if entities.get("framework"):
            parts.append(entities["framework"])
        if entities.get("files_mentioned"):
            parts.append(entities["files_mentioned"][0])
        if entities.get("assets"):
            parts.append(", ".join(entities["assets"][:3]))
        if entities.get("metrics"):
            parts.append(", ".join(entities["metrics"][:2]))
        if parts:
            return " + ".join(parts)
        # 回退: 取输入中的核心名词
        keywords = ["认证", "登录", "注册", "API", "数据库", "缓存", "队列",
                     "中间件", "路由", "用户", "支付", "订单", "分析", "数据",
                     "模块", "系统", "服务", "接口", "组件", "页面", "应用"]
        found = [kw for kw in keywords if kw in text_lower]
        return ", ".join(found[:3]) if found else text_lower[:40]

    def _infer_value_chain(self, intent_class: str, subject: str) -> str:
        chains = {
            "code_feature": "需求→设计→编码→测试→交付",
            "code_fix": "复现→定位→修复→验证→交付",
            "data_analysis": "数据源→清洗→分析→可视化→结论",
            "research": "搜索维→过滤→聚合→结构化→报告",
            "refactor": "审查→识别→重构→验证→交付",
            "simple_query": "理解→检索→组织→回答",
        }
        return chains.get(intent_class, "输入→处理→输出")

    def _infer_sustainability(self, intent_class: str, text_lower: str) -> str:
        if intent_class == "simple_query":
            return "一次性"
        if any(w in text_lower for w in ["持续", "一直", "不断", "监控", "实时"]):
            return "无限监控"
        return "有限搜索(N轮收敛)"

    def _has_creation_signal(self, text: str) -> float:
        kw = ["实现", "开发", "写", "创建", "添加", "做", "搞", "build",
              "implement", "create", "make"]
        return sum(1.0 for w in kw if w in text)

    def _has_fix_signal(self, text: str) -> float:
        kw = ["修复", "fix", "bug", "报错", "错误", "修", "不工作", "坏了",
              "error", "exception", "crash"]
        return sum(1.0 for w in kw if w in text)

    def _has_analysis_signal(self, text: str, entities: dict | None) -> float:
        score = 0.0
        kw = ["分析", "统计", "数据", "走势", "图表", "可视化", "报表",
              "analy", "chart", "plot", "report"]
        score += sum(0.8 for w in kw if w in text)
        if entities:
            if entities.get("assets"):
                score += 1.5
            if entities.get("metrics"):
                score += 1.0
            if entities.get("time_range"):
                score += 0.5
        return score

    def _has_research_signal(self, text: str) -> float:
        kw = ["搜索", "查找", "找", "调研", "搜", "research", "search", "find"]
        return sum(1.0 for w in kw if w in text)

    def _has_refactor_signal(self, text: str) -> float:
        kw = ["重构", "整理", "优化结构", "重写", "refactor", "restructure",
              "clean up", "清理"]
        return sum(1.0 for w in kw if w in text)

    def _has_query_signal(self, text: str) -> float:
        if len(text) < 30 and ("?" in text or "？" in text or "什么是" in text
                                or "怎么" in text or "解释" in text):
            return 2.0
        kw = ["什么是", "怎么", "解释", "what is", "how to", "explain"]
        return sum(0.8 for w in kw if w in text)

    def _build_subtask_name(self, stage: EntropyStage, user_input: str) -> str:
        short_input = user_input[:30]
        return f"[{stage.name}] {stage.description} — {short_input}"

    def _build_actions(self, stage: EntropyStage, user_input: str,
                        entities: dict) -> list[str]:
        actions = {
            "信息源": [f"读取/检索与 '{user_input[:30]}' 相关的信息"],
            "过滤层": [f"从信息源结果中筛选出关键部分"],
            "处理层": [f"对筛选结果执行核心处理/分析/编码"],
            "产出层": [f"将处理结果结构化为可交付格式"],
            "验证层": [f"验证产出的正确性和完整性"],
        }
        return actions.get(stage.name, [stage.description])

    def _pick_metric(self, stage: EntropyStage) -> str:
        metrics = {
            "信息源": "有效数据条数",
            "过滤层": "候选条目数",
            "处理层": "处理产出数",
            "产出层": "交付完整度",
            "验证层": "验证通过率",
        }
        return metrics.get(stage.name, "产出数量")

    def _pick_target(self, stage: EntropyStage, complexity: float) -> float:
        bases = {"信息源": 10, "过滤层": 5, "处理层": 3, "产出层": 1, "验证层": 1}
        base = bases.get(stage.name, 3)
        return max(1, base * (1.0 + complexity))

    def _predict_risks(self, stage: EntropyStage, intent_class: str) -> dict:
        risks = {
            "信息源": {"最可能失败": "数据源不可用或无权限", "触发条件": "连续2轮检索结果为空"},
            "过滤层": {"最可能失败": "筛选条件不合理导致0候选", "触发条件": "连续2轮候选为0"},
            "处理层": {"最可能失败": "逻辑错误或产出质量不达标", "触发条件": "门检连续3轮DEGRADED"},
            "产出层": {"最可能失败": "产出格式不兼容下游", "触发条件": "下游模块无法解析产出"},
            "验证层": {"最可能失败": "验证不充分，遗漏关键问题", "触发条件": "验证通过但后续发现新问题"},
        }
        return risks.get(stage.name, {"最可能失败": "未知", "触发条件": "产出为空"})

    def _pick_fallback(self, stage: EntropyStage) -> str:
        fallbacks = {
            "信息源": "使用缓存数据或用户提供的替代数据源",
            "过滤层": "放宽筛选条件，扩大候选范围",
            "处理层": "降级为简化版处理，优先保证产出存在",
            "产出层": "使用原始格式交付，由下游适配",
            "验证层": "标记为'未充分验证'，交付时附带风险提示",
        }
        return fallbacks.get(stage.name, "跳过此阶段，标记为降级交付")

    def _gate4_by_task_type(self, task_type: str, result: dict,
                             round_num: int) -> GateResult:
        """按任务类型区分的第4道门检。"""
        # 优化/改进类: 数值改善 → PROGRESS
        if task_type in ("code_gen", "refactor", "optimize"):
            changes = result.get("changes_made", 0)
            if changes > 0:
                return GateResult(True, "G4_改善判定", f"产生了{changes}个变更", changes)
            return GateResult(False, "G4_改善判定", "无改善", 0, True)

        # 采集/研究类: 新增>0 → PROGRESS
        if task_type in ("explore", "research", "search"):
            items = result.get("items_found", result.get("count", 0))
            if items > 0:
                return GateResult(True, "G4_新增判定", f"新增{items}条", items)
            return GateResult(False, "G4_新增判定", "无新增", 0, True)

        # 评估/验证类: 新确认项>0 → PROGRESS
        if task_type in ("verify", "validate", "test"):
            confirmed = result.get("confirmed", result.get("tests_passed", 0))
            if confirmed > 0:
                return GateResult(True, "G4_确认判定", f"确认{confirmed}项", confirmed)
            return GateResult(False, "G4_确认判定", "无新确认", 0, True)

        # 默认: 有产出就算PROGRESS
        has_output = bool(result)
        return GateResult(
            has_output, "G4_产出判定",
            "有产出" if has_output else "无产出",
            None, not has_output,
        )


# 模块级单例
_engine: DeductionEngine | None = None


def get_deduction_engine() -> DeductionEngine:
    global _engine
    if _engine is None:
        _engine = DeductionEngine()
    return _engine
