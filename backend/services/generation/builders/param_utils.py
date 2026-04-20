# backend/services/generation/builders/param_utils.py

from typing import Dict, Any, Optional

from backend.config.llm_parameters import SUPPORTED_LLM_PARAMETERS


def map_model_parameters(model_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """将扁平的 modelParameters 映射为结构化的 API 参数。

    调用方应通过 ORM 的 parsed_model_parameters 属性获取已归一化的 dict，
    本函数仅负责将扁平 key-value 映射为嵌套结构。
    """
    flat_params = model_params or {}

    structured: Dict[str, Any] = {}
    param_def_map = {p.key: p for p in SUPPORTED_LLM_PARAMETERS}

    for key, value in flat_params.items():
        if key in ["max_context_messages", "stream", "enabled_mcp_ids", "enable_suggest"]:
            continue

        definition = param_def_map.get(key)
        if definition:
            target = structured
            for part in definition.path[:-1]:
                target = target.setdefault(part, {})
            target[definition.path[-1]] = value

    if 'stream' in flat_params:
        structured['stream'] = flat_params['stream']

    return structured
