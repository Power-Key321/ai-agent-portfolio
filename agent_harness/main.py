"""
Agent Harness CLI 入口 — 独立运行或作为 CC skill 后端。

用法:
    python -m agent_harness.main "帮我实现一个JWT认证中间件"
    python -m agent_harness.main --diagnose "修复src/auth.py的bug"
    python -m agent_harness.main --stats
"""

import sys
import io
import json
from pathlib import Path

# 确保 agent_harness 在 path 中
_HARNESS_ROOT = Path(__file__).resolve().parent
if str(_HARNESS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT.parent))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent Harness — 乐高式模块化任务编排框架",
    )
    parser.add_argument(
        "task", nargs="?", default=None,
        help="要执行的任务描述",
    )
    parser.add_argument(
        "--diagnose", action="store_true",
        help="诊断模式：仅分类和装配，不执行",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="显示 ModelRouter 统计信息",
    )
    parser.add_argument(
        "--model", action="store_true",
        help="启用模拟模型回调（测试用，仅 CC 适配器）",
    )
    parser.add_argument(
        "--deepseek", action="store_true",
        help="使用 DeepSeek API 适配器（默认模型 deepseek-v4-flash）",
    )
    parser.add_argument(
        "--deepseek-model", type=str, default=None,
        help="DeepSeek 模型名覆盖（如 deepseek-v4-pro）",
    )
    parser.add_argument(
        "--intent", type=str, default=None,
        choices=["code_feature", "code_fix", "data_analysis", "research", "simple_query", "refactor"],
        help="外部指定意图，跳过模型分类（CC 验证用）",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="以 JSON 格式输出结果",
    )

    args = parser.parse_args()

    # 选择适配器后端
    if args.deepseek:
        from agent_harness.adapters.deepseek import DeepSeekAdapter
        adapter = DeepSeekAdapter(
            model=args.deepseek_model,
        )
    else:
        from agent_harness.adapters.claude_code import ClaudeCodeAdapter, diagnose_task
        model_callback = _make_mock_callback() if args.model else None
        adapter = ClaudeCodeAdapter(on_model_call=model_callback)

    if args.stats:
        stats = adapter.get_router_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    if args.task:
        if args.diagnose:
            if args.deepseek:
                result = json.dumps(
                    adapter.diagnose(args.task, intent_override=args.intent),
                    ensure_ascii=False, indent=2,
                )
            else:
                result = diagnose_task(args.task, intent_override=args.intent)
        else:
            result = adapter.run_standalone(args.task, intent_override=args.intent)

        if args.json or args.diagnose:
            print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            data = json.loads(result) if isinstance(result, str) else result
            print(f"\n意图: {data.get('intent_class', 'N/A')}")
            print(f"策略: {data.get('strategy_id', 'N/A')}")
            print(f"螺旋轮次: {data.get('spiral_iterations', 0)}")
            route_method = data.get('route_method', 'unknown')
            print(f"路由方式: {route_method}")
            conv = data.get('convergence', {})
            if conv:
                print(f"收敛速度: {conv.get('convergence_speed', 'N/A')}")
                print(f"最终半径: {conv.get('r_final', 'N/A')}")
            exec_log = data.get('execution_log', [])
            if exec_log:
                print(f"\n执行日志 ({len(exec_log)} 步):")
                for entry in exec_log:
                    status = "OK" if entry.get('success') else f"FAIL: {entry.get('error', '')}"
                    print(f"  {entry.get('module', '?'):>30} → {status}")
        return

    parser.print_help()


def _make_mock_callback():
    """构造一个模拟模型回调（用于测试和演示）。

    注意：只从 prompt 中提取用户输入部分进行关键词匹配，
    避免 skeleton 中的分类说明文本（如 "code_fix: fixing bugs"）干扰匹配。
    """
    import re

    def mock_model(prompt: str, skeleton_hash: str) -> str:
        # 只取 ## User Input 之后的内容，排除 skeleton 干扰
        user_match = re.search(r'## User Input\n(.+)', prompt)
        text = user_match.group(1).strip().lower() if user_match else prompt.lower()

        if any(kw in text for kw in ['实现', '做', '搞', '开发', '写', '创建', '添加']):
            return 'code_feature'
        if any(kw in text for kw in ['修复', 'fix', 'bug', '报错', '错误']):
            return 'code_fix'
        if any(kw in text for kw in ['分析', '画', '图', '统计', '走势', '数据']):
            return 'data_analysis'
        if any(kw in text for kw in ['搜索', '查找', '找', '搜', '调研']):
            return 'research'
        if any(kw in text for kw in ['重构', '整理', '优化']):
            return 'refactor'
        return 'simple_query'

    return mock_model


if __name__ == "__main__":
    main()
