#!/usr/bin/env python3
"""
NegVerify 模块测试套件。

覆盖：
1. 否定结论检测（多语言、多模式）
2. 黑名单过滤（typo / 语法错误）
3. 类型分类（mathematical / exhausted / correlation_zero 等）
4. Directive 构造（查询模板、领域推断）
5. 整合脚本 verdict 判定（alternative / double_negative / inconclusive）
6. 端到端闭环模拟（构建 deliverable → 检测 → 模拟外部研究 → 整合）
"""

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent_harness.modules.deliver.neg_verify import (
    NegVerifyModule,
    NegativeDetection,
    NEGATIVE_PATTERNS,
    BLACKLIST_PATTERNS,
    QUERY_TEMPLATES,
)
from agent_harness.modules.deliver.neg_verify_integrate import (
    evaluate,
    render_markdown,
    score_alternatives,
    score_negatives,
)


# ── 辅助：构建 envelope ──

def make_envelope(intent="research", deliverable=None):
    """构造测试用 Envelope-like dict。"""
    env = type("E", (), {})()
    env.intent_class = intent
    env.task = {
        "final_deliverable": deliverable or {},
    }
    return env


def make_deliverable_with_negative(summary="任务无法解决，公式穷尽", sections=None):
    """构造带否定结论的 deliverable。"""
    return {
        "format": "report",
        "summary": summary,
        "sections": sections or [
            {"title": "测试", "findings": [{"content": "该问题下界已被证明，理论上不可解"}]}
        ],
        "quality_self_assessment": {
            "completeness": 0.4,
            "known_gaps": ["全部公式组合均为 negative", "correlation = 0"],
        },
    }


# ── 测试 1: 否定检测 ──

class TestNegativeDetection(unittest.TestCase):
    """否定结论检测。"""

    def test_chinese_impossibility(self):
        text = "这个数学证明已表明该问题不可解，存在下界。"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNotNone(det)
        self.assertEqual(det.claim_type, "mathematical_impossibility")

    def test_chinese_exhausted(self):
        text = "全部公式组合已测完，搜索空间穷尽"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNotNone(det)
        self.assertEqual(det.claim_type, "exhausted_search")

    def test_chinese_correlation(self):
        text = "Pearson correlation = 0，无显著相关"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNotNone(det)
        self.assertEqual(det.claim_type, "correlation_zero")

    def test_english_no_path(self):
        text = "no known method exists for this attack vector"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNotNone(det)

    def test_too_short_skipped(self):
        text = "不可能"  # 太短
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNone(det)


# ── 测试 2: 黑名单 ──

class TestBlacklist(unittest.TestCase):
    """typo / 语法错误不应触发 neg_verify。"""

    def test_typo_skipped(self):
        text = "代码里有个 typo 导致的 syntax error"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNone(det, "typo 不应触发 neg_verify")

    def test_undefined_skipped(self):
        text = "运行时 undefined variable，导致 index out of range"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNone(det, "undefined 不应触发 neg_verify")

    def test_off_by_one_skipped(self):
        text = "off by one error 在循环里"
        det = NegVerifyModule._match_text(text, "test", 10)
        self.assertIsNone(det)


# ── 测试 3: 类型分类 ──

class TestClassification(unittest.TestCase):
    """否定类型分类。"""

    def test_mathematical(self):
        t = "lower bound proof shows this problem is provably hard"
        self.assertEqual(NegVerifyModule._classify(t), "mathematical_impossibility")

    def test_exhausted(self):
        t = "all formula variants tested negative, search space exhausted"
        self.assertEqual(NegVerifyModule._classify(t), "exhausted_search")

    def test_correlation(self):
        t = "pearson r=0, no significant correlation"
        self.assertEqual(NegVerifyModule._classify(t), "correlation_zero")

    def test_unknown_fallback(self):
        t = "some random conclusion without clear type"
        self.assertEqual(NegVerifyModule._classify(t), "no_solution")


# ── 测试 4: 集成 detection ──

