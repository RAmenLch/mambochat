# CHANGELOG

## [1.4.7]
**一个 Agent 可同时挂多个生图配置：LLM 通过 `image_generator` 参数按名称选择**。

### 🎨 多生图配置（Agent 侧多选）

- Agent 的「生图配置」从单选改为**多选**：`agentParameters.image_gen.configIds: string[]`，
  **顺序即优先级，第一个为默认**
- 历史数据零迁移：旧的单 `configId` 在读取时自动归一化进 `configIds`
- 不可用（未启用 / 绑定失效 / 构建失败）的配置在装配期**跳过并记日志**，
  不让一个坏配置拖垮整个 Agent 的生图能力；名称为空/重复时保留先出现的那个

### 🖼️ 新增平台侧参数 `image_generator`

- `image_generate` 与 `image_generate_show` 各多一个参数 `image_generator`
  （配置**名称**，留空即用该工具候选里的第一个）
- 名称匹配容错：去首尾空白、压缩全角空格、忽略大小写；匹配不到时**报错并列出
  可用名称**（不静默回退）
- `image_task_status` / `image_download` 不加参数：中间件在同一次运行内按 `task_id`
  记住提交它的配置，查不到时回退默认配置

### 💬 工具描述注入可用清单

- 工具描述末尾追加由配置快照**确定性**渲染的清单（顺序 = Agent 配置顺序，KV cache 安全）：
  逐个配置列出名称、说明（截断 120 字）、该配置的 `extra` 参数提示（截断 200 字）
  与异步后端行为说明
- 候选清单**按工具分别计算**：`image_generate` 只列开了标准三件套的配置，
  `image_generate_show` 只列开了一条龙的配置，LLM 无法选到不支持的组合
- 参考图参数：任一配置支持即暴露；选中不支持者由标准实现返回可读错误

### 🔁 异步下载与重跑

- 异步一条龙的 pending 结果新增 `image_generator`，落进
  `SubMessageConfig.pending_image_generator`；后台轮询器据此用**同一个配置**驱动下载
  （此前会话里只有一个配置，重连/多任务并发时会用错后端）
- 该配置之后被停用/删除时回退默认配置继续尝试，超时兜底不变
- 重跑复用 `image_run_args` 参数快照：有 `image_generator` 就用它，老快照用默认配置

### 🧱 代码结构

- 新增 `agent/image_gen/registry.py`：`ImageGenEntry`（名称 + 说明 + 实现 + 支持的工具体）、
  `pick_generator`（按名称选配置）、`build_generator_catalog`（渲染描述清单）
- `ImageGenMiddleware` 由「持有一个实现」改为「持有一组配置」，按参数分派；
  工具名不变（仍是 4 个固定名），前端工具渲染 / tail tool / HITL 零改动
- `AgentConfig.image_gen_standard` → `image_gen_standards: List[ImageGenEntry]`
- `ImageGenStandard` 新增 `generator_name`；`build_image_gen_entries()` 统一按顺序装配

### ⚠️ 兼容性

- 无数据库迁移：`agentParameters` 与子消息 `config` 都是 JSON 列，新增字段可选
- 单配置 + 不传 `image_generator` 时行为与旧版一致（工具描述多出清单段落）
