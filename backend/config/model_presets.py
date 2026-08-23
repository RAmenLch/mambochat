# backend/config/model_presets.py
"""
模型预置注册表。

用途：国产模型（DeepSeek、GLM/Z.ai/智谱 等）的 /models 端点只返回标准 OpenAI 格式
（仅 id/object/created/owned_by），不含上下文长度、多模态、支持参数等元数据。

此模块维护一个按 api_host 域名索引的模型预置字典，在 fetch_models 流程中自动补全缺失字段。
"""

from pydantic import BaseModel, Field
from typing import Optional


class ModelPreset(BaseModel):
    """单个模型的预置规格"""

    modelId: str = Field(..., description="模型 ID，与 API /models 响应中的 id 字段精确匹配")
    name: str = Field(..., description="模型显示名称")
    context_length: int = Field(..., description="最大上下文窗口（tokens）")
    max_output_tokens: int = Field(..., description="最大输出 tokens")
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    tokenizer: Optional[str] = Field(default=None)
    supported_parameters: list[str] = Field(
        default_factory=list,
        description="该模型支持的参数 key 列表，必须为 SUPPORTED_LLM_PARAMETERS 中已定义的 key",
    )


# ============================================================
# GLM 参数分组（按能力递增）
# ============================================================

_GLM_BASE = [
    "temperature", "top_p", "max_tokens", "max_completion_tokens",
    "frequency_penalty", "presence_penalty", "stop",
    "glm::do_sample",
]

# GLM 4.5+：思考模式
_GLM_THINKING = [*_GLM_BASE, "glm::thinking.type", "glm::thinking.clear_thinking"]

# GLM 4.6+：思考 + Tool Stream
_GLM_TOOL_STREAM = [*_GLM_THINKING, "glm::tool_stream"]

# GLM 5.2：思考 + Tool Stream + 推理深度控制
_GLM_REASONING = [*_GLM_TOOL_STREAM, "glm::reasoning_effort"]

# GLM 5.3：始终思考（不可关闭）+ Tool Stream + 推理深度控制
_GLM_REASONING_FIXED = [
    *_GLM_BASE,
    "glm::thinking.clear_thinking",
    "glm::tool_stream",
    "glm::reasoning_effort",
]


# ============================================================
# GLM 模型共享列表（api.z.ai 与 open.bigmodel.cn 共有）
# ============================================================

_GLM_SHARED_CHAT_MODELS: list[ModelPreset] = [
    # === GLM 5.x 系列 ===
    # GLM-5.3：旗舰，1M 上下文，始终思考（不可关闭），支持 reasoning_effort
    ModelPreset(
        modelId="glm-5.3",
        name="GLM-5.3",
        context_length=1_000_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_REASONING_FIXED,
    ),
    # GLM-5.2：旗舰，1M 上下文，支持 reasoning_effort
    ModelPreset(
        modelId="glm-5.2",
        name="GLM-5.2",
        context_length=1_000_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_REASONING,
    ),
    # GLM-5.1：旗舰，200K 上下文
    ModelPreset(
        modelId="glm-5.1",
        name="GLM-5.1",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),
    # GLM-5：744B 参数，200K 上下文
    ModelPreset(
        modelId="glm-5",
        name="GLM-5",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),
    # GLM-5-Turbo：Agent/OpenClaw 优化
    ModelPreset(
        modelId="glm-5-turbo",
        name="GLM-5 Turbo",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),

    # === 视觉模型 ===
    # GLM-5V-Turbo：多模态视觉（文本+图片+视频）
    ModelPreset(
        modelId="glm-5v-turbo",
        name="GLM-5V Turbo",
        context_length=200_000,
        max_output_tokens=128_000,
        input_modalities=["text", "image", "video"],
        supported_parameters=_GLM_TOOL_STREAM,
    ),

    # === GLM 4.7 系列 ===
    ModelPreset(
        modelId="glm-4.7",
        name="GLM-4.7",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),
    ModelPreset(
        modelId="glm-4.7-flashx",
        name="GLM-4.7 FlashX",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),
    ModelPreset(
        modelId="glm-4.7-flash",
        name="GLM-4.7 Flash (Free)",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),

    # === GLM 4.6 ===
    ModelPreset(
        modelId="glm-4.6",
        name="GLM-4.6",
        context_length=200_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_TOOL_STREAM,
    ),

    # === GLM 4.5 系列（无 tool_stream，4.6+ 才支持） ===
    ModelPreset(
        modelId="glm-4.5-air",
        name="GLM-4.5 Air",
        context_length=128_000,
        max_output_tokens=96_000,
        supported_parameters=_GLM_THINKING,
    ),
    ModelPreset(
        modelId="glm-4.5-airx",
        name="GLM-4.5 AirX",
        context_length=128_000,
        max_output_tokens=96_000,
        supported_parameters=_GLM_THINKING,
    ),
    ModelPreset(
        modelId="glm-4.5-flash",
        name="GLM-4.5 Flash (Free, 即将下线)",
        context_length=128_000,
        max_output_tokens=96_000,
        supported_parameters=_GLM_THINKING,
    ),

    # === GLM 4-32B（无思考模式，4.5+ 才支持） ===
    ModelPreset(
        modelId="glm-4-32b-0414-128k",
        name="GLM-4-32B-0414-128K",
        context_length=128_000,
        max_output_tokens=128_000,
        supported_parameters=_GLM_BASE,
    ),
]

