"""
NegVerifyModule — 否定结论外部对照守门员（防困死内部天花板）

在 DeliverGated 之后运行，自动检测 final_deliverable 中的否定结论，
构造外部对照查询，写入 envelope.task['neg_verify_directive']。

CC 主进程在看到 interrupt_signal=RESEARCH_NEEDED 时会自动执行
外部研究，然后调用 neg_verify_integrate.py 整合结果。

闭环流程:
  DeliverGated → NegVerifyModule.prepare()
       ↓
  CC main process: 执行 WebSearch + WebFetch（按 external_queries）
       ↓
  Bash: python neg_verify_integrate.py --stdin
       ↓
  DeliverGated 读取 neg_verify.verdict 重新组装 deliverable
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope


# ── 否定类型识别 ──

NEGATIVE_TYPES = {
    "mathematical_impossibility",      # 数学证明的不可破
    "information_theoretic_barrier",   # 信息论下界
    "exhausted_search",                # 搜索空间穷尽
    "intrinsic_limit",                 # 物理/协议约束
    "correlation_zero",                # 经验相关性为零
    "no_path_found",                   # 无可行路径
    "no_solution",                     # 通用否
}


# ── 否定结论关键词模式（多语言 + 学术 + 工程） ──

NEGATIVE_PATTERNS = [
    # 中文
    re.compile(r"(不可破|不可解|不可能|无法解决|无解|天花板|穷尽|已?死|不存在|不成立|为零|关?闭了?)", re.IGNORECASE),
    re.compile(r"(找不到|没找到|没有(.*)方法|没(.*)办法)", re.IGNORECASE),
    re.compile(r"(已?证(明|实).*?(不可|无|不存在))", re.IGNORECASE),
    # 英文
    re.compile(r"(intrinsic|impossible|exhausted|barrier|ceiling|closed)", re.IGNORECASE),
    re.compile(r"(no\s+(known\s+)?(solution|path|method|way|approach))", re.IGNORECASE),
    re.compile(r"(cannot\s+be\s+(solved|resolved|achieved))", re.IGNORECASE),
    re.compile(r"(provably\s+(hard|secure|infeasible))", re.IGNORECASE),
    # 数学下界 / 复杂度
    re.compile(r"(lower\s+bound|下界|复杂度下界)", re.IGNORECASE),
    # 统计
    re.compile(r"(correlation\s*[=≈~]\s*0|r\s*=\s*0|p\s*>\s*0\.05|not\s+significant)", re.IGNORECASE),
]

# 黑名单：不触发的模式（typo / 语法错误 / 简单逻辑错误）
BLACKLIST_PATTERNS = [
    re.compile(r"(typo|语法错误|空指针|undefined|import error|syntax error|缩进)", re.IGNORECASE),
    re.compile(r"(index.*out.*of.*range|key.*error|type.*error)", re.IGNORECASE),
    re.compile(r"(forgot.*to.*add|missed.*a|plus\s*1|off.*by.*one)", re.IGNORECASE),
]

# 外部查询模板（中英双语 × 2 角度）
QUERY_TEMPLATES: dict[str, tuple[str, str]] = {
    "mathematical_impossibility": (
        "绕过 {claim_short} 的方法 侧信道 实现漏洞 重新定义 {domain}",
        "bypass {claim_short} side channel implementation vulnerability reformulation",
    ),
    "information_theoretic_barrier": (
        "侧信道 信息泄露 RNG状态 {domain} 实现缺陷 非标准用法",
        "side information leakage RNG state implementation flaw {domain}",
    ),
    "exhausted_search": (
        "替代参数化 重新定义 平移路径 {domain} 未被搜索的分支",
        "alternative parameterization reformulation {domain} unexplored branch",
    ),
    "correlation_zero": (
        "替代分解 不同基 傅里叶域 {domain} 正交不变量",
        "alternative decomposition different basis Fourier domain orthogonal invariants {domain}",
    ),
    "intrinsic_limit": (
        "out-of-band 实现特定 非标准用法 {domain} 旁路",
        "out-of-band implementation-specific non-standard {domain} bypass",
    ),
    "no_path_found": (
        "已知攻击路径 {domain} 方法综述 CVE",
        "known attacks methods survey {domain} CVE",
    ),
    "no_solution": (
        "已知解法 {domain} 最新进展",
        "known solutions {domain} latest advances",
    ),
}


# ── 配置 ──

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "default_level": "LITE",                       # LITE / MINI / FULL
    "max_lite_per_session": 10,
    "max_mini_per_session": 3,
    "max_full_per_session": 1,
    "disable_for_intents": ["simple_query"],       # code_fix 不过滤（仍可触发）
    "min_claim_length": 8,                         # 太短的"否"可能是噪声
    "max_detections": 5,                           # 一次最多处理 5 个否定
}


# ── 数据类 ──

@dataclass
class NegativeDetection:
    """单个否定结论检测。"""
    claim: str
    claim_type: str
    location: str                 # summary / section:xxx / known_gaps
    confidence: float = 0.7       # 模式匹配的置信度
    matched_pattern: str = ""


# ── 主模块 ──

class NegVerifyModule(ModuleBase):
    """否定结论外部对照准备模块。

    name = "deliver"
    variant = "neg_verify"
    """

    name = "deliver"
    variant = "neg_verify"

    def __init__(self, config: dict | None = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}

    # ── 主入口 ──

    def process(self, envelope: Envelope) -> ModuleResult:
        """检测否定结论 + 构造外部对照查询。"""

        # 1. 启用检查
        if not self.config.get("enabled", True):
            envelope.task["neg_verify_directive"] = {"triggered": False, "reason": "disabled_by_config"}
            return ModuleResult(envelope=envelope)

        # 2. 黑名单检查
        intent = envelope.intent_class or ""
        if intent in self.config.get("disable_for_intents", []):
            envelope.task["neg_verify_directive"] = {
                "triggered": False,
                "reason": f"intent_in_blacklist:{intent}",
            }
            return ModuleResult(envelope=envelope)

        # 3. 读取 deliverable
        final = envelope.task.get("final_deliverable")
        if not final:
            envelope.task["neg_verify_directive"] = {"triggered": False, "reason": "no_deliverable"}
            return ModuleResult(envelope=envelope)

        # 4. 检测否定结论
        detections = self._detect_negatives(final)
        max_det = self.config.get("max_detections", 5)
        detections = detections[:max_det]

        if not detections:
            envelope.task["neg_verify_directive"] = {
                "triggered": False,
                "reason": "no_negative_detected",
                "checked_locations": self._count_checked(final),
            }
            return ModuleResult(envelope=envelope)

        # 5. 构造 directive
        directive = self._build_directive(detections, final, envelope)

        envelope.task["neg_verify_directive"] = directive
        envelope.task["neg_verify_state"] = "PENDING_RESEARCH"

        return ModuleResult(envelope=envelope)

    # ── 检测 ──

    def _detect_negatives(self, deliverable: dict) -> list[NegativeDetection]:
        """扫描 deliverable 多个位置，提取否定结论。"""
        detections: list[NegativeDetection] = []
        min_len = self.config.get("min_claim_length", 10)

        # 位置 1: summary
        summary = deliverable.get("summary", "") or ""
        det = self._match_text(summary, "summary", min_len)
        if det:
            detections.append(det)

        # 位置 2: sections[].findings[]
        for section in deliverable.get("sections", []) or []:
            title = section.get("title", "")
            for finding in section.get("findings", []) or []:
                content = finding.get("content", "") if isinstance(finding, dict) else str(finding)
                det = self._match_text(content, f"section:{title}", min_len)
                if det and not self._is_dup(det, detections):
                    detections.append(det)

        # 位置 3: quality_self_assessment.known_gaps[]
        qsa = deliverable.get("quality_self_assessment", {}) or {}
        for gap in qsa.get("known_gaps", []) or []:
            det = self._match_text(str(gap), "known_gaps", min_len)
            if det and not self._is_dup(det, detections):
                detections.append(det)

        # 位置 4: self_check 字段
        sc = qsa.get("self_check", {}) or {}
        for field in ("failure_summary", "degraded_summary", "warnings"):
            for item in sc.get(field, []) or []:
                det = self._match_text(str(item), f"self_check.{field}", min_len)
                if det and not self._is_dup(det, detections):
                    detections.append(det)

        return detections

    @staticmethod
    def _match_text(text: str, location: str, min_len: int) -> NegativeDetection | None:
        """在单段文本中匹配否定结论。"""
        if not text or len(text.strip()) < min_len:
            return None

        # 黑名单优先
        if any(p.search(text) for p in BLACKLIST_PATTERNS):
            return None

        # 匹配否定模式
        for pattern in NEGATIVE_PATTERNS:
            m = pattern.search(text)
            if m:
                return NegativeDetection(
                    claim=text.strip(),
                    claim_type=NegVerifyModule._classify(text),
                    location=location,
                    confidence=0.8 if len(m.group(0)) > 4 else 0.6,
                    matched_pattern=m.group(0)[:60],
                )

        return None

    @staticmethod
    def _is_dup(det: NegativeDetection, existing: list[NegativeDetection]) -> bool:
        """去重：相同 claim 或相同 type + 相似位置。"""
        for e in existing:
            if det.claim[:80] == e.claim[:80]:
                return True
            if det.claim_type == e.claim_type and det.location.split(":")[0] == e.location.split(":")[0]:
                return True
        return False

    @staticmethod
    def _classify(text: str) -> str:
        """根据文本内容分类否定类型。"""
        t = text.lower()

        if any(k in t for k in ["下界", "lower bound", "np 完全", "证明", "theoretically"]):
            return "mathematical_impossibility"
        if any(k in t for k in ["信息论", "information.theoretic", "information-theoretic", "无偏置", "熵"]):
            return "information_theoretic_barrier"
        if any(k in t for k in ["穷尽", "exhausted", "all.negative", "all zero", "搜索空间"]):
            return "exhausted_search"
        if any(k in t for k in ["correlation", "r=0", "r ≈ 0", "相关系数", "pearson"]):
            return "correlation_zero"
        if any(k in t for k in ["intrinsic", "天花板", "ceiling", "物理约束", "硬件"]):
            return "intrinsic_limit"
        if any(k in t for k in ["no.path", "no.method", "no.solution"]):
            return "no_path_found"

        return "no_solution"

    # ── 构造 directive ──

    def _build_directive(self, detections: list[NegativeDetection],
                          deliverable: dict, envelope: Envelope) -> dict:
        """构造外部对照指令。"""

        primary = detections[0]
        level = self.config.get("default_level", "LITE")
        domain = self._extract_domain(deliverable, primary.claim)

        # 生成查询（中英各 1 角度 = LITE；中英各 2 角度 = MINI；3+ = FULL）
        queries = self._generate_queries(primary, domain, level)

        # 提取内部已尝试方法（避免外部重复推荐）
        internal_attempts = self._extract_internal_attempts(deliverable)

        return {
            "triggered": True,
            "level": level,
            "interrupt_signal": "RESEARCH_NEEDED",
            "claim_type": primary.claim_type,
            "primary_claim": primary.claim,
            "primary_location": primary.location,
            "all_detections": [
                {
                    "claim": d.claim[:200],
                    "type": d.claim_type,
                    "location": d.location,
                    "confidence": d.confidence,
                }
                for d in detections
            ],
            "external_queries": queries,
            "domain": domain,
            "internal_attempts": internal_attempts,
            "config": {
                "max_results_per_query": {"LITE": 3, "MINI": 5, "FULL": 6}.get(level, 3),
                "max_fetches": {"LITE": 2, "MINI": 5, "FULL": 10}.get(level, 2),
                "require_3_vote_verify": level == "FULL",
            },
            "next_action": (
                "CC main process: 执行 external_queries 中的 WebSearch，"
                "对 top 结果执行 WebFetch（按 config.max_fetches 限制），"
                "然后调用 `python agent_harness/modules/deliver/neg_verify_integrate.py --stdin`"
                " 整合结果到 envelope.task['neg_verify']"
            ),
            "session_counter": envelope.task.get("neg_verify_session_count", 0) + 1,
        }

    def _generate_queries(self, det: NegativeDetection, domain: str, level: str) -> list[str]:
        """按档位生成查询数量。"""
        templates = QUERY_TEMPLATES.get(det.claim_type, QUERY_TEMPLATES["no_solution"])
        claim_short = det.claim[:80].replace("\n", " ")

        queries = []
        for tpl in templates:
            queries.append(tpl.format(claim_short=claim_short, domain=domain))

        # MINI/FULL 增加反方角度
        if level in ("MINI", "FULL"):
            queries.append(
                f"已知 {domain} 攻击方法 综述 CVE 漏洞"
            )

        return queries

    def _extract_internal_attempts(self, deliverable: dict) -> list[str]:
        """提取内部已尝试的方法（避免外部重复推荐）。"""
        attempts = set()

        # 从 sections 提取
        for section in deliverable.get("sections", []) or []:
            title = section.get("title", "")
            if title:
                attempts.add(title[:100])

        # 从 known_gaps 提取
        qsa = deliverable.get("quality_self_assessment", {}) or {}
        for gap in qsa.get("known_gaps", []) or []:
            attempts.add(str(gap)[:100])

        return sorted(attempts)[:10]

    def _extract_domain(self, deliverable: dict, claim: str) -> str:
        """推断领域关键词。"""
        text = (claim + " " + str(deliverable.get("summary", ""))).lower()

        domain_keywords = [
            ("algorithm", ["algorithm", "算法", "复杂度", "complexity", "性能"]),
            ("data", ["data", "数据", "数据集", "dataset", "清洗"]),
            ("model", ["model", "模型", "训练", "training", "inference", "推理"]),
            ("implementation", ["implementation", "实现", "代码", "code", "架构"]),
            ("protocol", ["protocol", "协议", "标准", "standard", "接口", "api"]),
        ]

        for label, kws in domain_keywords:
            if any(k in text for k in kws):
                return label

        return "general"

    @staticmethod
    def _count_checked(deliverable: dict) -> int:
        """统计被检查的位置数（用于 verbose 日志）。"""
        count = 1 if deliverable.get("summary") else 0
        count += len(deliverable.get("sections", []) or [])
        qsa = deliverable.get("quality_self_assessment", {}) or {}
        count += len(qsa.get("known_gaps", []) or [])
        return count


# ── 便捷函数 ──

def get_neg_verify_module(config: dict | None = None) -> NegVerifyModule:
    return NegVerifyModule(config=config)