# CHANGELOG

## [1.4.0] - 2026-11-02
**生图模型类型与服务商级执行器：把「纯生图接口」接入生图标准**。

### 🎨 新增生图模型类型（`model_type=image`）

- **模型类型三选一**：会话模型 / 向量模型 / 生图模型。生图模型用于非对话的纯生图，
  不会出现在会话的模型选择器里，也不能被会话使用（后端双重校验）
- **服务商级执行器**：新增 `worker_type`：`openai_images` / `openrouter_images`。
  同一服务商下的多个生图模型共用执行器与 URL，只有 `modelId` 与少量默认参数不同
    - `openai_images` → `{apiHost}/images/generations`，有参考图时 `/images/edits`（multipart）
    - `openrouter_images` → `{apiHost}/images`，参考图走 `input_references`
- **模型能力与默认参数**：`meta_config.image_options`（quality / output_format /
  aspect_ratio / background / output_compression / seed）、`meta_config.image_capabilities`
  （拉取模型或检测时回填 `supported_parameters` 描述符，用于参数二次裁剪）
- **拉取模型自动分流**：生图执行器服务商向 `/images/models`（OpenRouter）或 `/models`
  取列表，返回的模型默认 `model_type=image`
- **宽松挂载**：生图模型也可挂在普通对话服务商下，执行器按 `worker_type` / `apiHost`
  自动推导；推导不出时提示为该模型单独建生图服务商

### 🖼️ 生图配置新增第三后端（`backendType=image_api`）

- 生图配置页后端类型三选一：MCP 服务 / 对话出图模型 / 生图模型
- 新增实现类 `ImageApiImageGenStandard`，完整实现生图标准三原语：任务磁盘持久化、
  逐张并发（n=1 × count）、单张失败重试一次、部分成功仍 `completed`、`wait_timeout`
  短轮询、24h 清理，与既有 MCP / Chat 模型后端行为一致
- 「检测」只做 GET 探测（校验 Key、确认模型存在、回填能力），不触发真实生成、不产生费用
- 参考图完整实现：OpenAI 走 `/images/edits` 多部分上传，OpenRouter 走 `input_references`

### 💬 参数提示与行为护栏

- **额外参数提示**：`image_generate` / `image_generate_show` 的工具描述末尾追加该模型支持的
  `extra` 参数与值域（来自 `meta_config.image_capabilities` 快照）。渲染完全确定性
  （键与枚举值排序、固定截断：每个枚举 ≤12 值、整段 ≤320 字符），不发网络请求、不读运行时
  状态 —— 用户不主动改配置，会话前缀不变，KV cache 安全
- **能力空白不猜**：模型未声明 `supported_parameters` 时提示"未知键会被忽略"，且不下发任何
  `extra` 键（只发 `prompt` / `n` / `resolution`）
- **参考图必需**：`input_references.min >= 1` 的编辑类模型（如 `krea/k3-edit`、
  `recraft/recraft-v4-styles-*`）强制按「支持」处理，未带参考图时直接返回可读错误，
  不再把必然失败的请求发给服务商
- 该两项仅作用于 `image_api` 后端；MCP 与对话出图后端的工具描述逐字节不变

### 🧱 代码结构

- 新增 `backend/services/generation/image_executors/`（与 `worker/`、`managers/` 同级）：
  执行器层只做 HTTP 协议适配，不依赖 agent 包，依赖方向保持 `agent → image_executors`
- `agent/image_gen/` 只保留标准实现类与 agent 工具；`factory` 按后端类型三分支装配

### ⚠️ 兼容性

- 无数据库迁移：`model_type` / `worker_type` 皆为字符串列，`meta_config` 为 TEXT
- 旧的 `mcp` / `model` 配置、会话模型列表、向量模型、图片重跑接口行为均不变
