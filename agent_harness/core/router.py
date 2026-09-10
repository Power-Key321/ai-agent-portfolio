"""
路由层 — 意图识别 → 策略匹配 → 模块装配指令。

v2: 支持螺旋多轮精炼。每轮 Router 可以重新匹配策略、
调整装配链（如从 decomp.single 升级到 decomp.linear）。

冷启动用规则匹配，后期可替换为模型路由。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_harness.core.envelope import Envelope


@dataclass
class AssemblyInstruction:
    """单条装配指令：哪个模块 + 哪个变体 + 在链中的位置。"""

    module: str
    variant: str
    position: int


@dataclass
class StrategyConfig:
    """一条策略配置：意图匹配 → 装配链 + 螺旋配置。"""

    strategy_id: str
    intent_patterns: list[str]
    assembly: list[str]  # ["preproc.code", "decomp.dag", ...]
    max_parallel_subtasks: int = 1
    default_model: str = "sonnet"
    retry_policy: str = "standard"
    spiral_config: dict = field(default_factory=lambda: {
        "max_iterations": 5,
        "convergence_threshold": 0.05,
        "refinement_strategy": "add_constraints",
    })

    def to_assembly_instructions(self) -> list[AssemblyInstruction]:
        instructions = []
        for i, entry in enumerate(self.assembly):
            if "." in entry:
                module, variant = entry.split(".", 1)
            else:
                module, variant = entry, "default"
            instructions.append(AssemblyInstruction(module=module, variant=variant, position=i))
        return instructions


class Router:
    """意图路由器。

    用法:
        router = Router()
        router.load_strategies()  # 加载内置策略表

        envelope = router.classify(envelope, user_input)
        # → envelope.intent_class = "code_feature"
        # → envelope.strategy_id = "code_feature"

        strategy = router.match(envelope)
        # → StrategyConfig

        instructions = router.assemble(strategy)
        # → list[AssemblyInstruction]
    """

    def __init__(self, strategies_path: Optional[Path] = None):
        self._strategies: dict[str, StrategyConfig] = {}
        self._strategies_path = strategies_path
        self._use_adaptive: bool = False
        self._analyzer = None
        self._assembler = None

    def load_strategies(self, path: Optional[Path] = None) -> None:
        """加载策略表。优先从 JSON 文件，回退到内置默认。"""
        target = path or self._strategies_path
        if target and target.exists():
            self._load_from_json(target)
        else:
            self._load_defaults()

    def _load_from_json(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        for sid, cfg in data.get("strategies", {}).items():
            self._strategies[sid] = StrategyConfig(
                strategy_id=sid,
                intent_patterns=cfg.get("intent_patterns", []),
                assembly=cfg.get("assembly", []),
                max_parallel_subtasks=cfg.get("max_parallel_subtasks", 1),
                default_model=cfg.get("default_model", "sonnet"),
                retry_policy=cfg.get("retry_policy", "standard"),
                spiral_config=cfg.get("spiral_config", {}),
            )

    def _load_defaults(self) -> None:
        """内置默认策略表（冷启动规则）。

        包含经典版（v1）和演绎增强版（v2）。
        通过 set_mode() 切换，默认使用 v2 演绎增强版。
        """
        self._classic_strategies = {
            "code_feature": StrategyConfig(
                strategy_id="code_feature",
                intent_patterns=[
                    r"实现", r"添加.*功能", r"开发", r"写一个", r"创建",
                    r"做一个", r"帮我.*做", r"帮我.*写", r"帮我.*实现",
                    r"create", r"add.*feature", r"implement", r"build", r"make.*a",
                ],
                assembly=[
                    "preproc.code", "decomp.linear", "schedule.sequential",
                    "context.full", "execute", "deliver.diff",
                ],
                max_parallel_subtasks=3,
                default_model="opus",
                retry_policy="standard",
                spiral_config={
                    "max_iterations": 5,
                    "convergence_threshold": 0.05,
                    "refinement_strategy": "add_constraints",
                },
            ),
            "code_fix": StrategyConfig(
                strategy_id="code_fix",
                intent_patterns=[
                    r"修复", r"fix", r"bug", r"报错", r"错误", r"error",
                    r"不工作", r"坏了",
                ],
                assembly=[
                    "preproc.code", "decomp.single", "schedule.sequential",
                    "context.full", "execute", "deliver.diff",
                ],
                max_parallel_subtasks=1,
                default_model="sonnet",
                retry_policy="aggressive",
                spiral_config={
                    "max_iterations": 3,
                    "convergence_threshold": 0.08,
                    "refinement_strategy": "narrow_scope",
                },
            ),
            "data_analysis": StrategyConfig(
                strategy_id="data_analysis",
                intent_patterns=[
                    r"分析", r"数据", r"统计", r"可视化", r"报表",
                    r"analy", r"report", r"chart", r"plot",
                ],
                assembly=[
                    "preproc.full", "decomp.linear", "schedule.sequential",
                    "context.minimal", "execute", "deliver.report",
                ],
                max_parallel_subtasks=5,
                default_model="opus",
                retry_policy="standard",
                spiral_config={
                    "max_iterations": 4,
                    "convergence_threshold": 0.05,
                    "refinement_strategy": "add_constraints",
                },
            ),
            "research": StrategyConfig(
                strategy_id="research",
                intent_patterns=[
                    r"调研", r"搜索", r"查找", r"找", r"查",
                    r"research", r"search", r"find", r"look",
                ],
                assembly=[
                    "preproc.full", "decomp.linear", "schedule.sequential",
                    "context.minimal", "execute", "deliver.report",
                ],
                max_parallel_subtasks=8,
                default_model="haiku",
                retry_policy="conservative",
                spiral_config={
                    "max_iterations": 3,
                    "convergence_threshold": 0.10,
                    "refinement_strategy": "narrow_scope",
                },
            ),
            "simple_query": StrategyConfig(
                strategy_id="simple_query",
                intent_patterns=[
                    r"什么是", r"怎么", r"解释", r"说明",
                    r"what is", r"how to", r"explain",
                ],
                assembly=[
                    "preproc.simple", "decomp.single", "schedule.sequential",
                    "context.minimal", "execute", "deliver.report",
                ],
                max_parallel_subtasks=1,
                default_model="haiku",
                retry_policy="conservative",
                spiral_config={
                    "max_iterations": 1,
                    "convergence_threshold": 0.20,
                    "refinement_strategy": None,
                },
            ),
            "refactor": StrategyConfig(
                strategy_id="refactor",
                intent_patterns=[
                    r"重构", r"整理", r"优化结构", r"refactor",
                    r"restructure", r"clean",
                ],
                assembly=[
                    "preproc.code", "decomp.linear", "schedule.sequential",
                    "context.full", "execute", "deliver.diff",
                ],
                max_parallel_subtasks=2,
                default_model="opus",
                retry_policy="standard",
                spiral_config={
                    "max_iterations": 4,
                    "convergence_threshold": 0.05,
                    "refinement_strategy": "add_constraints",
                },
            ),
        }

        # v2 演绎增强版：用碳基演绎法模块替换经典模块
        self._deductive_strategies = {
            "code_feature": StrategyConfig(
                strategy_id="code_feature",
                intent_patterns=self._classic_strategies["code_feature"].intent_patterns,
                assembly=[
                    "preproc.deductive", "decomp.entropy", "schedule.sequential",
                    "context.full", "execute.gated", "deliver.gated",
                ],
                max_parallel_subtasks=3,
                default_model="opus",
                retry_policy="standard",
                spiral_config={
                    "max_iterations": 5,
                    "convergence_threshold": 0.05,
                    "refinement_strategy": "add_constraints",
                },
            ),
            "code_fix": StrategyConfig(
                strategy_id="code_fix",
                intent_patterns=self._classic_strategies["code_fix"].intent_patterns,
                assembly=[
                    "preproc.deductive", "decomp.entropy", "schedule.sequential",
                    "context.full", "execute.gated", "deliver.gated",
                ],
                max_parallel_subtasks=1,
                default_model="sonnet",
                retry_policy="aggressive",
                spiral_config={
                    "max_iterations": 3,
                    "convergence_threshold": 0.08,
                    "refinement_strategy": "narrow_scope",
                },
            ),
            "data_analysis": StrategyConfig(
                strategy_id="data_analysis",
                intent_patterns=self._classic_strategies["data_analysis"].intent_patterns,
                assembly=[
                    "preproc.deductive", "decomp.entropy", "schedule.sequential",
                    "context.minimal", "execute.gated", "deliver.gated",
                ],
                max_parallel_subtasks=5,
                default_model="opus",
                retry_policy="standard",
                spiral_config={
                    "max_iterations": 4,
                    "convergence_threshold": 0.05,
                    "refinement_strategy": "add_constraints",
                },
            ),
            "research": StrategyConfig(
                strategy_id="research",
                intent_patterns=self._classic_strategies["research"].intent_patterns,
                assembly=[
                    "preproc.deductive", "decomp.entropy", "schedule.sequential",
                    "context.minimal", "execute.gated", "deliver.gated",
                ],
                max_parallel_subtasks=8,
                default_model="haiku",
                retry_policy="conservative",
                spiral_config={
                    "max_iterations": 3,
                    "convergence_threshold": 0.10,
                    "refinement_strategy": "narrow_scope",
                },
            ),
            "simple_query": StrategyConfig(
                strategy_id="simple_query",
                intent_patterns=self._classic_strategies["simple_query"].intent_patterns,
                assembly=[
                    "preproc.deductive", "decomp.entropy", "schedule.sequential",
                    "context.minimal", "execute.gated", "deliver.gated",
                ],
                max_parallel_subtasks=1,
                default_model="haiku",
                retry_policy="conservative",
                spiral_config={
                    "max_iterations": 1,
                    "convergence_threshold": 0.20,
                    "refinement_strategy": None,
                },
            ),
            "refactor": StrategyConfig(
                strategy_id="refactor",
                intent_patterns=self._classic_strategies["refactor"].intent_patterns,
                assembly=[
                    "preproc.deductive", "decomp.entropy", "schedule.sequential",
                    "context.full", "execute.gated", "deliver.gated",
                ],
                max_parallel_subtasks=2,
                default_model="opus",
                retry_policy="standard",
                spiral_config={
                    "max_iterations": 4,
                    "convergence_threshold": 0.05,
                    "refinement_strategy": "add_constraints",
                },
            ),
        }

        self._strategies = self._deductive_strategies  # 默认使用 v2
        self._mode = "deductive"

        # v2.1: 给所有 strategy 自动追加 neg_verify（在 deliver.gated 之后）
        # 这样 harness 在交付前自动检测否定结论，触发外部对照。
        # neg_verify 模块自带黑名单过滤，simple_query 不会触发外部研究。
        self._inject_neg_verify_into_all_strategies()

    def _inject_neg_verify_into_all_strategies(self) -> None:
        """在所有 strategy 的 assembly 末尾追加 deliver.neg_verify。

        只对包含 deliver.gated 的 strategy 生效，避免破坏 diff/report 路径。
        """
        for strategy_set in (self._classic_strategies, self._deductive_strategies):
            for sid, sconfig in strategy_set.items():
                if "deliver.gated" in sconfig.assembly and "deliver.neg_verify" not in sconfig.assembly:
                    # 找到 deliver.gated 的位置，在它后面插入 neg_verify
                    new_assembly = []
                    for module in sconfig.assembly:
                        new_assembly.append(module)
                        if module == "deliver.gated":
                            new_assembly.append("deliver.neg_verify")
                    sconfig.assembly = new_assembly

    def set_mode(self, mode: str) -> str:
        """切换策略模式: 'classic' | 'deductive'。

        deductive 使用碳基演绎法增强模块（5要素压缩、熵减链、门检、自检）。
        classic 使用原始模块（关键词实体、固定分解、无门检）。
        """
        if mode == "classic":
            self._strategies = self._classic_strategies
            self._mode = "classic"
            self._use_adaptive = False
        elif mode == "deductive":
            self._strategies = self._deductive_strategies
            self._mode = "deductive"
            self._use_adaptive = False
        elif mode == "adaptive":
            self._strategies = self._deductive_strategies
            self._mode = "adaptive"
            self._use_adaptive = True
        return self._mode

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_adaptive(self) -> bool:
        return self._use_adaptive

    def enable_adaptive(self) -> None:
        """启用自适应乐高模式。启用后 classify() 仍按原路径分类，
        但 assemble_from_profile() 可用，且 match()/assemble() 可被
        profile-based 路径替代。"""
        self._use_adaptive = True
        self._mode = "adaptive"

    # ── 自适应方法 (v4) ──

    def create_profile(self, envelope: Envelope) -> "ProblemProfile":  # noqa: F821
        """从 envelope 生成 ProblemProfile (委托给 ProblemAnalyzer)。"""
        if self._analyzer is None:
            from agent_harness.core.problem_analyzer import ProblemAnalyzer
            self._analyzer = ProblemAnalyzer()
        return self._analyzer.analyze(envelope)

    def assemble_from_profile(self, profile: "ProblemProfile") -> list[AssemblyInstruction]:  # noqa: F821
        """从 ProblemProfile 生成动态装配链 (委托给 CapabilityAssembler)。"""
        if self._assembler is None:
            from agent_harness.core.capability_assembler import CapabilityAssembler
            self._assembler = CapabilityAssembler()
        return self._assembler.assemble(profile)

    def assemble_from_strategy_id(self, strategy_id: str) -> list[AssemblyInstruction]:
        """从 legacy strategy_id 生成装配链 (向后兼容预设映射)。"""
        if self._assembler is None:
            from agent_harness.core.capability_assembler import CapabilityAssembler
            self._assembler = CapabilityAssembler()
        return self._assembler.assemble_from_strategy_id(strategy_id)

    def classify(self, envelope: Envelope, user_input: str) -> Envelope:
        """根据用户输入分类意图，写入 envelope。

        每轮螺旋可重新调用，支持意图精炼。
        """
        envelope.task["original_input"] = envelope.task.get("original_input") or user_input

        matched, confidence = self._match_intent(user_input)

        if envelope.intent_class is None:
            envelope.intent_class = matched
            envelope.strategy_id = matched
        elif confidence > 0.8 and matched != envelope.intent_class:
            envelope.task.setdefault("intent_history", []).append({
                "from": envelope.intent_class,
                "to": matched,
                "iteration": envelope.spiral_iteration,
            })
            envelope.intent_class = matched
            envelope.strategy_id = matched

        return envelope

    def refine_for_spiral(self, envelope: Envelope, user_feedback: dict) -> Envelope:
        """螺旋精炼回调：根据用户反馈重新分类或增加约束。

        这是注入到 SpiralRefiner.on_refine 的回调。
        """
        explicit = user_feedback.get("explicit_constraints", {})
        for key, value in explicit.items():
            envelope.add_constraint(key, value)

        note = user_feedback.get("note", "")
        if note:
            matched, confidence = self._match_intent(note)
            if confidence > 0.6:
                old = envelope.intent_class
                envelope.intent_class = matched
                envelope.strategy_id = matched
                envelope.task.setdefault("intent_history", []).append({
                    "from": old, "to": matched,
                    "iteration": envelope.spiral_iteration,
                    "trigger": "user_feedback",
                })

        return envelope

    def match(self, envelope: Envelope) -> StrategyConfig:
        """根据 envelope 匹配策略配置。"""
        sid = envelope.strategy_id or envelope.intent_class or "simple_query"
        return self._strategies.get(sid, self._strategies["simple_query"])

    def assemble(self, strategy: StrategyConfig) -> list[AssemblyInstruction]:
        """从策略配置产出装配指令列表。"""
        return strategy.to_assembly_instructions()

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def _match_intent(self, text: str) -> tuple[str, float]:
        """简单规则匹配：遍历所有策略的 intent_patterns，返回最佳匹配。

        无匹配时返回 ("", 0.0)，由上层决定是否fallback到模型路由。
        """
        best, best_score = "", 0.0
        text_lower = text.lower()

        for sid, cfg in self._strategies.items():
            for pattern in cfg.intent_patterns:
                try:
                    if re.search(pattern, text_lower):
                        score = len(pattern) / 20.0
                        score = min(score, 1.0)
                        if score > best_score:
                            best, best_score = sid, score
                except re.error:
                    if pattern.lower() in text_lower:
                        score = len(pattern) / 20.0
                        if score > best_score:
                            best, best_score = sid, score

        return best, best_score