# ============================================================
# api.z.ai 独有模型
# ============================================================

_GLM_ZAI_ONLY_MODELS: list[ModelPreset] = [
    ModelPreset(
        modelId="glm-4.5",
        name="GLM-4.5",
        context_length=128_000,
        max_output_tokens=96_000,
        supported_parameters=_GLM_THINKING,
    ),
    ModelPreset(
        modelId="glm-4.5-x",
        name="GLM-4.5-X",
        context_length=128_000,
        max_output_tokens=96_000,
        supported_parameters=_GLM_THINKING,
    ),
]

# ============================================================
# open.bigmodel.cn 独有模型
# ============================================================

_GLM_BIGMODEL_ONLY_MODELS: list[ModelPreset] = [
    # --- 纯文本 ---
    ModelPreset(
        modelId="glm-4-long",
        name="GLM-4-Long",
        context_length=1_000_000,
        max_output_tokens=4_096,
        supported_parameters=_GLM_THINKING,
    ),
    ModelPreset(
        modelId="glm-4-flashx-250414",
        name="GLM-4-FlashX-250414",
        context_length=128_000,
        max_output_tokens=16_384,
        supported_parameters=_GLM_BASE,
    ),
    ModelPreset(
        modelId="glm-4-flash-250414",
        name="GLM-4-Flash-250414 (Free)",
        context_length=128_000,
        max_output_tokens=16_384,
        supported_parameters=_GLM_BASE,
    ),
    # --- 视觉模型 ---
    ModelPreset(
        modelId="glm-4.6v",
        name="GLM-4.6V",
        context_length=128_000,
        max_output_tokens=32_768,
        input_modalities=["text", "image"],
        supported_parameters=_GLM_TOOL_STREAM,
    ),
    ModelPreset(
        modelId="glm-4.6v-flash",
        name="GLM-4.6V Flash (Free)",
        context_length=128_000,
        max_output_tokens=32_768,
        input_modalities=["text", "image"],
        supported_parameters=_GLM_TOOL_STREAM,
    ),
    ModelPreset(
        modelId="glm-4.1v-thinking-flashx",
        name="GLM-4.1V-Thinking-FlashX",
        context_length=64_000,
        max_output_tokens=16_384,
        input_modalities=["text", "image"],
        supported_parameters=_GLM_THINKING,
    ),
    ModelPreset(
        modelId="glm-4.1v-thinking-flash",
        name="GLM-4.1V-Thinking-Flash (Free)",
        context_length=64_000,
        max_output_tokens=16_384,
        input_modalities=["text", "image"],
        supported_parameters=_GLM_THINKING,
    ),
    ModelPreset(
        modelId="glm-4v-flash",
        name="GLM-4V-Flash (Free)",
        context_length=16_384,
        max_output_tokens=1_024,
        input_modalities=["text", "image"],
        supported_parameters=_GLM_BASE,
    ),
]

# ============================================================
# 模型预置注册表
# key = api_host 域名（去除协议和路径），如 "api.deepseek.com"
# ============================================================