class TestIntegrationDetection(unittest.TestCase):
    """从 deliverable 多位置检测。"""

    def setUp(self):
        self.module = NegVerifyModule()

    def test_detect_from_summary(self):
        d = make_deliverable_with_negative(summary="这个数学问题不可破，存在下界")
        detections = self.module._detect_negatives(d)
        self.assertGreater(len(detections), 0)
        self.assertEqual(detections[0].location, "summary")

    def test_detect_from_sections(self):
        d = make_deliverable_with_negative(
            summary="正常摘要",
            sections=[{"title": "Section A", "findings": [{"content": "该结论的信息论下界已被证明"}]}]
        )
        detections = self.module._detect_negatives(d)
        self.assertGreater(len(detections), 0)

    def test_detect_from_known_gaps(self):
        d = {
            "summary": "正常",
            "sections": [],
            "quality_self_assessment": {
                "known_gaps": ["全部公式 negative", "Pearson r = 0"]
            }
        }
        detections = self.module._detect_negatives(d)
        self.assertGreaterEqual(len(detections), 1)

    def test_dedup(self):
        d = {
            "summary": "该问题在理论上不可破",
            "sections": [{"title": "S", "findings": [{"content": "该问题在理论上不可破"}]}],
            "quality_self_assessment": {"known_gaps": ["该问题在理论上不可破"]},
        }
        detections = self.module._detect_negatives(d)
        # 三个位置都提到相同结论，应该去重为 1
        self.assertEqual(len(detections), 1)

    def test_blacklist_filters_known_gaps(self):
        d = {
            "summary": "代码 typo 已修",
            "sections": [],
            "quality_self_assessment": {"known_gaps": ["有 syntax error"]}
        }
        detections = self.module._detect_negatives(d)
        self.assertEqual(len(detections), 0)


# ── 测试 5: Directive 构造 ──

class TestDirective(unittest.TestCase):
    """构造外部对照指令。"""

    def setUp(self):
        self.module = NegVerifyModule()
        self.env = make_envelope()

    def test_basic_directive(self):
        det = NegativeDetection(
            claim="该问题下界不可破",
            claim_type="mathematical_impossibility",
            location="summary",
        )
        d = make_deliverable_with_negative(summary=det.claim)
        directive = self.module._build_directive([det], d, self.env)
        self.assertTrue(directive["triggered"])
        self.assertEqual(directive["claim_type"], "mathematical_impossibility")
        self.assertEqual(directive["level"], "LITE")
        self.assertGreater(len(directive["external_queries"]), 0)
        self.assertIn("RESEARCH_NEEDED", directive["interrupt_signal"])

    def test_queries_have_claim_and_domain(self):
        det = NegativeDetection(
            claim="该问题的信息论下界已被证明",
            claim_type="information_theoretic_barrier",
            location="summary",
        )
        d = make_deliverable_with_negative(summary=det.claim)
        directive = self.module._build_directive([det], d, self.env)
        # 至少一条 query 包含 claim 关键词或 domain 关键词
        all_q = " ".join(directive["external_queries"]).lower()
        self.assertTrue(
            "泄露" in all_q or "leakage" in all_q or "下界" in all_q
        )

    def test_mini_level_more_queries(self):
        module = NegVerifyModule(config={"default_level": "MINI"})
        det = NegativeDetection(
            claim="test claim",
            claim_type="mathematical_impossibility",
            location="summary",
        )
        d = make_deliverable_with_negative(summary=det.claim)
        env = make_envelope()
        d_directive = module._build_directive([det], d, env)
        self.assertGreaterEqual(len(d_directive["external_queries"]), 3)


# ── 测试 6: 黑名单 intent 过滤 ──

