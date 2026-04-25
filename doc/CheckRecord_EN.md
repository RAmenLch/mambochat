# MamboChat Model Feature Verification Records

## 1. SiliconFlow https://api.siliconflow.cn/v1/
### Pro/deepseek-ai/DeepSeek-R1 (OpenAI Compatible)
| Feature  | Verified |
|-----|--|
| Chain of Thought Output |✔| 
 | Tool Calling|✔|

### Pro/zai-org/GLM-4.7 (OpenAI Compatible)
| Feature  | Verified |
|-----|--|
| Chain of Thought Output |✔| 
 | Tool Calling|✔|

### zai-org/GLM-4.6V (OpenAI Compatible)
| Feature | Verified | Notes |
|----|--|--|
| Chain of Thought Output |✔| 
| Image Input| ✔| Requires `image` input modality config |

### deepseek-ai/DeepSeek-V3.2 (OpenAI Compatible)
| Feature      | Verified |
|---------|--|
| Chain of Thought Output   |✔| 
| Tool Calling (CoT) |✔|

### Qwen/Qwen3-Embedding-8B (Embedding)
| Feature       | Verified |
|----------|--|
| Embedding (4096 dims) |✔|


## 2. OpenRouter https://openrouter.ai/api/v1
### google/gemini-3-pro-preview (OpenAI Compatible)
| Feature | Verified |
|----|--|
| Chain of Thought Output |✔| 
| Image Input| ✔|
| Tool Calling|✔|

### google/gemini-3-pro-image-preview (OpenAI Compatible)
| Feature    | Verified |
|-------|--|
| Chain of Thought Output |✔| 
| Image Input  | ✔|
| Image Output  | ✔|

### openai/gpt-5-image-mini (OpenAI Compatible)
| Feature    | Verified |
|-------|--|
| Chain of Thought Output |✔| 
| Image Input  | ✔|
| Image Output  | ✔|

### anthropic/claude-opus-4.6 (Anthropic Native)
| Feature    | Verified | Notes                        |
|-------|--|---------------------------|
| Chain of Thought Output |✔| Default 32000 tokens, adjustable via `thinking` param | 
| Image Input  | ✔|                           |
| Tool Calling|✔|                           |



## 3. Google 

### models/gemini-3-flash-preview (OpenAI Compatible https://generativelanguage.googleapis.com/v1beta/openai/)
| Feature | Verified |
|----|----|
| Chain of Thought Output | ✔  | 
| Image Input| ✔  |
| Tool Calling| ✘  |

### models/gemini-3-flash-preview (Google Gemini Native https://generativelanguage.googleapis.com/v1beta/) 
| Feature | Verified | Notes                        |
|----|----|---------------------------|
| Chain of Thought Output | ✔  | Enabled by default, adjustable via `includeThoughts` | 
| Image Input| ✔  | Requires `image` input modality config            |
| Tool Calling|  ✔   |

## 4. DeepSeek https://api.deepseek.com/v1

### deepseek-chat [deepseek-v4-flash] (DeepSeek Native)
| Feature | Verified |
|----|----|
| Tool Calling|  ✔   |

### deepseek-reason [deepseek-v4-flash] (DeepSeek Native)
| Feature        | Verified |
|-----------|-|
| Chain of Thought Output | ✔ |
| Tool Calling (CoT) |✔|

### deepseek-v4-flash (DeepSeek Native)
| Feature        | Verified | Notes                                                               |
|-----------|----|------------------------------------------------------------------|
| Chain of Thought Output     | ✔  | Can be disabled via Thinking Type (DeepSeek); adjustable via Reasoning Effort (DeepSeek) |
| Tool Calling (CoT) | ✔  |                                                                  |

### deepseek-v4-pro (DeepSeek Native)
| Feature        | Verified | Notes                                                               |
|-----------|----|------------------------------------------------------------------|
| Chain of Thought Output     | ✔  | Can be disabled via Thinking Type (DeepSeek); adjustable via Reasoning Effort (DeepSeek) |
| Tool Calling (CoT) | ✔  |                                                                  |