MODEL_PRESETS: dict[str, list[ModelPreset]] = {
    "api.deepseek.com": [
        # --- DeepSeek V4 系列（最新） ---
        ModelPreset(
            modelId="deepseek-v4-flash",
            name="DeepSeek V4 Flash",
            context_length=1_000_000,
            max_output_tokens=384_000,
            supported_parameters=[
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "deepseek::thinking.type",
                "deepseek::reasoning_effort",
            ],
        ),
        ModelPreset(
            modelId="deepseek-v4-pro",
            name="DeepSeek V4 Pro",
            context_length=1_000_000,
            max_output_tokens=384_000,
            supported_parameters=[
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "deepseek::thinking.type",
                "deepseek::reasoning_effort",
            ],
        ),
        # --- 视觉模型（2026/08/21 发布，实验性质） ---
        # 支持 JPEG/PNG/GIF/WebP 图片输入，纯文本能力与 V4-Flash 持平
        ModelPreset(
            modelId="deepseek-v4-flash-vision-exp",
            name="DeepSeek V4 Flash Vision (Exp)",
            context_length=1_000_000,
            max_output_tokens=384_000,
            input_modalities=["text", "image"],
            supported_parameters=[
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "frequency_penalty",
                "presence_penalty",
                "stop",
                "deepseek::thinking.type",
                "deepseek::reasoning_effort",
            ],
        ),
        # --- 旧版（2026/07/24 弃用，当前仍可用） ---
        ModelPreset(
            modelId="deepseek-chat",
            name="DeepSeek Chat (Legacy)",
            context_length=128_000,
            max_output_tokens=8_192,
            supported_parameters=[
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "frequency_penalty",
                "presence_penalty",
                "stop",
            ],
        ),
        ModelPreset(
            modelId="deepseek-reasoner",
            name="DeepSeek Reasoner (Legacy)",
            context_length=128_000,
            max_output_tokens=8_192,
            supported_parameters=[
                "temperature",
                "top_p",
                "max_tokens",
                "max_completion_tokens",
                "frequency_penalty",
                "presence_penalty",
                "stop",
            ],
        ),
    ],
    "api.z.ai": (
        _GLM_SHARED_CHAT_MODELS + _GLM_ZAI_ONLY_MODELS
    ),
    "open.bigmodel.cn": (
        _GLM_SHARED_CHAT_MODELS + _GLM_BIGMODEL_ONLY_MODELS
    ),
    "api.moonshot.cn": [
        # === Kimi K3（旗舰，1M 上下文，始终思考，reasoning_effort 控制深度） ===
        ModelPreset(
            modelId="kimi-k3",
            name="Kimi K3",
            context_length=1_000_000,
            max_output_tokens=1_048_576,
            input_modalities=["text", "image", "video"],
            supported_parameters=[
                "max_completion_tokens", "stop",
                "kimi::reasoning_effort",
            ],
        ),
        # === Kimi K2.7 Code（始终思考，始终保留上下文） ===
        ModelPreset(
            modelId="kimi-k2.7-code",
            name="Kimi K2.7 Code",
            context_length=256_000,
            max_output_tokens=32_768,
            input_modalities=["text", "image", "video"],
            supported_parameters=[
                "temperature", "top_p", "max_tokens", "max_completion_tokens",
                "frequency_penalty", "presence_penalty", "stop",
                "kimi::thinking.keep",
            ],
        ),
        ModelPreset(
            modelId="kimi-k2.7-code-highspeed",
            name="Kimi K2.7 Code HighSpeed",
            context_length=256_000,
            max_output_tokens=32_768,
            input_modalities=["text", "image", "video"],
            supported_parameters=[
                "temperature", "top_p", "max_tokens", "max_completion_tokens",
                "frequency_penalty", "presence_penalty", "stop",
                "kimi::thinking.keep",
            ],
        ),
        # === Kimi K2.6（可选思考 + 可选保留上下文） ===
        ModelPreset(
            modelId="kimi-k2.6",
            name="Kimi K2.6",
            context_length=256_000,
            max_output_tokens=32_768,
            input_modalities=["text", "image", "video"],
            supported_parameters=[
                "temperature", "top_p", "max_tokens", "max_completion_tokens",
                "frequency_penalty", "presence_penalty", "stop",
                "kimi::thinking.type",
                "kimi::thinking.keep",
            ],
        ),
        # === Kimi K2.5（可选思考，无 Preserved Thinking） ===
        ModelPreset(
            modelId="kimi-k2.5",
            name="Kimi K2.5",
            context_length=256_000,
            max_output_tokens=32_768,
            input_modalities=["text", "image", "video"],
            supported_parameters=[
                "temperature", "top_p", "max_tokens", "max_completion_tokens",
                "frequency_penalty", "presence_penalty", "stop",
                "kimi::thinking.type",
            ],
        ),

    ],
}
