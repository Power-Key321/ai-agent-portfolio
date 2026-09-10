"""
ModelRouter — 模型驱动的意图路由（升级自纯正则Router）。

设计:
  正则冷启动（0 token, 即时） → 低置信度fallback → 模型路由（~500 token）
  → 模型结果学习为新正则 → 下次同类查询命中正则 → 逐步减少模型调用

与PromptBuilder配合:
  模型路由的prompt通过PromptBuilder构建 → 框架骨架命中缓存 → 只有动态区按量付费
  → 每次模型路由的实际成本仅~50 token（90%缓存命中节省）
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from agent_harness.core.envelope import Envelope
from agent_harness.core.prompt_builder import PromptBuilder, get_prompt_builder

# 轻量级原子读写（避免循环导入 auto_attach）
def _atomic_read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}" if hasattr(os, 'getpid') else ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


@dataclass
class RouteResult:
    """路由结果 — 包含意图分类+置信度+路由方式。"""
    intent_class: str
    confidence: float        # 0.0 ~ 1.0
    method: str              # "regex" | "model" | "learned_regex"
    model_used: str | None   # 如果用了模型，模型名
    tokens_consumed: int     # 本次路由消耗token
    reasoning: str           # 分类理由


@dataclass
class ModelRouter:
    """模型驱动的意图路由器。

    三层路由策略:
    1. 完全匹配 → instant, 0 token
    2. 正则匹配 → instant, 0 token
    3. 模型调用 → ~500 token (但框架骨架命中缓存, 实际增量仅~50 token)

    学习机制:
    模型分类结果 → 自动提取关键词 → 注册为新正则 → 下次零token命中
    """

    # 注入的模型调用回调 (由Adapter提供)
    on_model_call: Callable[[str, str], str] | None = None

    # 内置正则Router (冷启动fallback)
    from agent_harness.core.router import Router
    _regex_router: Router = field(default_factory=Router, init=False)

    # 学习到的正则（从模型分类结果中提取）
    _learned_patterns: dict[str, list[str]] = field(default_factory=dict, init=False)

    # 统计
    total_classifications: int = 0
    regex_hits: int = 0
    model_calls: int = 0
    learned_hits: int = 0
    total_tokens_saved: int = 0

    # 置信度阈值
    regex_confidence_threshold: float = 0.45   # 正则置信度低于此值 → fallback到模型
    model_min_confidence: float = 0.7          # 模型结果低于此值 → 标记为不确定

    # PromptBuilder（保证模型调用时框架骨架命中缓存）
    prompt_builder: PromptBuilder | None = None

    def __post_init__(self):
        self._regex_router.load_strategies()
        self.prompt_builder = get_prompt_builder()
        self._learned_patterns = self._load_learned_patterns()
        if not self._learned_patterns:
            self._learned_patterns = {s: [] for s in self._regex_router.list_strategies()}
        # 确保新策略也有条目
        for s in self._regex_router.list_strategies():
            if s not in self._learned_patterns:
                self._learned_patterns[s] = []

    # ── 主入口 ──

    def classify(self, envelope: Envelope, user_input: str) -> RouteResult:
        """对用户输入进行意图分类。三层fallback。"""
        self.total_classifications += 1
        text = user_input
        text_lower = text.lower()

        # Layer 1: 学习到的正则（0 token，来自之前的模型分类）
        result = self._try_learned_patterns(text_lower)
        if result and result.confidence >= self.regex_confidence_threshold:
            self.learned_hits += 1
            self._count_saved_tokens(500)  # 省了一次模型调用
            envelope = self._apply_result(envelope, result)
            return result

        # Layer 2: 内置正则（0 token，冷启动规则）
        matched_id, raw_conf = self._regex_router._match_intent(text)
        if raw_conf > 0:
            # 有实际匹配：提升置信度（正则模式有区分度，但不如模型语义理解）
            regex_conf = min(0.50 + raw_conf, 0.90)
        else:
            # 无匹配：置信度为0，强制fallback到模型
            regex_conf = 0.0
            matched_id = "simple_query"  # fallback intent if model also fails
        if regex_conf >= self.regex_confidence_threshold:
            self.regex_hits += 1
            result = RouteResult(
                intent_class=matched_id,
                confidence=regex_conf,
                method="regex",
                model_used=None,
                tokens_consumed=0,
                reasoning=f"内置正则匹配: confidence={regex_conf:.2f}",
            )
            envelope = self._apply_result(envelope, result)
            return result

        # Layer 3: 模型路由（~500 token，但框架骨架缓存命中 = 实际~50 token增量）
        self.model_calls += 1
        result = self._model_classify(user_input, matched_id, regex_conf)
        if result:
            # 学习：将模型结果注册为新正则
            self._learn_from_model(user_input, result.intent_class)
            envelope = self._apply_result(envelope, result)

        # Fallback: 用正则的best guess
        if result is None:
            self.regex_hits += 1
            result = RouteResult(
                intent_class=matched_id,
                confidence=regex_conf,
                method="regex",
                model_used=None,
                tokens_consumed=0,
                reasoning=f"模型调用失败, fallback到正则: {matched_id}",
            )

        envelope = self._apply_result(envelope, result)
        return result

    # ── 模型路由 ──

    def _model_classify(
        self, user_input: str, regex_best: str, regex_conf: float
    ) -> Optional[RouteResult]:
        """调用模型进行意图分类。

        使用PromptBuilder构建prompt → 框架骨架命中缓存 → 成本极低。
        """
        if self.on_model_call is None:
            return None

        pb = self.prompt_builder
        prompt_data = pb.build(
            user_input=user_input,
            state={"regex_best_guess": regex_best, "regex_confidence": regex_conf},
            task_type="classify",
        )

        try:
            model_output = self.on_model_call(prompt_data["prompt"], prompt_data["skeleton_hash"])
            intent = self._parse_model_output(model_output)

            if intent in self._regex_router.list_strategies():
                return RouteResult(
                    intent_class=intent,
                    confidence=0.85,
                    method="model",
                    model_used="claude",
                    tokens_consumed=prompt_data["dynamic_tokens"],
                    reasoning=f"模型分类: {intent} (正则best={regex_best}, conf={regex_conf:.2f})",
                )
        except Exception:
            pass

        return None

    def _parse_model_output(self, output: str) -> str:
        """从模型输出中提取意图类别。"""
        valid = set(self._regex_router.list_strategies())
        output_lower = output.strip().lower()
        for intent in valid:
            if intent in output_lower:
                return intent
        return output_lower.split("\n")[0].strip()

    # ── 学习机制 ──

    def _learn_from_model(self, user_input: str, intent: str) -> None:
        """从模型分类结果中提取关键词，注册为新正则。"""
        keywords = self._extract_keywords(user_input)
        for kw in keywords:
            if kw not in self._learned_patterns.get(intent, []):
                self._learned_patterns.setdefault(intent, []).append(kw)
        # 持久化到磁盘（多窗口共享学习成果）
        self._persist_learned_patterns()

    def _extract_keywords(self, text: str) -> list[str]:
        """从用户输入中提取有区分度的关键词。"""
        # 移除常见停用词
        stopwords = {"帮我", "一个", "一下", "这个", "那个", "的", "了", "是", "在", "和", "请"}
        words = []
        # 简单分词: 按常见分隔符切
        for part in re.split(r'[，。！？\s,!.?;；、]', text):
            part = part.strip()
            if len(part) >= 2 and part not in stopwords:
                words.append(part)
        # 返回最长的2-3个（最有区分度）
        return sorted(words, key=len, reverse=True)[:3]

    def _try_learned_patterns(self, text_lower: str) -> Optional[RouteResult]:
        """尝试匹配学习到的正则。

        学习到的正则来自模型分类结果，可靠性远高于手写正则，
        因此使用更宽松的阈值和更高的基础置信度。
        """
        best, best_score, best_pattern = None, 0.0, None
        for intent, patterns in self._learned_patterns.items():
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    # 学习到的关键词: 基础分0.80, 长度加成
                    score = 0.80 + min(len(pattern) / 100, 0.15)
                    if score > best_score:
                        best = intent
                        best_score = score
                        best_pattern = pattern
        # 学习模式用更低的阈值 (0.50), 因为它们是模型验证过的
        if best and best_score >= 0.50:
            return RouteResult(
                intent_class=best,
                confidence=best_score,
                method="learned_regex",
                model_used=None,
                tokens_consumed=0,
                reasoning=f"学习到的正则匹配: '{best_pattern}' → {best} (confidence={best_score:.2f})",
            )
        return None

    # ── 辅助方法 ──

    def _apply_result(self, envelope: Envelope, result: RouteResult) -> Envelope:
        """将路由结果写入 Envelope。"""
        envelope.intent_class = result.intent_class
        envelope.strategy_id = result.intent_class
        envelope.task["_route_result"] = {
            "method": result.method,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "tokens_consumed": result.tokens_consumed,
        }
        return envelope

    def _count_saved_tokens(self, tokens: int) -> None:
        self.total_tokens_saved += tokens

    # ── 学习模式持久化（平移支持） ──

    def _learned_patterns_path(self) -> Path:
        """学习模式存储路径。

        默认落在包内 feedback/；环境变量 AGENT_HARNESS_STATE_DIR 可覆盖，
        让测试与多环境部署把状态写进隔离目录，避免彼此污染。
        """
        root = os.environ.get("AGENT_HARNESS_STATE_DIR")
        base = Path(root) if root else Path(__file__).resolve().parent.parent / "feedback"
        return base / "learned_patterns.json"

    def _persist_learned_patterns(self) -> None:
        """持久化学习模式到磁盘（原子写入，多窗口安全）。"""
        try:
            path = self._learned_patterns_path()
            # 合并已有数据
            existing = _atomic_read_json(path) or {}
            for intent, patterns in self._learned_patterns.items():
                if intent not in existing:
                    existing[intent] = []
                for p in patterns:
                    if p not in existing[intent]:
                        existing[intent].append(p)
                existing[intent] = existing[intent][-50:]
            _atomic_write_json(path, existing)
        except Exception:
            pass  # 静默失败，不影响路由功能

    def _load_learned_patterns(self) -> dict[str, list[str]]:
        """从磁盘加载已持久化的学习模式。"""
        try:
            data = _atomic_read_json(self._learned_patterns_path())
            if data:
                return {k: v for k, v in data.items() if isinstance(v, list)}
        except Exception:
            pass
        return {}

    # ── Router 委托方法（策略匹配 + 装配指令） ──

    def match(self, envelope: Envelope):
        """委托到内部 Router：根据 envelope 匹配策略配置。"""
        return self._regex_router.match(envelope)

    def assemble(self, strategy):
        """委托到内部 Router：从策略配置产出装配指令列表。"""
        return self._regex_router.assemble(strategy)

    def list_strategies(self) -> list[str]:
        return self._regex_router.list_strategies()

    # ── 自适应方法 (v4) — 委托到内部 Router ──

    @property
    def is_adaptive(self) -> bool:
        return self._regex_router.is_adaptive

    def enable_adaptive(self) -> None:
        self._regex_router.enable_adaptive()

    def create_profile(self, envelope: Envelope) -> "ProblemProfile":  # noqa: F821
        return self._regex_router.create_profile(envelope)

    def assemble_from_profile(self, profile: "ProblemProfile") -> list:  # noqa: F821
        return self._regex_router.assemble_from_profile(profile)

    def assemble_from_strategy_id(self, strategy_id: str) -> list:
        return self._regex_router.assemble_from_strategy_id(strategy_id)

    def refine_for_spiral(self, envelope: Envelope, user_feedback: dict) -> Envelope:
        """螺旋精炼回调，委托到内部 Router。"""
        return self._regex_router.refine_for_spiral(envelope, user_feedback)

    def set_mode(self, mode: str) -> str:
        """切换策略模式: 'classic' | 'deductive'。"""
        return self._regex_router.set_mode(mode)

    @property
    def mode(self) -> str:
        return self._regex_router.mode

    def get_stats(self) -> dict:
        return {
            "total": self.total_classifications,
            "regex_hits": self.regex_hits,
            "learned_hits": self.learned_hits,
            "model_calls": self.model_calls,
            "model_call_rate": f"{self.model_calls / max(1, self.total_classifications):.1%}",
            "tokens_saved": self.total_tokens_saved,
            "learned_patterns_count": sum(len(v) for v in self._learned_patterns.values()),
            "mode": self._regex_router.mode,
            "cache_metrics": {
                "hit_rate": f"{self.prompt_builder.metrics.hit_rate:.1%}" if self.prompt_builder else "N/A",
                "tokens_saved": self.prompt_builder.metrics.estimated_tokens_saved if self.prompt_builder else 0,
                "cost_saved": f"${self.prompt_builder.metrics.estimated_cost_saved:.4f}" if self.prompt_builder else "N/A",
            },
        }
