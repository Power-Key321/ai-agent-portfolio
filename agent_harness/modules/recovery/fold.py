"""
Fold — 模式折叠 — 将深层嵌套参数展开为扁平表示，执行时再展开还原。

当工具参数 schema 超过 10 个字段或深度 > 2 时，
某些模型会丢失参数。Fold 将深嵌套结构转为 dot-notation 平面格式，
dispatch 时再重新嵌套。
"""

from __future__ import annotations


def fold_schema(schema: dict, prefix: str = "") -> dict:
    """将嵌套 schema 拍平为 dot-notation。

    Example:
        {"user": {"name": str, "address": {"city": str, "zip": int}}}
        → {"user.name": str, "user.address.city": str, "user.address.zip": int}
    """
    flat: dict = {}
    for key, value in schema.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and not _is_leaf(value):
            flat.update(fold_schema(value, full_key))
        else:
            flat[full_key] = value
    return flat


def unfold_arguments(flat_args: dict) -> dict:
    """将 flat dot-notation 参数重新嵌套。

    Example:
        {"user.name": "Alice", "user.address.city": "NYC"}
        → {"user": {"name": "Alice", "address": {"city": "NYC"}}}
    """
    nested: dict = {}
    for key, value in flat_args.items():
        parts = key.split(".")
        current = nested
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return nested


def should_fold(schema: dict, max_fields: int = 10, max_depth: int = 2) -> bool:
    """判断 schema 是否需要折叠。"""
    total_fields = _count_fields(schema)
    depth = _max_depth(schema)
    return total_fields > max_fields or depth > max_depth


def _count_fields(d: dict) -> int:
    count = 0
    for v in d.values():
        if isinstance(v, dict) and not _is_leaf(v):
            count += _count_fields(v)
        else:
            count += 1
    return count


def _max_depth(d: dict, current: int = 0) -> int:
    max_d = current + 1
    for v in d.values():
        if isinstance(v, dict) and not _is_leaf(v):
            max_d = max(max_d, _max_depth(v, current + 1))
    return max_d


def _is_leaf(d: dict) -> bool:
    """判断是否为叶子节点（描述类型而非嵌套结构）。"""
    type_keys = {"type", "description", "enum", "default", "properties", "items"}
    return bool(type_keys & set(d.keys()))
