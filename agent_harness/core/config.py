"""
HarnessConfig — 统一配置中心。

所有可配置参数汇聚于此，支持:
1. 默认值（零配置运行）
2. 环境变量覆盖（HARNESS_* 前缀）
3. JSON 配置文件加载
4. Schema 自校验

用法:
    config = HarnessConfig()
    config.load()  # 按 环境变量 > config.json > 默认值 优先级
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── 默认配置 ──

DEFAULT_CONFIG = {
    "spiral": {
        "convergence_threshold": 0.05,
        "max_iterations": 5,
        "alpha": 0.4,
        "beta": 0.3,
    },
    "gate": {
        "complexity_low_threshold": 0.30,
        "complexity_high_threshold": 0.60,
        "ambiguity_weight": 0.5,
        "entity_richness_bonus": -0.5,
        "input_short_threshold": 30,
        "input_long_threshold": 120,
    },
    "router": {
        "regex_confidence_threshold": 0.45,
        "model_min_confidence": 0.70,
        "learned_pattern_threshold": 0.50,
    },
    "cache": {
        "ttl_seconds": 300,
        "max_content_length": 3000,
    },
    "executor": {
        "retry_same_max": 3,
        "retry_refined_max": 2,
        "re_decompose_max": 2,
        "timeout_ms": 60000,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_reset_seconds": 60,
    },
    "context": {
        "memory_dirs": [],
        "project_root": "",
        "max_content_length": 3000,
    },
    "logging": {
        "level": "INFO",
        "file": "",
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    },
}

# Schema: 每个 key 的期望类型
CONFIG_SCHEMA = {
    "spiral": dict,
    "spiral.convergence_threshold": (int, float),
    "spiral.max_iterations": int,
    "spiral.alpha": (int, float),
    "spiral.beta": (int, float),
    "gate": dict,
    "gate.complexity_low_threshold": (int, float),
    "gate.complexity_high_threshold": (int, float),
    "gate.ambiguity_weight": (int, float),
    "gate.entity_richness_bonus": (int, float),
    "gate.input_short_threshold": int,
    "gate.input_long_threshold": int,
    "router.regex_confidence_threshold": (int, float),
    "router.model_min_confidence": (int, float),
    "router.learned_pattern_threshold": (int, float),
    "executor.retry_same_max": int,
    "executor.retry_refined_max": int,
    "executor.re_decompose_max": int,
    "executor.timeout_ms": int,
    "executor.circuit_breaker_threshold": int,
    "executor.circuit_breaker_reset_seconds": int,
    "logging.level": str,
}


@dataclass
class HarnessConfig:
    """统一配置中心。

    加载优先级: 环境变量 HARNESS_* > config.json > 默认值

    Args:
        config_path: JSON 配置文件路径（可选）
    """

    config_path: Path | None = None
    _data: dict = field(default_factory=dict, init=False)
    _errors: list[str] = field(default_factory=list, init=False)

    def __post_init__(self):
        self._data = deepcopy(DEFAULT_CONFIG)

    def load(self, config_path: Path | None = None) -> HarnessConfig:
        """加载配置。先加载 JSON 文件，再覆盖环境变量。"""
        self._errors = []

        # Layer 1: JSON 配置文件
        path = config_path or self.config_path
        if path is None:
            path = self._find_config_file()
        if path and path.exists():
            self._load_json(path)

        # Layer 2: 环境变量
        self._load_env()

        # Layer 3: 校验
        self._validate()

        return self

    # ── 便捷访问 ──

    def get(self, key: str, default: Any = None) -> Any:
        """用点分隔的 key 获取配置值。如 'spiral.convergence_threshold'。"""
        keys = key.split(".")
        node = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    @property
    def spiral(self) -> dict:
        return self._data.get("spiral", {})

    @property
    def gate(self) -> dict:
        return self._data.get("gate", {})

    @property
    def router(self) -> dict:
        return self._data.get("router", {})

    @property
    def executor(self) -> dict:
        return self._data.get("executor", {})

    @property
    def cache(self) -> dict:
        return self._data.get("cache", {})

    @property
    def context(self) -> dict:
        return self._data.get("context", {})

    @property
    def logging(self) -> dict:
        return self._data.get("logging", {})

    @property
    def errors(self) -> list[str]:
        return self._errors

    @property
    def valid(self) -> bool:
        return len(self._errors) == 0

    def to_dict(self) -> dict:
        return deepcopy(self._data)

    # ── 内部 ──

    @staticmethod
    def _find_config_file() -> Path | None:
        candidates = [
            Path.cwd() / "harness_config.json",
            Path(__file__).resolve().parent.parent / "harness_config.json",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _load_json(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._deep_merge(self._data, data)
        except (json.JSONDecodeError, IOError) as e:
            self._errors.append(f"Config file error: {e}")

    def _load_env(self) -> None:
        env_map = {
            "HARNESS_SPIRAL_THRESHOLD": "spiral.convergence_threshold",
            "HARNESS_SPIRAL_MAX_ITER": "spiral.max_iterations",
            "HARNESS_SPIRAL_ALPHA": "spiral.alpha",
            "HARNESS_SPIRAL_BETA": "spiral.beta",
            "HARNESS_GATE_COMPLEXITY_LOW": "gate.complexity_low_threshold",
            "HARNESS_GATE_COMPLEXITY_HIGH": "gate.complexity_high_threshold",
            "HARNESS_ROUTER_REGEX_CONF": "router.regex_confidence_threshold",
            "HARNESS_ROUTER_MODEL_CONF": "router.model_min_confidence",
            "HARNESS_EXEC_TIMEOUT_MS": "executor.timeout_ms",
            "HARNESS_EXEC_RETRY_MAX": "executor.retry_same_max",
            "HARNESS_CB_THRESHOLD": "executor.circuit_breaker_threshold",
            "HARNESS_CACHE_TTL": "cache.ttl_seconds",
            "HARNESS_LOG_LEVEL": "logging.level",
            "HARNESS_LOG_FILE": "logging.file",
            "HARNESS_MEMORY_DIRS": "context.memory_dirs",
            "HARNESS_PROJECT_ROOT": "context.project_root",
        }

        for env_var, config_key in env_map.items():
            value = os.environ.get(env_var)
            if value is not None:
                self._set_dotted(config_key, self._coerce(value))

    @staticmethod
    def _coerce(value: str) -> Any:
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def _set_dotted(self, key: str, value: Any) -> None:
        keys = key.split(".")
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    @staticmethod
    def _deep_merge(base: dict, overlay: dict) -> None:
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                HarnessConfig._deep_merge(base[key], value)
            else:
                base[key] = deepcopy(value)

    def _validate(self) -> None:
        for key_path, expected_type in CONFIG_SCHEMA.items():
            value = self.get(key_path)
            if value is None:
                continue
            if not isinstance(value, expected_type):
                self._errors.append(
                    f"Type mismatch for {key_path}: expected {expected_type}, got {type(value).__name__}"
                )


# ── 全局单例 ──

_config: HarnessConfig | None = None


def get_config() -> HarnessConfig:
    global _config
    if _config is None:
        _config = HarnessConfig().load()
    return _config


def reload_config(path: Path | None = None) -> HarnessConfig:
    global _config
    _config = HarnessConfig(config_path=path).load()
    return _config