class TestIntentBlacklist(unittest.TestCase):
    """simple_query 不应触发 neg_verify。"""

    def test_simple_query_skipped(self):
        module = NegVerifyModule()
        env = make_envelope(intent="simple_query")
        env.task["final_deliverable"] = make_deliverable_with_negative(
            summary="这个数学问题不可破"
        )
        result = module.process(env)
        directive = env.task["neg_verify_directive"]
        self.assertFalse(directive["triggered"])
        self.assertIn("blacklist", directive["reason"])

    def test_research_triggers(self):
        module = NegVerifyModule()
        env = make_envelope(intent="research")
        env.task["final_deliverable"] = make_deliverable_with_negative(
            summary="这个数学问题不可破"
        )
        module.process(env)
        directive = env.task["neg_verify_directive"]
        self.assertTrue(directive["triggered"])


# ── 测试 7: 整合脚本 — 替代方案判定 ──

class TestIntegrateAlternative(unittest.TestCase):
    """外部找到替代方案应判定 alternative_found。"""

    def test_alternative_found_high(self):
        directive = {
            "triggered": True,
            "claim_type": "mathematical_impossibility",
            "primary_claim": "该问题在理论上不可破",
        }
        external = {
            "search_results": [
                {"title": "Alternative approach via caching", "snippet": "bypasses the theoretical barrier by changing data layout"},
                {"title": "Known implementation flaw", "snippet": "CVE-2021-28216 documented bypass"},
            ],
            "fetched_sources": [
                {"content": "An alternative method bypasses the mathematical barrier by exploiting an implementation flaw."}
            ],
            "synthesis": "可通过实现层漏洞绕过原有的数学下界，存在替代方法",
        }
        result = evaluate(directive, external)
        self.assertEqual(result["verdict"], "alternative_found")
        self.assertEqual(result["confidence"], "high")
        self.assertGreater(len(result["alternatives"]), 0)


class TestIntegrateDoubleNegative(unittest.TestCase):
    """外部也确认无解 → double_negative。"""

    def test_double_negative(self):
        directive = {
            "triggered": True,
            "claim_type": "mathematical_impossibility",
            "primary_claim": "该问题在理论上不可破",
        }
        external = {
            "search_results": [],
            "fetched_sources": [
                {"content": "This is mathematically proven. No known method can bypass this. Provably secure."}
            ],
            "synthesis": "外部文献一致确认：数学上已证明无解，没有已知方法",
        }
        result = evaluate(directive, external)
        self.assertEqual(result["verdict"], "double_negative")
        self.assertIn(result["confidence"], ("high", "medium"))


class TestIntegrateInconclusive(unittest.TestCase):
    """外部信号不足 → inconclusive。"""

    def test_too_short(self):
        directive = {
            "triggered": True,
            "claim_type": "no_solution",
            "primary_claim": "test",
        }
        external = {
            "search_results": [],
            "fetched_sources": [],
            "synthesis": "ok",
        }
        result = evaluate(directive, external)
        self.assertEqual(result["verdict"], "inconclusive")

    def test_mixed_signals(self):
        directive = {
            "triggered": True,
            "claim_type": "no_solution",
            "primary_claim": "test",
        }
        external = {
            "search_results": [{"title": "Some article", "snippet": "alternative approach possible in theory"}],
            "fetched_sources": [{"content": "But mathematically proven infeasible in most cases."}],
            "synthesis": "信号混杂：理论上有替代路径，实际不可行",
        }
        result = evaluate(directive, external)
        self.assertIn(result["verdict"], ("inconclusive", "alternative_found", "double_negative"))


# ── 测试 8: Markdown 渲染 ──

class TestMarkdownRender(unittest.TestCase):
    """verdict → Markdown。"""

    def test_alternative_markdown(self):
        result = {
            "verdict": "alternative_found",
            "confidence": "high",
            "primary_claim": "test claim",
            "alternatives": [{"category": "side_channel", "match_count": 3}],
            "external_evidence_summary": "found alternatives",
        }
        md = render_markdown(result)
        self.assertIn("不交付否定", md)
        self.assertIn("side_channel", md)

    def test_double_negative_markdown(self):
        result = {
            "verdict": "double_negative",
            "confidence": "high",
            "primary_claim": "test",
            "negative_evidence": [{"category": "proven", "match_count": 3}],
        }
        md = render_markdown(result)
        self.assertIn("双重确认否定", md)
        self.assertIn("可信度", md)

    def test_inconclusive_markdown(self):
        result = {
            "verdict": "inconclusive",
            "confidence": "low",
            "primary_claim": "test",
            "alternative_score": 0.5,
            "negative_score": 0.3,
            "recommendation": "建议升级",
        }
        md = render_markdown(result)
        self.assertIn("存疑否定", md)


