"""
Carbon Engine API Server — FastAPI + WebSocket。

启动:
    python -m agent_harness.api.server
    python -m agent_harness.api.server --port 8420 --host 0.0.0.0

端点:
    POST   /api/task/start        — 提交任务
    WS     /api/task/{id}/stream  — WebSocket 流式推送
    GET    /api/task/{id}/status  — 任务状态
    GET    /api/tasks             — 任务列表
    GET    /api/stats             — 引擎统计
    GET    /api/evolution         — 进化数据
    GET    /health                — 健康检查
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 harness 在 path 中
_HARNESS_ROOT = Path(__file__).resolve().parent.parent
if str(_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HARNESS_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_harness.api.routes.tasks import router as tasks_router, set_adapter
from agent_harness.api.routes.stats import router as stats_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Carbon Engine API",
        description="乐高式模块化任务编排框架 — REST + WebSocket API",
        version="2.0.0",
    )

    # CORS — 允许桌面客户端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tasks_router)
    app.include_router(stats_router)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "brand": "Carbon Engine",
            "version": "2.0.0",
            "framework": "Harness v2",
        }

    return app


app = create_app()


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Carbon Engine API Server")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址")
    parser.add_argument("--port", type=int, default=8420, help="绑定端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    parser.add_argument("--deepseek-key", default="", help="DeepSeek API key")

    args = parser.parse_args()

    if args.deepseek_key:
        import os
        os.environ["DEEPSEEK_API_KEY"] = args.deepseek_key

    # 初始化适配器
    try:
        from agent_harness.adapters.deepseek import get_deepseek_adapter
        adapter = get_deepseek_adapter()
        set_adapter(adapter)
        print(f"[Carbon Engine] DeepSeek adapter initialized (key={'***' if adapter.api_key else 'NONE'})")
    except Exception as e:
        print(f"[Carbon Engine] Adapter init warning: {e}")

    print(f"[Carbon Engine] Starting server on http://{args.host}:{args.port}")
    print(f"[Carbon Engine] API docs: http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "agent_harness.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
