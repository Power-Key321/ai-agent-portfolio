"""
AdapterBase — 适配器抽象协议。

所有 CLI 适配器（Claude Code, Codex, Cursor 等）必须实现此接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from agent_harness.core.envelope import Envelope
from agent_harness.core.model_router import ModelRouter
from agent_harness.core.orchestrator import Orchestrator
from agent_harness.core.spiral_refiner import SpiralRefiner
from agent_harness.core.state_manager import StateManager
from agent_harness.core.memory_guard import MemoryGuard
from agent_harness.core.observability import get_collector, HarnessReport
from agent_harness.modules.base import ModuleBase


class AdapterBase(ABC):
    """适配器基类 — 定义 Harness 对接到外部 CLI 的标准协议。

    每个外部环境（CC/Codex/Cursor/Windsurf/Shell）各实现一个子类。

    子类必须实现:
    - _register_modules(): 注册该环境可用的模块变体
    - _resolve_model_call(): 该环境的模型调用实现
    - _resolve_tool_call(): 该环境的工具调用实现

    可选覆盖:
    - on_before_spiral(): 每轮螺旋开始前的钩子
    - on_after_spiral(): 每轮螺旋结束后的钩子
    - on_deliver(): 交付前的最后处理钩子
    """

    # 子类需设置
    adapter_name: str = "base"

    def __init__(
        self,
        model_router: ModelRouter | None = None,
        harness_root: Path | None = None,
        agent_mode: str = "inline",  # v3: "inline" | "distributed"
    ):
        self.harness_root = harness_root or Path(__file__).resolve().parent.parent
        self.model_router = model_router or ModelRouter()
        self.orchestrator: Orchestrator | None = None
        self.refiner: SpiralRefiner | None = None
        self.master_agent: "MasterAgent | None" = None  # noqa: F821 — v3
        self.agent_mode = agent_mode
        workspace = str(self.harness_root.parent / ".claude" / "harness_states")
        self.state_manager = StateManager(workspace_dir=workspace)
        self.memory_guard = MemoryGuard(window_budget_total=200000)
        self._cc_envelope: Envelope | None = None

        self._build_orchestrator()
        self._build_refiner()

        if agent_mode == "distributed":
            self._build_master_agent()

    # ── 抽象方法 ──

    @abstractmethod
    def _register_modules(self) -> list[ModuleBase]:
        """子类实现：返回该环境可用的模块变体列表。"""
        ...

    @abstractmethod
    def _resolve_model_call(self, prompt: str, skeleton_hash: str) -> str:
        """子类实现：该环境的模型调用。"""
        ...

    # ── 可选钩子（子类覆盖） ──

    def on_before_spiral(self, envelope: Envelope) -> Envelope:
        return envelope

    def on_after_spiral(self, envelope: Envelope) -> Envelope:
        return envelope

    def on_deliver(self, result: dict) -> dict:
        return result

    # ── 模板方法 ──

    def start(self, user_input: str, context_refs: list[str] | None = None, intent_override: str | None = None) -> dict:
        """Harness 主入口 — 模板方法，子类通常无需覆盖。

        intent_override: 外部（如 Claude Code）直接指定意图，跳过模型分类。
            合法值: code_feature, code_fix, data_analysis, research, simple_query, refactor
        """
        envelope = Envelope()
        envelope.task["original_input"] = user_input

        if intent_override and intent_override in self.model_router.list_strategies():
            envelope.intent_class = intent_override
            envelope.strategy_id = intent_override
            envelope.task["_route_result"] = {
                "method": "claude_override",
                "confidence": 1.0,
                "reasoning": f"外部直接指定意图: {intent_override}",
                "tokens_consumed": 0,
            }
        else:
            self.model_router.classify(envelope, user_input)

        if context_refs:
            envelope.context["refs"] = context_refs
        else:
            envelope.context["refs"] = self._infer_context_refs(envelope)

        # v4 自适应模式: 生成 ProblemProfile
        if getattr(self.model_router, 'is_adaptive', False):
            envelope.problem_profile = self.model_router.create_profile(envelope)

        envelope = self.refiner.start(envelope)
        collector = get_collector()
        t_start = __import__("time").time()

        while envelope.should_continue_spiral:
            envelope = self.on_before_spiral(envelope)
            envelope = self.refiner.execute_spiral(envelope)

            # 记录螺旋收敛
            collector.record_spiral(
                envelope.spiral_iteration, envelope.convergence_radius,
            )

            # v4: profile-based 短路或 legacy simple_query
            if envelope.problem_profile is not None:
                if envelope.problem_profile.is_trivial:
                    break
            elif envelope.strategy_id == "simple_query":
                break
            if envelope.convergence_radius < envelope.convergence_target:
                break

            envelope.feedback["accepted"] = True
            envelope = self.on_after_spiral(envelope)
            envelope = self.refiner.refine(envelope, {"signal": "accepted"})

        convergence_summary = self.refiner.finalize(envelope)
        total_elapsed = (__import__("time").time() - t_start) * 1000
        collector.record_execution(
            envelope.intent_class or "unknown",
            envelope.strategy_id or "unknown",
            len(envelope.task.get("subtasks", [])),
            total_elapsed,
            True,
        )
        result = {
            "deliverable": envelope.task.get("final_deliverable", {}),
            "convergence": convergence_summary,
            "spiral_iterations": envelope.spiral_iteration,
            "execution_log": self.orchestrator.get_execution_log(),
            "intent_class": envelope.intent_class,
            "strategy_id": envelope.strategy_id,
            "route_method": envelope.task.get("_route_result", {}).get("method", "unknown"),
            "metrics": collector.get_snapshot(),
            "report_short": self.get_report_short(),
        }
        return self.on_deliver(result)

    def diagnose(self, user_input: str, intent_override: str | None = None) -> dict:
        """诊断模式 — 分类+装配，不执行。"""
        envelope = Envelope()
        if intent_override and intent_override in self.model_router.list_strategies():
            envelope.intent_class = intent_override
            envelope.strategy_id = intent_override
            envelope.task["_route_result"] = {
                "method": "claude_override",
                "confidence": 1.0,
                "reasoning": f"外部直接指定意图: {intent_override}",
                "tokens_consumed": 0,
            }
        else:
            self.model_router.classify(envelope, user_input)
        strategy = self.model_router.match(envelope)
        instructions = self.model_router.assemble(strategy)
        route_info = envelope.task.get("_route_result", {})

        return {
            "intent": envelope.intent_class,
            "strategy": strategy.strategy_id,
            "model": strategy.default_model,
            "spiral_config": strategy.spiral_config,
            "max_parallel": strategy.max_parallel_subtasks,
            "assembly": [(i.module, i.variant) for i in instructions],
            "route": {
                "method": route_info.get("method", "unknown"),
                "confidence": route_info.get("confidence", 0),
                "reasoning": route_info.get("reasoning", ""),
            },
        }

    # ── 内部通用实现 ──

    def _build_orchestrator(self) -> None:
        self.orchestrator = Orchestrator(router=self.model_router)
        modules = self._register_modules()
        self.orchestrator.register_modules(modules)

    def _build_refiner(self) -> None:
        self.refiner = SpiralRefiner(
            convergence_threshold=0.05,
            max_iterations=5,
            on_spiral_complete=self._run_one_spiral,
            on_refine=self.model_router.refine_for_spiral,
        )

    def _build_master_agent(self) -> None:
        """v3: 构建 MasterAgent (分布式模式)。"""
        from agent_harness.agents.master import MasterAgent
        from agent_harness.agents.bus import AgentBus
        bus = AgentBus()
        self.master_agent = MasterAgent(
            bus=bus,
            orchestrator=self.orchestrator,
            refiner=self.refiner,
            router=self.model_router,
            mode="distributed",
        )
        # 将已注册的模块包装为 InlineSubAgent
        modules = self._register_modules()
        self.master_agent.register_module_agents(modules)

    def _run_one_spiral(self, envelope: Envelope) -> Envelope:
        if self.agent_mode == "distributed" and self.master_agent:
            return self.master_agent.execute(envelope)
        return self.orchestrator.execute(envelope)

    def set_knowledge_graph(self, kg: "KnowledgeGraph") -> None:  # noqa: F821
        """v3: 挂载知识图谱。在 inline 和 distributed 模式下均可用。

        挂载后每轮螺旋自动注入图谱上下文到 Envelope，
        每次交互完成后自动丰富图谱。
        """
        from agent_harness.knowledge.graph_context import GraphContext
        self._graph_context = GraphContext(kg)

        # 分布式模式: 也挂载到 MasterAgent
        if self.master_agent:
            self.master_agent.set_graph(kg)

        # 将图谱注入钩子织入螺旋前置处理
        _original_before_spiral = self.on_before_spiral

        def _inject_graph_context(envelope):
            envelope = _original_before_spiral(envelope)
            if hasattr(self, '_graph_context') and self._graph_context is not None:
                self._graph_context.inject_to_envelope(envelope)
            return envelope

        self.on_before_spiral = _inject_graph_context

    def _infer_context_refs(self, envelope: Envelope) -> list[str]:
        # v4: profile-based inference
        if envelope.problem_profile is not None:
            p = envelope.problem_profile
            refs = ["memory://user_role"]
            if p.domain_code > 0.3 or p.context_dependency > 0.5:
                refs.append("file://.")
            if p.domain_data > 0.3 or p.domain_system > 0.3:
                refs.append("memory://project")
            return refs
        # legacy path
        intent = envelope.intent_class or ""
        refs = ["memory://user_role"]
        if intent in ("code_feature", "code_fix", "refactor"):
            refs.append("file://.")
        if intent in ("data_analysis", "research"):
            refs.append("memory://project")
        return refs

    # ── CC 交互模式 ──

    def start_cc(self, user_input: str, intent_override: str | None = None) -> dict:
        """CC 交互模式 — 分类 + 第一轮螺旋，返回执行计划供 CC 执行。

        Returns:
            {"phase": "execute", "execution_plan": [...], "envelope_summary": {...}}
            或 {"phase": "complete", "deliverable": {...}}（简单任务直接完成）
        """
        self._cc_envelope = Envelope()
        self._cc_envelope.task["original_input"] = user_input

        if intent_override and intent_override in self.model_router.list_strategies():
            self._cc_envelope.intent_class = intent_override
            self._cc_envelope.strategy_id = intent_override
            self._cc_envelope.task["_route_result"] = {
                "method": "claude_override", "confidence": 1.0,
                "reasoning": f"CC 直接指定: {intent_override}", "tokens_consumed": 0,
            }
        else:
            self.model_router.classify(self._cc_envelope, user_input)

        self._cc_envelope.context["refs"] = self._infer_context_refs(self._cc_envelope)
        self._cc_envelope = self.refiner.start(self._cc_envelope)

        if self._cc_envelope.strategy_id == "simple_query":
            self._cc_envelope = self.refiner.execute_spiral(self._cc_envelope)
            return {"phase": "complete", "deliverable": self._build_final_result(self._cc_envelope)}

        self._cc_envelope = self.on_before_spiral(self._cc_envelope)
        self._cc_envelope = self.refiner.execute_spiral(self._cc_envelope)

        plan = self._extract_execution_plan(self._cc_envelope)
        return {
            "phase": "execute",
            "execution_plan": plan,
            "envelope_summary": {
                "intent": self._cc_envelope.intent_class,
                "strategy": self._cc_envelope.strategy_id,
                "spiral_round": self._cc_envelope.spiral_iteration,
                "convergence_radius": self._cc_envelope.convergence_radius,
                "module_chain": [e["module"] for e in self.orchestrator.get_execution_log()],
            },
        }

    def continue_cc(self, execution_results: list[dict]) -> dict:
        """CC 交互模式 — 注入执行结果，继续下一轮螺旋。

        Args:
            execution_results: [{"subtask_id": "s1", "status": "success",
                                  "output_summary": "...", "artifacts": [...]}, ...]

        Returns:
            {"phase": "execute", "execution_plan": [...]} 或 {"phase": "complete", "deliverable": {...}}
        """
        self._apply_execution_results(self._cc_envelope, execution_results)

        # MemoryGuard: 追踪本轮用量
        est_tokens = sum(len(r.get("output_summary", "")) // 4 for r in execution_results)
        self.memory_guard.track_round(
            self._cc_envelope.spiral_iteration,
            est_tokens,
            len(execution_results),
        )
        # 压缩检查
        self.memory_guard.maybe_compress(self._cc_envelope)

        self._cc_envelope.feedback["accepted"] = True
        self._cc_envelope = self.on_after_spiral(self._cc_envelope)
        self._cc_envelope = self.refiner.refine(self._cc_envelope, {"signal": "accepted"})

        if not self._cc_envelope.should_continue_spiral:
            return {"phase": "complete", "deliverable": self._build_final_result(self._cc_envelope)}

        self._cc_envelope = self.on_before_spiral(self._cc_envelope)
        self._cc_envelope = self.refiner.execute_spiral(self._cc_envelope)

        plan = self._extract_execution_plan(self._cc_envelope)
        return {
            "phase": "execute",
            "execution_plan": plan,
            "envelope_summary": {
                "intent": self._cc_envelope.intent_class,
                "strategy": self._cc_envelope.strategy_id,
                "spiral_round": self._cc_envelope.spiral_iteration,
                "convergence_radius": self._cc_envelope.convergence_radius,
            },
        }

    def finish_cc(self) -> dict:
        """CC 交互模式 — 完成剩余螺旋轮次，返回最终结果。"""
        while self._cc_envelope.should_continue_spiral:
            self._cc_envelope.feedback["accepted"] = True
            self._cc_envelope = self.on_after_spiral(self._cc_envelope)
            self._cc_envelope = self.refiner.refine(self._cc_envelope, {"signal": "accepted"})
            if not self._cc_envelope.should_continue_spiral:
                break
            self._cc_envelope = self.on_before_spiral(self._cc_envelope)
            self._cc_envelope = self.refiner.execute_spiral(self._cc_envelope)
        return self._build_final_result(self._cc_envelope)

    def get_cc_state(self) -> dict | None:
        """获取当前 CC 交互会话的状态（用于持久化）。"""
        if not hasattr(self, '_cc_envelope') or self._cc_envelope is None:
            return None
        return {
            "intent": self._cc_envelope.intent_class,
            "strategy": self._cc_envelope.strategy_id,
            "spiral_round": self._cc_envelope.spiral_iteration,
            "convergence_radius": self._cc_envelope.convergence_radius,
            "task": self._cc_envelope.task,
        }

    # ── CC 模式内部方法 ──

    def _extract_execution_plan(self, envelope: Envelope) -> list[dict]:
        """从 envelope 中提取 CC 可执行的行动计划。"""
        subtasks = envelope.task.get("subtasks", [])
        plan = []
        for st in subtasks:
            item = {
                "subtask_id": st["id"],
                "entropy_stage": st.get("entropy_stage", ""),
                "description": st.get("description", st.get("goal", "")),
                "goal": st.get("goal", ""),
                "success_criteria": st.get("success_criteria", ""),
                "actions": st.get("actions", []),
                "quant_metric": st.get("quant_metric", {}),
                "dependencies": st.get("dependencies", []),
                "fallback_strategy": st.get("fallback_strategy", ""),
                "context_hint": {
                    "language": envelope.task.get("entities", {}).get("language"),
                    "framework": envelope.task.get("entities", {}).get("framework"),
                    "files": envelope.task.get("entities", {}).get("files_mentioned", []),
                },
            }
            plan.append(item)
        return plan

    def _apply_execution_results(self, envelope: Envelope,
                                   results: list[dict]) -> None:
        """将 CC 的执行结果注入 envelope。"""
        existing_log = envelope.task.get("gate_log", [])
        for r in results:
            sid = r.get("subtask_id", "")
            existing_log.append({
                "subtask_id": sid,
                "status": r.get("status", "success"),
                "executor": "claude_code",
                "output_summary": r.get("output_summary", "")[:500],
                "artifacts": r.get("artifacts", []),
            })
            # 同时注入 artifacts 供后续模块读取
            envelope.task.setdefault("_artifacts", []).append({
                "type": "cc_execution",
                "subtask": sid,
                "status": r.get("status"),
                "output_summary": r.get("output_summary", "")[:500],
            })
        envelope.task["gate_log"] = existing_log
        envelope.task["cc_results_applied"] = True

    def _build_final_result(self, envelope: Envelope) -> dict:
        """构建最终结果（复用 start() 的尾部逻辑）。"""
        # 强制 finalize
        if envelope.should_continue_spiral:
            convergence_summary = self.refiner.finalize(envelope)
        else:
            convergence_summary = {
                "convergence_speed": 0.0,
                "r_initial": envelope.convergence_radius,
                "r_final": envelope.convergence_radius,
                "total_spirals": envelope.spiral_iteration,
            }
        return {
            "deliverable": envelope.task.get("final_deliverable", {}),
            "convergence": convergence_summary,
            "spiral_iterations": envelope.spiral_iteration,
            "execution_log": self.orchestrator.get_execution_log(),
            "intent_class": envelope.intent_class,
            "strategy_id": envelope.strategy_id,
            "route_method": envelope.task.get("_route_result", {}).get("method", "unknown"),
            "memory_guard": self.memory_guard.get_usage_report(),
            "metrics": get_collector().get_snapshot(),
            "report_short": self.get_report_short(),
        }

    # ── 持久化 ──

    def save_state(self, slug: str) -> str:
        """保存当前 CC 交互会话到磁盘。"""
        state = self.get_cc_state()
        if state is None:
            raise RuntimeError("无活跃的 CC 交互会话")
        execution_results = self._cc_envelope.task.get("execution_results", [])
        return self.state_manager.save(slug, state, execution_results)

    def resume(self, slug: str) -> dict | None:
        """从磁盘恢复会话。返回已保存的状态摘要。"""
        data = self.state_manager.load(slug)
        if data is None:
            return None
        return {
            "slug": slug,
            "saved_at": data["master"].get("saved_at", ""),
            "intent": data["master"].get("intent", ""),
            "strategy": data["master"].get("strategy", ""),
            "spiral_round": data["master"].get("spiral_round", 0),
            "subtask_count": len(data.get("subtasks", [])),
        }

    def get_router_stats(self) -> dict:
        return self.model_router.get_stats()

    def get_report(self) -> str:
        """返回当前会话的人类可读执行报告。"""
        collector = get_collector()
        snapshot = collector.get_snapshot()
        report = HarnessReport(snapshot)
        return report.render()

    def get_report_short(self) -> str:
        """返回当前会话的单行摘要。"""
        collector = get_collector()
        snapshot = collector.get_snapshot()
        report = HarnessReport(snapshot)
        return report.render_short()
