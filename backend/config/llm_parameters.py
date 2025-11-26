# backend/config/llm_parameters.py

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Any, Literal

# --- 1. 参数结构定义 ---

class LLMParameter(BaseModel):
    """
    定义一个LLM参数的完整结构，用于系统内部的管理、校验和前端UI生成。
    """
    key: str = Field(..., description="唯一的参数标识符，用于数据库存储和内部引用。例如：'temperature' 或 'openai::tool_choice'。")
    label: str = Field(..., description="在前端UI中展示给用户的名称。例如：'Temperature'。")
    path: List[str] = Field(..., description="用于构建最终API请求体的路径。例如：['temperature'] 或 ['tool_config', 'tool_choice']。")
    description: str = Field(..., description="参数功能的详细描述，供前端UI展示。")
    type: Literal['integer', 'number', 'string', 'boolean'] = Field(..., description="参数值的数据类型。")
    limit: Optional[Union[List[Any], dict[str, float]]] = Field(None, description="值的约束。对于string类型，是枚举值列表；对于number/integer类型，是包含 'min' 和 'max' 的字典。")
    default_value: Any = Field(..., description="参数被启用时的默认值。")
    default_activate: bool = Field(..., description="在新创建的Chat中，此参数是否默认启用并包含在 modelParameters 中。")


# --- 2. 系统支持的LLM参数列表 ---

SUPPORTED_LLM_PARAMETERS: List[LLMParameter] = [
    # --- 常用核心参数 (默认激活) ---
    LLMParameter(
        key="temperature",
        label="Temperature",
        path=["temperature"],
        description="控制生成文本的随机性。值越高，输出越随机、越有创意；值越低，输出越确定、越保守。",
        type="number",
        limit={"min": 0.0, "max": 2.0},
        default_value=0.7,
        default_activate=True
    ),
    LLMParameter(
        key="top_p",
        label="Top P (Nucleus Sampling)",
        path=["top_p"],
        description="一种替代温度采样的方法。模型会考虑累积概率超过 P 值的最小词汇集。建议与 Temperature 只使用其一。",
        type="number",
        limit={"min": 0.0, "max": 1.0},
        default_value=1.0,
        default_activate=True
    ),

    # --- 常用核心参数 (默认不激活) ---
    LLMParameter(
        key="max_tokens",
        label="Max Tokens",
        path=["max_tokens"],
        description="单次请求中，模型生成的最大token数量。这会影响回复的长度。",
        type="integer",
        limit={"min": 1},
        default_value=4096,
        default_activate=False
    ),
    LLMParameter(
        key="seed",
        label="Seed",
        path=["seed"],
        description="一个整数，用于确保可复现的输出。当设置相同时，对于相同的输入，多次请求将返回相同的结果（尽力而为）。",
        type="integer",
        limit={"min": 0},
        default_value=None,
        default_activate=False
    ),
    LLMParameter(
        key="top_k",
        label="Top K",
        path=["top_k"],
        description="在每一步生成时，限制模型从概率最高的 K 个词中进行选择。这可以减少生成低概率词汇的可能性。",
        type="integer",
        limit={"min": 0},
        default_value=None,
        default_activate=False
    ),
    LLMParameter(
        key="openrouter::image_config.aspect_ratio",
        label="Image Aspect Ratio (OpenRouter)",
        path=["image_config", "aspect_ratio"],
        description="（示例）用于图像生成模型，控制生成图像的宽高比。",
        type="string",
        limit=["1:1","2:3","3:2","3:4","4:3","4:5","5:4","16:9","9:16","21:9"],
        default_value="1:1",
        default_activate=False
    ),
]


# --- 3. 预设服务商列表 ---

DEFAULT_PROVIDERS: List[dict[str, str]] = [
    {
        "name": "OpenAI",
        "apiHost": "https://api.openai.com/v1"
    },
    {
        "name": "Gemini",
        "apiHost": "https://generativelanguage.googleapis.com/v1beta/openai"
    },
    {
        "name": "OpenRouter",
        "apiHost": "https://openrouter.ai/api/v1"
    },
    {
        "name": "DeepSeek",
        "apiHost": "https://api.deepseek.com/v1"
    },
    {
        "name": "SiliconFlow",
        "apiHost": "https://api.siliconflow.cn/v1/"
    },
    {
        "name": "Local LLM (LM Studio)",
        "apiHost": "http://localhost:1234/v1"
    }
]
