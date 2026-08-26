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
    path: List[str] = Field(..., description="用于构建最终API请求体的路径。例如：['temperature'] 或 ['tool_config', 'tool_choice']。若以 'extra_body' 开头（如 ['extra_body', 'thinking', 'type']），该参数经请求体的 extra_body 字段传递，用于非 OpenAI 标准扩展参数。")
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
        description="单次请求中，模型生成的最大token数量。这会影响回复的长度。部分新模型推荐使用 max_completion_tokens 替代此参数。",
        type="integer",
        limit={"min": 1},
        default_value=4096,
        default_activate=False
    ),
    LLMParameter(
        key="max_completion_tokens",
        label="Max Completion Tokens",
        path=["max_completion_tokens"],
        description="指定模型生成的最大完成token数（含推理token）。这是 max_tokens 的新版替代参数，部分新模型（如 GPT-4.1 系列）推荐使用此参数。",
        type="integer",
        limit={"min": 1},
        default_value=4096,
        default_activate=False
    ),
    LLMParameter(
        key="frequency_penalty",
        label="Frequency Penalty",
        path=["frequency_penalty"],
        description="降低模型重复使用已在文本中出现过的词的概率。值越高，越倾向于使用新词汇，减少重复。范围 -2.0 到 2.0。",
        type="number",
        limit={"min": -2.0, "max": 2.0},
        default_value=0,
        default_activate=False
    ),
    LLMParameter(
        key="presence_penalty",
        label="Presence Penalty",
        path=["presence_penalty"],
        description="增加模型谈论新话题的倾向。值越高，越倾向于引入新概念，增加话题多样性。范围 -2.0 到 2.0。",
        type="number",
        limit={"min": -2.0, "max": 2.0},
        default_value=0,
        default_activate=False
    ),
    LLMParameter(
        key="repetition_penalty",
        label="Repetition Penalty",
        path=["repetition_penalty"],
        description="对已生成的token施加惩罚因子。值大于1时，降低重复生成相同token的概率；值等于1时无惩罚。常用于开源模型（如 Llama、Qwen）。",
        type="number",
        limit={"min": 1.0, "max": 2.0},
        default_value=1.0,
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
        key="min_p",
        label="Min P",
        path=["min_p"],
        description="设置token概率的最小阈值。只有概率不小于最可能token概率的P倍的token才会被考虑。值越低，采样范围越广。范围 0.0 到 1.0。",
        type="number",
        limit={"min": 0.0, "max": 1.0},
        default_value=0.1,
        default_activate=False
    ),
    LLMParameter(
        key="stop",
        label="Stop Sequences",
        path=["stop"],
        description="当模型生成指定的停止序列时停止输出。可以传入最多4个字符串，以逗号分隔输入。",
        type="string",
        limit=None,
        default_value=None,
        default_activate=False
    ),
    LLMParameter(
        key="openrouter::image_config.aspect_ratio",
        label="Image Aspect Ratio (OpenRouter)",
        path=["extra_body", "image_config", "aspect_ratio"],
        description="用于图像生成模型，控制生成图像的宽高比。传 auto 由服务商自动选择，或指定具体比例（如 16:9、9:16）。服务商会收敛到其支持的子集。",
        type="string",
        limit=["auto","1:1","1:2","2:1","1:4","4:1","1:8","8:1","2:3","3:2","3:4","4:3","4:5","5:4","16:9","9:16","9:21","21:9"],
        default_value="1:1",
        default_activate=False
    ),

    # --- OpenRouter 图像生成参数（经 extra_body.image_config 传递）---
    # key 使用 OpenRouter 原始参数名，使其在 fetch_models 时能被服务商返回的
    # supported_parameters 自动匹配挂载到图片模型上。
    LLMParameter(
        key="quality",
        label="Image Quality (OpenRouter)",
        path=["extra_body", "image_config", "quality"],
        description="图像生成质量等级。auto 由服务商自动选择；low/medium/high 指定质量。不支持质量档位的服务商会忽略此参数。",
        type="string",
        limit=["auto", "low", "medium", "high"],
        default_value="auto",
        default_activate=False
    ),
    LLMParameter(
        key="output_format",
        label="Image Output Format (OpenRouter)",
        path=["extra_body", "image_config", "output_format"],
        description="图像输出格式：png / jpeg / webp / svg（svg 仅矢量模型支持）。省略时使用服务商默认格式。",
        type="string",
        limit=["png", "jpeg", "webp", "svg"],
        default_value="png",
        default_activate=False
    ),
    LLMParameter(
        key="background",
        label="Image Background (OpenRouter)",
        path=["extra_body", "image_config", "background"],
        description="图像背景处理：transparent 需要支持透明通道的格式（png/webp），opaque 为不透明背景。",
        type="string",
        limit=["auto", "transparent", "opaque"],
        default_value="auto",
        default_activate=False
    ),
    LLMParameter(
        key="output_compression",
        label="Image Compression (OpenRouter)",
        path=["extra_body", "image_config", "output_compression"],
        description="webp/jpeg 格式的压缩级别（0-100），数值越低质量越高文件越大；png 忽略此参数。",
        type="integer",
        limit={"min": 0, "max": 100},
        default_value=90,
        default_activate=False
    ),
    LLMParameter(
        key="size",
        label="Image Size (OpenRouter)",
        path=["extra_body", "image_config", "size"],
        description="图像尺寸简写：分辨率档位（如 2K）或显式像素（如 2048x2048）。显式像素为最终尺寸，勿与 aspect_ratio 同时设置。",
        type="string",
        limit=None,
        default_value=None,
        default_activate=False
    ),
    LLMParameter(
        key="gemini::includeThoughts",
        label="includeThoughts(Gemini)",
        path=["include_thoughts"],
        description="是否在响应中输出 Gemini 模型的思考过程。",
        type="boolean",
        limit=[True,False],
        default_value=True,
        default_activate=False
    ),
    LLMParameter(
        key="gemini::reasoning_effort",
        label="Reasoning Effort (Gemini)",
        path=["reasoning_effort"],
        description="控制 Gemini 模型的推理努力级别。值越高，推理越深入但响应越慢。",
        type="string",
        limit=["minimal","low","medium","high"],
        default_value="medium",
        default_activate=False
    ),
    LLMParameter(
        key="reasoning",
        label="Reasoning Effort (OpenRouter)",
        path=["reasoning","effort"],
        description="通过 OpenRouter 的嵌套结构控制推理努力级别。映射为 {reasoning: {effort: value}}。值越高，推理越深入但响应越慢。",
        type="string",
        limit=["minimal","low","medium","high"],
        default_value="medium",
        default_activate=False
    ),
    LLMParameter(
        key="include_reasoning",
        label="Include Reasoning",
        path=["include_reasoning"],
        description="当模型支持推理模式时，是否在响应中返回推理过程（thinking/reasoning 内容）。",
        type="boolean",
        limit=[True, False],
        default_value=True,
        default_activate=False
    ),
    LLMParameter(
        key="anthropic::thinking.type",
        label="Thinking Type (Anthropic)",
        path=["thinking", "type"],
        description="是否启用 Anthropic 扩展思考模式。启用后须同时设置 thinking.budget_tokens。",
        type="string",
        limit=["enabled","disabled"],
        default_value="enabled",
        default_activate=False
    ),
    LLMParameter(
        key="anthropic::thinking.budget_tokens",
        label="Thinking Budget Tokens (Anthropic)",
        path=["thinking", "budget_tokens"],
        description="Anthropic 扩展思考模式的最大 token 预算。须同时启用 thinking.type(Anthropic)。",
        type="integer",
        limit={"min": 1000,"max":32000},
        default_value=2048,
        default_activate=False
    ),
    LLMParameter(
        key="anthropic::verbosity",
        label="Verbosity (Anthropic)",
        path=["verbosity"],
        description="控制 Anthropic 模型输出的详细程度。",
        type="string",
        limit=["concise", "default", "verbose"],
        default_value="default",
        default_activate=False
    ),
    LLMParameter(
        key="deepseek::thinking.type",
        label="Thinking Type (DeepSeek)",
        path=["thinking", "type"],
        description="控制 DeepSeek V4 思考模式开关。启用后模型会在输出最终回答前先进行思维链推理。注意：思考模式下 temperature/top_p/presence_penalty/frequency_penalty 不生效。",
        type="string",
        limit=["enabled", "disabled"],
        default_value="enabled",
        default_activate=False
    ),
    LLMParameter(
        key="deepseek::reasoning_effort",
        label="Reasoning Effort (DeepSeek)",
        path=["reasoning_effort"],
        description="控制 DeepSeek V4 思考模式的推理强度。high 为常规深度思考，max 为最强推理（适合复杂 Agent 场景）。仅当 Thinking Type 为 enabled 时生效。",
        type="string",
        limit=["high", "max"],
        default_value="high",
        default_activate=False
    ),

    # --- GLM / Z.AI / 智谱 特有参数 ---
    LLMParameter(
        key="glm::thinking.type",
        label="Thinking Type (GLM)",
        path=["thinking", "type"],
        description="控制 GLM 模型（4.5 及以上）的思维链开关。启用后，GLM-5.x/4.6+ 由模型自行判断是否思考，GLM-4.7/4.5V 则强制思考。",
        type="string",
        limit=["enabled", "disabled"],
        default_value="enabled",
        default_activate=False
    ),
    LLMParameter(
        key="glm::thinking.clear_thinking",
        label="Clear Thinking History (GLM)",
        path=["thinking", "clear_thinking"],
        description="控制是否清除历史回合中的 reasoning_content（思考内容）。开启可减少上下文长度和成本（推荐），关闭则保留全部历史思考。",
        type="boolean",
        limit=[True, False],
        default_value=True,
        default_activate=False
    ),
    LLMParameter(
        key="glm::reasoning_effort",
        label="Reasoning Effort (GLM)",
        path=["reasoning_effort"],
        description="控制 GLM-5.2/5.3 思考模式的推理深度。GLM-5.3 仅支持 low/high/max 且始终思考；GLM-5.2 支持 none/minimal/low/medium/high/xhigh/max。仅当 Thinking Type 为 enabled 时生效。",
        type="string",
        limit=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        default_value="max",
        default_activate=False
    ),
    LLMParameter(
        key="glm::do_sample",
        label="Do Sample (GLM)",
        path=["do_sample"],
        description="是否启用采样。关闭时 temperature、top_p 等采样参数失效，输出更确定。GLM 默认开启。",
        type="boolean",
        limit=[True, False],
        default_value=True,
        default_activate=False
    ),
    LLMParameter(
        key="glm::tool_stream",
        label="Tool Stream (GLM)",
        path=["tool_stream"],
        description="是否对 Function Calls 启用流式响应。仅 GLM-4.6 及以上版本支持。",
        type="boolean",
        limit=[True, False],
        default_value=False,
        default_activate=False
    ),

    # --- Kimi (Moonshot) 特有参数 ---
    LLMParameter(
        key="kimi::thinking.type",
        label="Thinking Type (Kimi)",
        path=["extra_body", "thinking", "type"],
        description="控制 Kimi K2.5/K2.6 可选思考模式开关。enabled 开启，disabled 关闭。",
        type="string",
        limit=["enabled", "disabled"],
        default_value="enabled",
        default_activate=False
    ),
    LLMParameter(
        key="kimi::thinking.keep",
        label="Preserved Thinking (Kimi)",
        path=["extra_body", "thinking", "keep"],
        description="控制是否将历史轮次的推理内容保留在上下文中。仅 Kimi K2.6 支持可选（设为 'all' 启用），K2.7 Code 始终启用且不可关闭。",
        type="string",
        limit=["all"],
        default_value="all",
        default_activate=False
    ),
    LLMParameter(
        key="kimi::reasoning_effort",
        label="Reasoning Effort (Kimi K3)",
        path=["reasoning_effort"],
        description="控制 Kimi K3 模型的思考深度。K3 始终开启思考模式，此参数控制力度：low=快速推理，high=深度推理，max=最强推理（默认）。注意：K3 的 temperature 固定为 1.0、top_p 固定为 0.95，不建议显式传入。",
        type="string",
        limit=["low", "high", "max"],
        default_value="max",
        default_activate=False
    ),

]


