#!/usr/bin/env python3
"""
NegVerifyIntegrate — 整合外部研究结果到交付物

CC 主进程调用方式:
    echo '<directive_with_external.json>' | python neg_verify_integrate.py --stdin

输入 JSON 格式:
{
  "neg_verify_directive": {...},       # neg_verify.py 构造的指令
  "external_research": {               # CC 主进程填入的外部研究结果
    "search_results": [
      {"title": "...", "url": "...", "snippet": "..."}
    ],
    "fetched_sources": [
      {"url": "...", "title": "...", "content": "..."}
    ],
    "synthesis": "..."                 # CC 综合的文本
  }
}

输出 JSON:
{
  "neg_verify": {
    "triggered": true,
    "verdict": "alternative_found | double_negative | inconclusive",
    "confidence": "high | medium | low",
    "alternatives": [...],
    "external_evidence_summary": "...",
    "claim_type": "...",
    "primary_claim": "..."
  }
}

判定逻辑:
- alternative_found: 找到 ≥2 个独立替代方案线索
- double_negative: 外部也明确确认无解（≥2 个独立证据）
- inconclusive: 信号不足，无法判定
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


# ── 替代方案检测模式 ──

ALTERNATIVE_PATTERNS = [
    # 侧信道
    (re.compile(r"(侧信道|side.channel|旁路攻击|timing.attack|power.analysis)", re.IGNORECASE), "side_channel", 1.0),
    # 实现漏洞
    (re.compile(r"(实现漏洞|implementation.flaw|implementation.vulnerability)", re.IGNORECASE), "implementation_flaw", 1.0),
    (re.compile(r"CVE-\d{4}-\d+", re.IGNORECASE), "cve", 1.0),
    # 替代方法
    (re.compile(r"(替代方法|alternative.*method|alternative.*approach)", re.IGNORECASE), "alternative_method", 0.9),
    # 重新定义
    (re.compile(r"(重新定义|reformulation|alternative.*formulation|reformulat)", re.IGNORECASE), "reformulation", 0.9),
    # 绕过
    (re.compile(r"(绕过|bypass)", re.IGNORECASE), "bypass", 0.7),
    # 信息泄露
    (re.compile(r"(side.information|泄露|leakage|auxiliary.*channel)", re.IGNORECASE), "leakage", 1.0),
    # 结构性替代（换基/等价变换/重新参数化）
    (re.compile(r"(换基|等价变换|重新参数化|structural.*alternative|change.*of.*basis)", re.IGNORECASE), "structural_alternative", 0.9),
    # 历史/2010 漏洞
    (re.compile(r"(2010|2011|2012|2013).*(漏洞|vulnerability|bug)", re.IGNORECASE), "historical_vuln", 0.8),
    # 实现层攻击
    (re.compile(r"(implementation.*attack|protocol.*level|out.of.band)", re.IGNORECASE), "implementation_attack", 1.0),
]


# ── 外部否定证据模式 ──

EXTERNAL_NEGATIVE_PATTERNS = [
    (re.compile(r"(已经证明|mathematically proven|theoretically proven)", re.IGNORECASE), "proven", 1.0),
    (re.compile(r"(没有办法|no known|不存在.*方法|no method)", re.IGNORECASE), "no_method", 1.0),
    (re.compile(r"(computationally.infeasible|intractable)", re.IGNORECASE), "infeasible", 1.0),
    (re.compile(r"(provably.secure|information.theoretically.secure)", re.IGNORECASE), "provably_secure", 1.0),
]


# ── 评估函数 ──

def collect_external_text(external: dict) -> str:
    """汇总所有外部文本（搜索结果 + 抓取内容 + 综合）。"""
    parts: list[str] = []
    parts.append(external.get("synthesis", "") or "")

    for r in external.get("search_results", []) or []:
        if isinstance(r, dict):
            parts.append(r.get("title", ""))
            parts.append(r.get("snippet", ""))
        else:
            parts.append(str(r))

    for f in external.get("fetched_sources", []) or []:
        if isinstance(f, dict):
            parts.append(f.get("title", ""))
            # 限制单源文本长度，避免 token 爆炸
            content = f.get("content", "") or f.get("claims_text", "")
            parts.append(content[:5000])
        else:
            parts.append(str(f))

    return " ".join(parts)


def score_alternatives(text: str) -> tuple[list[dict], float]:
    """扫描外部文本，匹配替代方案模式。"""
    hits: list[dict] = []
    total_score = 0.0
    seen_categories: set[str] = set()

    for pattern, category, weight in ALTERNATIVE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            # 同类别多次命中只计一次（避免重复计数）
            if category not in seen_categories:
                hits.append({
                    "category": category,
                    "match_count": len(matches),
                    "weight": weight,
                    "samples": list(set(matches))[:3],
                })
                seen_categories.add(category)
                total_score += weight * min(len(matches), 3)

    return hits, total_score


def score_negatives(text: str) -> tuple[list[dict], float]:
    """扫描外部文本，匹配否定证据模式。"""
    hits: list[dict] = []
    total_score = 0.0
    seen_categories: set[str] = set()

    for pattern, category, weight in EXTERNAL_NEGATIVE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            if category not in seen_categories:
                hits.append({
                    "category": category,
                    "match_count": len(matches),
                    "weight": weight,
                    "samples": list(set(matches))[:3],
                })
                seen_categories.add(category)
                total_score += weight * min(len(matches), 3)

    return hits, total_score


def evaluate(directive: dict, external: dict) -> dict:
    """评估外部研究结果，给出最终判定。"""

    claim_type = directive.get("claim_type", "unknown")
    primary_claim = directive.get("primary_claim", "")[:200]
    search_results = external.get("search_results", []) or []
    fetched = external.get("fetched_sources", []) or []
    synthesis = external.get("synthesis", "") or ""

    # 汇总文本
    all_text = collect_external_text(external)
    all_text_len = len(all_text)

    # 信号太弱
    if all_text_len < 100:
        return {
            "verdict": "inconclusive",
            "confidence": "low",
            "reason": "external_text_too_short",
            "external_text_length": all_text_len,
            "claim_type": claim_type,
            "primary_claim": primary_claim,
        }

    alt_hits, alt_score = score_alternatives(all_text)
    neg_hits, neg_score = score_negatives(all_text)

    # ── 判定 ──

    # 规则 1: 替代方案占优
    if alt_score >= 1.5 and alt_score > neg_score:
        return {
            "verdict": "alternative_found",
            "confidence": "high" if alt_score >= 3.0 else "medium",
            "alternatives": alt_hits,
            "alternative_score": alt_score,
            "external_evidence_summary": synthesis[:500],
            "external_sources_count": len(search_results) + len(fetched),
            "claim_type": claim_type,
            "primary_claim": primary_claim,
        }

    # 规则 2: 外部也否定
    if neg_score >= 1.5 and neg_score > alt_score:
        return {
            "verdict": "double_negative",
            "confidence": "high" if neg_score >= 3.0 else "medium",
            "negative_evidence": neg_hits,
            "negative_score": neg_score,
            "external_evidence_summary": synthesis[:500],
            "external_sources_count": len(search_results) + len(fetched),
            "claim_type": claim_type,
            "primary_claim": primary_claim,
        }

    # 规则 3: 信号混杂 / 不确定
    return {
        "verdict": "inconclusive",
        "confidence": "low" if alt_score < 0.5 and neg_score < 0.5 else "medium",
        "alternative_score": alt_score,
        "negative_score": neg_score,
        "alternatives": alt_hits,
        "negative_evidence": neg_hits,
        "external_evidence_summary": synthesis[:500],
        "external_sources_count": len(search_results) + len(fetched),
        "claim_type": claim_type,
        "primary_claim": primary_claim,
        "recommendation": (
            "LITE 结果不明确，建议升级到 MINI 档位重试"
            if (alt_score + neg_score) >= 1.0
            else "信号不足，建议人工判断或换查询角度"
        ),
    }


def render_markdown(result: dict) -> str:
    """渲染 verdict 为人类可读 Markdown（供 CC 嵌入交付物）。"""
    v = result.get("verdict", "unknown")
    conf = result.get("confidence", "low")
    primary = result.get("primary_claim", "")[:150]

    if v == "alternative_found":
        alts = result.get("alternatives", [])
        alt_md = "\n".join(f"  - **{a['category']}**: 命中 {a['match_count']} 次" for a in alts[:5])
        return (
            f"## ❌ 不交付否定 — 找到外部替代方案\n\n"
            f"- **原始结论**: {primary}\n"
            f"- **判定**: `alternative_found` (confidence: {conf})\n"
            f"- **替代方案线索**:\n{alt_md}\n"
            f"- **建议**: 请重新审视原始结论，考虑改走以下路径: "
            f"{', '.join(a['category'] for a in alts[:3])}\n"
        )

    if v == "double_negative":
        neg = result.get("negative_evidence", [])
        neg_md = "\n".join(f"  - **{n['category']}**: 命中 {n['match_count']} 次" for n in neg[:5])
        return (
            f"## ✅ 双重确认否定\n\n"
            f"- **原始结论**: {primary}\n"
            f"- **判定**: `double_negative` (confidence: {conf})\n"
            f"- **外部证据**:\n{neg_md}\n"
            f"- **可信度**: 高（内部 + 外部独立验证均无解）\n"
            f"- **建议**: 接受此结论，可停止投入更多资源\n"
        )

    # inconclusive
    rec = result.get("recommendation", "建议人工判断")
    return (
        f"## ⚠️ 存疑否定\n\n"
        f"- **原始结论**: {primary}\n"
        f"- **判定**: `inconclusive` (confidence: {conf})\n"
        f"- **替代信号得分**: {result.get('alternative_score', 0)}\n"
        f"- **否定信号得分**: {result.get('negative_score', 0)}\n"
        f"- **建议**: {rec}\n"
        f"- **下一步**: 考虑升级到 MINI 档位或换查询角度\n"
    )


# ── 主入口 ──

def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        return 0

    raw: str = ""
    if len(sys.argv) > 1 and sys.argv[1] == "--stdin":
        raw = sys.stdin.read()
    elif len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        # 尝试 stdin
        if not sys.stdin.isatty():
            raw = sys.stdin.read()

    if not raw.strip():
        print(json.dumps({"error": "no_input", "usage": "stdin JSON"}, ensure_ascii=False))
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": "json_decode_failed", "detail": str(e)}, ensure_ascii=False))
        return 1

    directive = data.get("neg_verify_directive", {})
    external = data.get("external_research", {})

    if not directive.get("triggered"):
        # 未触发
        print(json.dumps({
            "neg_verify": {
                "triggered": False,
                "reason": directive.get("reason", "not_triggered"),
            }
        }, ensure_ascii=False, indent=2))
        return 0

    # 评估
    result = evaluate(directive, external)

    # 输出 JSON + Markdown
    output = {
        "neg_verify": result,
        "neg_verify_markdown": render_markdown(result),
        "stats": {
            "search_results_count": len(external.get("search_results", []) or []),
            "fetched_sources_count": len(external.get("fetched_sources", []) or []),
            "synthesis_length": len(external.get("synthesis", "") or ""),
            "external_text_length": len(collect_external_text(external)),
        },
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())