"""全量上下文检索 — 按 refs 指针预热 LazyCache。"""

import os
from agent_harness.modules.base import ModuleBase, ModuleResult
from agent_harness.core.envelope import Envelope, LazyCache


# 默认搜索路径（可被构造参数或环境变量覆盖）
DEFAULT_MEMORY_DIRS = [
    os.path.expanduser(r"~\.claude\projects"),
    os.path.expanduser(r"~\.claude\memory"),
    os.path.join(os.path.dirname(__file__), "..", "..", "memory"),
]
DEFAULT_PROJECT_ROOT = os.environ.get(
    "HARNESS_PROJECT_ROOT",
    os.path.join(os.path.dirname(__file__), "..", ".."),
)


class ContextFull(ModuleBase):
    """全量上下文检索模块。

    接收 Envelope.context.refs 的指针列表，
    逐一检索并将结果写入 LazyCache。
    后续模块可直接从 cache 读取，无需重复检索。

    Args:
        memory_dirs: memory:// 协议的搜索目录列表
        project_root: file:// 协议的项目根目录
        max_content_length: 单个检索结果的最大字符数
    """

    name = "context"
    variant = "full"

    def __init__(
        self,
        memory_dirs: list[str] | None = None,
        project_root: str | None = None,
        max_content_length: int = 3000,
    ):
        self.memory_dirs = memory_dirs or os.environ.get(
            "HARNESS_MEMORY_DIRS", ""
        ).split(os.pathsep) if os.environ.get("HARNESS_MEMORY_DIRS") else DEFAULT_MEMORY_DIRS
        self.project_root = project_root or DEFAULT_PROJECT_ROOT
        self.max_content_length = max_content_length

    def process(self, envelope: Envelope) -> ModuleResult:
        cache: LazyCache = envelope.context.get("cache")
        refs: list[str] = envelope.context.get("refs", [])

        if cache is not None and cache._resolver is None:
            cache.set_resolver(self._resolve)

        if refs and cache is not None:
            cache.preload(refs)
            envelope.context["window_used_so_far"] = cache.total_tokens()

        return ModuleResult(envelope=envelope)

    def _resolve(self, ref: str) -> dict | None:
        """实际检索逻辑。

        ref 格式:
          - "memory://<name>" → 在 memory_dirs 中搜索 .md 文件
          - "file://." → 扫描项目根目录
          - "file://<relpath>" → 读取项目根目录下的相对路径

        后续可接入向量检索、RAG等。
        """

        if ref.startswith("memory://"):
            return self._resolve_memory(ref)

        if ref.startswith("file://"):
            return self._resolve_file(ref)

        return None

    def _resolve_memory(self, ref: str) -> dict:
        memory_name = ref.replace("memory://", "").lower().replace("-", " ").replace("_", " ")
        best_match = None

        for base_dir in self.memory_dirs:
            if not os.path.isdir(base_dir):
                continue
            try:
                for root, dirs, files in os.walk(base_dir):
                    # 限制深度避免无限遍历
                    depth = root[len(base_dir):].count(os.sep)
                    if depth > 2:
                        dirs.clear()
                    for fname in files:
                        if not fname.endswith((".md", ".txt", ".json")):
                            continue
                        fname_normalized = fname.replace("-", " ").replace("_", " ").replace(".md", "").replace(".txt", "").replace(".json", "").lower()
                        if memory_name in fname_normalized or fname_normalized in memory_name:
                            fpath = os.path.join(root, fname)
                            try:
                                content = open(fpath, encoding="utf-8").read()[:self.max_content_length]
                                best_match = {
                                    "source": ref,
                                    "file": fpath,
                                    "relevance_score": 0.8,
                                    "content": content,
                                    "token_count": len(content) // 3,
                                }
                                return best_match
                            except Exception:
                                continue
            except PermissionError:
                continue

        return {
            "source": ref,
            "relevance_score": 0.0,
            "content": f"[Memory not found: {memory_name}]",
            "token_count": 20,
        }

    def _resolve_file(self, ref: str) -> dict:
        file_ref = ref.replace("file://", "").lstrip("/")

        if file_ref == ".":
            # 扫描项目根目录结构
            try:
                items = os.listdir(self.project_root)
                content = "\n".join(
                    f"{'[D]' if os.path.isdir(os.path.join(self.project_root, i)) else '[F]'} {i}"
                    for i in sorted(items)[:50]
                )
                return {
                    "source": ref,
                    "relevance_score": 0.9,
                    "content": f"项目根目录 ({self.project_root}):\n{content}",
                    "token_count": len(content) // 3,
                }
            except Exception:
                return self._not_found(ref, self.project_root)

        # 安全检查：防止路径遍历
        full_path = os.path.normpath(os.path.join(self.project_root, file_ref))
        if not full_path.startswith(os.path.normpath(self.project_root)):
            return self._not_found(ref, file_ref)

        if not os.path.exists(full_path):
            return self._not_found(ref, file_ref)

        try:
            if os.path.isdir(full_path):
                items = os.listdir(full_path)
                content = "\n".join(sorted(items)[:50])
                return {
                    "source": ref,
                    "relevance_score": 0.9,
                    "content": content,
                    "token_count": len(content) // 3,
                }
            else:
                content = open(full_path, encoding="utf-8").read()[:self.max_content_length]
                return {
                    "source": ref,
                    "relevance_score": 0.9,
                    "content": content,
                    "token_count": len(content) // 3,
                }
        except Exception:
            return self._not_found(ref, file_ref)

    def _not_found(self, ref: str, attempted: str) -> dict:
        return {
            "source": ref,
            "relevance_score": 0.0,
            "content": f"[Not found: {attempted}]",
            "token_count": 15,
        }