# --- 3. 预设服务商列表 ---

DEFAULT_PROVIDERS: List[dict[str, str]] = [
    {
        "name": "OpenAI",
        "apiHost": "https://api.openai.com/v1",
        "worker_type": "openai"
    },
    {
        "name": "Gemini (OpenAI Compatible)",
        "apiHost": "https://generativelanguage.googleapis.com/v1beta/openai",
        "worker_type": "openai"
    },
    {
        "name": "Gemini (Native)",
        "apiHost": "https://generativelanguage.googleapis.com/v1beta",
        "worker_type": "google"
    },
    {
        "name": "OpenRouter",
        "apiHost": "https://openrouter.ai/api/v1",
        "worker_type": "openai"
    },
    {
        "name": "DeepSeek",
        "apiHost": "https://api.deepseek.com/v1",
        "worker_type": "deepseek"
    },
    {
        "name": "SiliconFlow",
        "apiHost": "https://api.siliconflow.cn/v1/",
        "worker_type": "openai"
    },
    {
        "name": "Z.AI (GLM)",
        "apiHost": "https://api.z.ai/api/paas/v4",
        "worker_type": "openai"
    },
    {
        "name": "智谱 BigModel (GLM)",
        "apiHost": "https://open.bigmodel.cn/api/paas/v4",
        "worker_type": "openai"
    },
    {
        "name": "Kimi (Moonshot)",
        "apiHost": "https://api.moonshot.cn/v1",
        "worker_type": "openai"
    },
    {
        "name": "Local LLM (LM Studio)",
        "apiHost": "http://localhost:1234/v1",
        "worker_type": "openai"
    }
]