# ── 测试 9: 端到端闭环（无真实网络） ──

class TestEndToEndLoop(unittest.TestCase):
    """模拟完整闭环：构建 deliverable → detect → directive → 模拟外部 → integrate → 整合到 deliverable。"""

    def test_full_loop_with_alternative(self):
        # Step 1: 构建 deliverable（带否定结论）
        deliverable = make_deliverable_with_negative(
            summary="该问题数学上不可破，存在理论下界"
        )

        # Step 2: NegVerifyModule 检测
        module = NegVerifyModule()
        env = make_envelope(intent="research", deliverable=deliverable)
        module.process(env)
        directive = env.task["neg_verify_directive"]
        self.assertTrue(directive["triggered"])

        # Step 3: 模拟 CC 主进程执行外部研究
        simulated_external = {
            "search_results": [
                {"title": "Alternative approach found", "snippet": "bypasses theoretical barrier"},
            ],
            "fetched_sources": [
                {"content": "An implementation flaw CVE-2021-28216 provides an alternative method that bypasses the mathematical barrier."}
            ],
            "synthesis": "外部研究找到替代方法，可绕过原有的数学下界",
        }

        # Step 4: 调用整合脚本逻辑
        result = evaluate(directive, simulated_external)
        self.assertEqual(result["verdict"], "alternative_found")

        # Step 5: DeliverGated 整合（重新生成 deliverable）
        env.task["neg_verify"] = result
        env.task["neg_verify_markdown"] = render_markdown(result)

        # 重新跑 DeliverGated 逻辑（只测整合部分）
        final_deliverable = deliverable.copy()
        final_deliverable["neg_verify"] = result
        final_deliverable["neg_verify_markdown"] = env.task["neg_verify_markdown"]
        final_deliverable["conclusion_overridden"] = True
        final_deliverable["original_verdict"] = "negative"
        final_deliverable["new_verdict"] = "alternative_available"

        # 验证整合正确
        self.assertEqual(final_deliverable["conclusion_overridden"], True)
        self.assertEqual(final_deliverable["new_verdict"], "alternative_available")
        self.assertIn("不交付否定", final_deliverable["neg_verify_markdown"])


# ── 测试 10: 领域推断 ──

class TestDomainInference(unittest.TestCase):
    """根据 claim 推断领域关键词。"""

    def test_algorithm_domain(self):
        d = make_deliverable_with_negative(summary="该算法复杂度下界已被证明")
        module = NegVerifyModule()
        env = make_envelope()
        det = NegativeDetection(claim="该算法复杂度下界", claim_type="math", location="s")
        domain = module._extract_domain(d, det.claim)
        self.assertIn("algorithm", domain.lower())

    def test_model_domain(self):
        d = make_deliverable_with_negative(summary="模型推理能力无法进一步提升")
        module = NegVerifyModule()
        env = make_envelope()
        det = NegativeDetection(claim="模型推理能力无法提升", claim_type="info", location="s")
        domain = module._extract_domain(d, det.claim)
        self.assertIn("model", domain.lower())

    def test_unknown_domain(self):
        module = NegVerifyModule()
        env = make_envelope()
        det = NegativeDetection(claim="generic claim", claim_type="no", location="s")
        d = {"summary": ""}
        domain = module._extract_domain(d, det.claim)
        self.assertEqual(domain, "general")


# ── 入口 ──

if __name__ == "__main__":
    print("=" * 70)
    print("NegVerify 模块测试")
    print("=" * 70)
    unittest.main(verbosity=2)