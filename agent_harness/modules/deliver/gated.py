"""
DeliverGated — 带6项自检的交付模块。

在交付前执行：
- 6项自检（量化可比较/依赖完整/上限合理/降级覆盖/代价合理/类型一致）
- 代价预估（token/时间/风险等级）
- 质量自评（完整性/已知缺口/风险提示）
- 自动选择 diff_patch 或 report 格式
- **集成 neg_verify**: 检测到否定结论时标记 RESEARCH_NEEDED，CC 主进程执行外部研究后再回来整合
"""

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope
from agent_harness.core.deduction_engine import get_deduction_engine


class DeliverGated(ModuleBase):
    """门检交付 — 6项自检 + 代价预估 + 质量自评 + neg_verify 集成。

    统一入口，根据意图自动选择 diff_patch 或 report 格式。
    替代 DeliverDiff / DeliverReport。
    """

    name = "deliver"
    variant = "gated"

    def __init__(self):
        self._engine = get_deduction_engine()

    def process(self, envelope: Envelope) -> ModuleResult:
        results = envelope.task.get("execution_results", [])
        subtasks = envelope.task.get("subtasks", [])
        intent = envelope.intent_class or ""
        gate_log = envelope.task.get("gate_log", [])
        degradation_total = envelope.task.get("degradation_total", 0)

        # 汇总 artifacts
        artifacts = []
        for r in results:
            for a in r.get("artifacts", []):
                artifacts.append(a)

        # 计算预估 token
        estimated_tokens = sum(
            st.get("estimated_tokens", 5000) for st in subtasks
        )

        # 6项自检
        self_check = self._engine.run_self_check(
            subtasks=subtasks,
            execution_results=results,
            intent_class=intent,
            estimated_tokens=estimated_tokens,
        )

        # 确定交付格式
        is_code_task = intent in ("code_feature", "code_fix", "refactor")
        delivery_format = "diff_patch" if is_code_task else "report"

        # 构建交付物
        sections = []
        for r in results:
            st = next((s for s in subtasks if s["id"] == r.get("subtask_id")), None)
            sections.append({
                "title": st["description"] if st else r.get("subtask_id", ""),
                "entropy_stage": st.get("entropy_stage", "") if st else "",
                "status": r.get("status", "unknown"),
                "fallback_applied": r.get("fallback_applied"),
                "findings": r.get("artifacts", []),
            })

        # 门检摘要
        gate_summary = {
            "total_gates": len(gate_log),
            "passed": sum(1 for g in gate_log if g.get("status") == "success"),
            "degraded": sum(1 for g in gate_log if g.get("status") == "DEGRADED"),
            "degradation_streak_total": degradation_total,
        }

        # 质量自评
        all_success = all(r.get("status") == "success" for r in results)
        has_degradations = any(r.get("status") == "degraded" for r in results)

        deliverable = {
            "format": delivery_format,
            "summary": (
                f"执行了 {len(results)} 个子任务"
                f"{'（含' + str(gate_summary['degraded']) + '个降级）' if has_degradations else ''}"
                f"，产出 {len(artifacts)} 个变更"
            ),
            "artifacts": artifacts,
            "sections": sections,
            "quality_self_assessment": {
                "completeness": (
                    1.0 if all_success
                    else 0.7 if not has_degradations
                    else 0.4
                ),
                "known_gaps": self._identify_gaps(subtasks, results, gate_log),
                "self_check": self_check,
            },
            "cost_estimate": {
                "estimated_tokens": estimated_tokens,
                "estimated_time_ms": estimated_tokens * 5,
                "risk_level": self_check.get("estimated_risk", "unknown"),
                "degradation_events": degradation_total,
            },
            "gate_summary": gate_summary,
        }

        # ── 整合 neg_verify 结果（如果已执行） ──
        neg_verify = envelope.task.get("neg_verify")
        if neg_verify and neg_verify.get("verdict"):
            deliverable["neg_verify"] = neg_verify
            deliverable["neg_verify_markdown"] = envelope.task.get(
                "neg_verify_markdown", ""
            )

            # 关键：若 verdict == "alternative_found"，覆盖原结论标记
            if neg_verify["verdict"] == "alternative_found":
                deliverable["conclusion_overridden"] = True
                deliverable["original_verdict"] = "negative"
                deliverable["new_verdict"] = "alternative_available"

        envelope.task["final_deliverable"] = deliverable
        return ModuleResult(envelope=envelope)

    @staticmethod
    def _identify_gaps(subtasks: list, results: list,
                        gate_log: list) -> list[str]:
        """识别交付物中的已知缺口。"""
        gaps = []

        # 降级的子任务
        for r in results:
            if r.get("status") == "degraded":
                gaps.append(
                    f"子任务 {r['subtask_id']} 降级: {r.get('fallback_applied', '未知降级策略')}"
                )

        # 门检失败的阶段
        for g in gate_log:
            if g.get("status") == "DEGRADED":
                failed_gates = [
                    gate["name"] for gate in g.get("gates", [])
                    if not gate.get("passed", False)
                ]
                gaps.append(
                    f"子任务 {g['subtask_id']} 门检失败: {', '.join(failed_gates)}"
                )

        # 缺失的熵减阶段
        executed_stages = {
            st.get("entropy_stage", "") for st in subtasks
            if any(r.get("subtask_id") == st.get("id") for r in results)
        }
        for st in subtasks:
            stage = st.get("entropy_stage", "")
            if stage and stage not in executed_stages:
                gaps.append(f"熵减阶段 '{stage}' 未执行")

        return gaps[:5]  # 最多5条
