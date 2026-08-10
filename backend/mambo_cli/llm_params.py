"""LLM 模型参数定义与校验（基于后端 /api/system-config 的 llm_parameters）。

对齐前端 AgentEditor 的"建议参数"过滤逻辑:
  coreParameters(temperature/top_p) + 模型 meta_config.supported_parameters + default_activate
"""
from __future__ import annotations

import argparse

from backend.mambo_cli.util import UsageError, parse_bool

# 前端在 modelParameters 中额外保留的 chat 专属参数（不在 SUPPORTED_LLM_PARAMETERS 中）
CHAT_ONLY_PARAMS = {"max_context_messages", "stream", "enable_suggest", "enable_ask_user"}

# 与前端 AgentEditor 一致的"始终建议"核心参数
CORE_PARAMS = {"temperature", "top_p"}


def build_definition_map(definitions: list[dict]) -> dict[str, dict]:
    """key -> 参数定义 dict 映射。"""
    return {d.get("key"): d for d in definitions if d.get("key")}


def suggested_params(definitions: list[dict], supported_parameters: set[str]) -> list[dict]:
    """过滤出建议参数列表（前端 dynamicParameters 同款逻辑）。"""
    result = []
    for d in definitions:
        key = d.get("key")
        if key in CORE_PARAMS or key in supported_parameters or d.get("default_activate"):
            result.append(d)
    return result


def validate_param(def_map: dict[str, dict], key: str, raw_value: str):
    """校验并规范化参数值（返回原生类型 int/float/bool/str，与前端存储一致）；非法时抛 UsageError。"""
    if key in CHAT_ONLY_PARAMS:
        return raw_value
    definition = def_map.get(key)
    if not definition:
        raise UsageError(
            f"未知模型参数 '{key}'（可用 mambo agent params <agent> 查看建议参数；"
            f"chat 专属参数: {'/'.join(sorted(CHAT_ONLY_PARAMS))}）"
        )
    ptype = definition.get("type")
    limit = definition.get("limit")
    if ptype == "integer":
        try:
            value = int(raw_value)
        except ValueError:
            raise UsageError(f"参数 '{key}' 需要整数，收到 '{raw_value}'")
        _check_range(key, value, limit)
        return value
    if ptype == "number":
        try:
            value = float(raw_value)
        except ValueError:
            raise UsageError(f"参数 '{key}' 需要数值，收到 '{raw_value}'")
        _check_range(key, value, limit)
        return value
    if ptype == "boolean":
        try:
            value = parse_bool(raw_value)
        except argparse.ArgumentTypeError as exc:
            raise UsageError(f"参数 '{key}': {exc}")
        return value
    # string: 枚举检查
    if isinstance(limit, list) and raw_value not in [str(x) for x in limit]:
        raise UsageError(
            f"参数 '{key}' 取值必须是 {'/'.join(str(x) for x in limit)}（收到 '{raw_value}'）"
        )
    return raw_value


def _check_range(key: str, value, limit) -> None:
    if not isinstance(limit, dict):
        return
    if "min" in limit and value < limit["min"]:
        raise UsageError(f"参数 '{key}' 最小值 {limit['min']}，收到 {value}")
    if "max" in limit and value > limit["max"]:
        raise UsageError(f"参数 '{key}' 最大值 {limit['max']}，收到 {value}")


def format_limit(limit) -> str:
    """将 limit 渲染为可读文本。"""
    if isinstance(limit, dict):
        parts = []
        if "min" in limit:
            parts.append(f"≥{limit['min']}")
        if "max" in limit:
            parts.append(f"≤{limit['max']}")
        return " ".join(parts)
    if isinstance(limit, list):
        return "/".join(str(x) for x in limit)
    return "-"
