# 常用模型在MamboChat主要功能测试记录

## 1.硅基流动 https://api.siliconflow.cn/v1/
### Pro/deepseek-ai/DeepSeek-R1 (OpenAI Compatible)
| 功能  |验证|
|-----|--|
| 思维链输出 |✔| 
 | 工具调用|✔|
### Pro/zai-org/GLM-4.7 (OpenAI Compatible)
| 功能  |验证|
|-----|--|
| 思维链输出 |✔| 
 | 工具调用|✔|
### zai-org/GLM-4.6V (OpenAI Compatible)
| 功能 |验证|备注|
|----|--|--|
| 思维链输出 |✔| 
|图片输入| ✔|需配置支持输入模态image|

### deepseek-ai/DeepSeek-V3.2(OpenAI Compatible)
| 功能      |验证|
|---------|--|
| 思维链输出   |✔| 
| 工具调用(思维链) |✔|

### Qwen/Qwen3-Embedding-8B (Embedding)
| 功能       |验证|
|----------|--|
| 词嵌入(4096维) |✔|


## 2.OpenRouter https://openrouter.ai/api/v1
### google/gemini-3-pro-preview(OpenAI Compatible)
| 功能 |验证|
|----|--|
| 思维链输出 |✔| 
|图片输入| ✔|
| 工具调用|✔|

### google/gemini-3-pro-image-preview(OpenAI Compatible)
| 功能    |验证|
|-------|--|
| 思维链输出 |✔| 
| 图片输入  | ✔|
| 图片输出  | ✔|

### openai/gpt-5-image-mini(OpenAI Compatible)
| 功能    |验证|
|-------|--|
| 思维链输出 |✔| 
| 图片输入  | ✔|
| 图片输出  | ✔|

### anthropic/claude-opus-4.6(Anthropic Native)
| 功能    |验证| 备注                        |
|-------|--|---------------------------|
| 思维链输出 |✔| 默认启用32000额度,可调整thinking参数 | 
| 图片输入  | ✔|                           |
| 工具调用|✔|                           |



## 3. 谷歌 

### models/gemini-3-flash-preview(OpenAI Compatible https://generativelanguage.googleapis.com/v1beta/openai/)
| 功能 | 验证 |
|----|----|
| 思维链输出 | ✔  | 
|图片输入| ✔  |
| 工具调用| ✘  |

### models/gemini-3-flash-preview(Google Gemini Native https://generativelanguage.googleapis.com/v1beta/) 
| 功能 | 验证 | 备注                        |
|----|----|---------------------------|
| 思维链输出 | ✔  | 默认启用,可调整includeThoughts参数 | 
|图片输入| ✔  | 需配置支持输入模态image            |
| 工具调用|  ✔   |

## 4. DeepSeek https://api.deepseek.com/v1

### deepseek-chat[DeepSeek-V3.2] (DeepSeek Native)
| 功能 | 验证 |
|----|----|
| 工具调用|  ✔   |

### deepseek-reason[DeepSeek-V3.2] (DeepSeek Native)
| 功能        | 验证 |
|-----------|-|
| 思维链输出 | ✔ | 
| 工具调用(思维链) |✔|