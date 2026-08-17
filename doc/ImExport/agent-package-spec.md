# MamboChat Agent 导出包规范 v1

## 1. 概述

本规范定义 MamboChat Agent 分享文件的格式：一个 gzip 压缩的 JSON 文件，包含 Agent（含 subAgent 闭包）及其完整依赖（服务商+模型、资源树、MCP、Resource / Local Backend、二进制载荷），用于在不同 MamboChat 实例之间迁移。

- 文件扩展名：`.mamboagent`
- 编码：UTF-8
- 内部实现：gzip 压缩的 JSON 文档（文件头为 gzip 魔数 `1f 8b`，任何解压工具均可识别）
- 顶层格式标识：`format = "mambochat.agent-package"`

## 2. 文件与编码

- 文件为 gzip 压缩的单个 JSON 文档（`application/gzip`）。
- 压缩前 JSON 使用紧凑格式（无多余空白）。
- 二进制载荷（文件内容、头像）以 base64 内嵌于 `blobs[]` 段（见 4.3）。

## 3. 顶层结构

```jsonc
{
  "$schema": "./agent_package_schema_v1.json",
  "format": "mambochat.agent-package",
  "formatVersion": "1.3.0",
  "mambochatVersion": "1.3.0",
  "exportedAt": "2026-05-01T12:00:00+08:00",
  "description": "可选说明",
  "agents":     [],
  "providers":  [],
  "resources":  [],
  "mcpServers": [],
  "backends":   [],
  "blobs":      []
}
```

`$schema` 为可选字段，值指向随应用分发的 JSON Schema 文件（相对路径）。它仅供校验/IDE 提示使用，**导入逻辑不请求、不依赖该地址**；缺失时以 `format` + `formatVersion` 为准。

## 4. 通用约定

### 4.1 sourceId 引用机制

- 包内所有实体（agent / provider / model / resource / resource version / mcp server / backend / blob / **导出端虚拟的容器节点**）均携带 `sourceId`（blob 段以 `blobId` 作为包内引用标识，见 §5.7），值为导出时数据库中的原始 UUID（虚拟容器节点除外，见 §6.3）。
- 跨段引用统一使用 `sourceId` 字符串；引用字段见各段定义。
- 导出端保证包内 `sourceId` 全局唯一。
- 导入端维护 `sourceId → 新UUID` 映射，创建完成后统一重写引用；**引用与名称无关，改名不影响引用解析**。
- **落库 id 一律新生成**：导入时所有新建实体的数据库主键均为新 UUID，绝不直接复用包内 `sourceId`（`sourceId` 仅作为包内引用标识，不落库）。

### 4.2 敏感数据规则

| 数据 | 处理 |
|---|---|
| `AIProvider.apiKey` | 不导出。服务商段**恒**以 `apiKeyMissing: true` 标记（无论 DB 中是否有 key，导出端不做任何判断）。导入端创建服务商时以占位符 `"********"` 写入 apiKey（满足 DB 非空约束，与 Backend 密码脱敏 `PASSWORD_MASK` 同款），导入报告列出全部服务商供 UI 提示补填，补填前该服务商不可用 |
| `McpServer.env` / `headers` | 不导出（字段省略） |
| SSH / API 类型 Backend | 整个实体不导出（含密码 / api_key 等凭据；`backends[]` 仅含 `backendType == "resource" \| "local"`） |
| Local 类型 Backend | 整个实体导出：`configData` 仅含路径配置（`root_dir` / `edit_whitelist` / `edit_blacklist` / `ignore_dirs`），无凭据类敏感字段；`root_dir` 指向导出机本地路径，导入端不校验存在性，导入后用户需确认 / 调整目标机上的 `root_dir` |

### 4.3 blobs 载荷段

- 所有二进制内容（资源文件型版本内容、Agent 头像）统一存放在顶层 `blobs[]` 段，JSON 主体区域保持纯结构、可读。
- 引用方携带元信息（`filename` / `mimeType` / `size`）+ `blobId` 引用。
- 文本型资源（system_prompt / submessage_template）直接以 UTF-8 字符串内联，**不进入 blobs**。
- 导出端按 **File 记录**（即 `blobId`）去重：同一 File 记录被多处引用时只导出一份（引用方共用同一 `blobId`）；不同 File 记录即使内容完全相同也分别导出，**绝不按内容合并**（文件型版本 `content` 指向 File 记录，合并会导致本可独立编辑的文件共享同一 File）。
- 导入端先建立 `blobId → bytes` 索引，再按序创建实体。

## 5. 数据段定义

### 5.1 元信息

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `format` | string | ✅ | 固定 `"mambochat.agent-package"` |
| `formatVersion` | string | ✅ | 格式版本号，值 = 本规范最后一次变更时的 mambochat 版本（当前 `"1.3.0"`）；仅当导入/导出规范本身变更时才 bump（mambochat 版本更新但规范未变则不变）；兼容规则见 §8 |
| `mambochatVersion` | string | ✅ | 导出时的应用版本（如 `"1.3.0"`），导入端据此做兼容性提示 |
| `exportedAt` | string | ✅ | ISO-8601 导出时间 |
| `description` | string | 否 | 人类可读说明 |

### 5.2 `agents[]`

导出入口仅接受单个 Agent（`itemType == "agent"`，不支持文件夹）。导出的 Agent 集合 = 主 Agent + subAgents 递归闭包，**平铺数组**；`subAgents` 仅引用 `itemType == "agent"` 的节点（不含文件夹），闭包内不会出现文件夹节点。字段与后端 `Agent` 表 / `AgentCreate` schema 对齐；**不导出** `parentId` / `sortOrder` / 时间戳。

- **Agent 本体位置**（Agent 树）：主 Agent 导入到目标文件夹；subAgent 平铺进 `<主Agent原名>_subagent` 文件夹（与主 Agent 同级放入目标文件夹，文件夹名固定用主 Agent **原名**；subAgent 自身不处理名称冲突，见 §7.2）。
- **Agent 资源位置**：每个 Agent 的依赖资源由导出端组织进其**资源命名空间**（主 Agent → `<改名后主Agent名>/` 顶层；subAgent → `<改名后主Agent名>/subagents/<subagent名>/`，递归嵌套），见 §6.4。Agent 本体位置与资源位置相互独立。

```jsonc
{
  "sourceId": "agent-uuid",
  "name": "Demo Agent",
  "description": "说明",
  "itemType": "agent",
  "AgentType": "Mambo",
  "systemPrompt": "...",
  "modelParameters": { /* 原样导出 */ },
  "agentParameters": {
    "include_general_purpose": false,
    "enable_planning": true,
    "enable_memory": false,
    "enable_summarization": false,
    "enable_show": true,
    "memory_resource_ids": ["res-uuid"],
    "summarization_config": null,
    "security_review": { "enabled": false, "model_id": "model-uuid" },
    "version_control": { "enabled": false, "auto_snapshot": true },
    "mcp_direct_tool_threshold": 15
  },
  "aiModelId": "model-uuid",
  "agentAvatarId": "blob-uuid",
  "resourcePromptList": ["res-uuid"],
  "enabledMcpIds": ["mcp-uuid"],
  "subAgents": ["agent-uuid"],
  "backendIds": ["backend-uuid"],
  "defaultBackendId": "backend-uuid"
}
```

| 字段 | 引用目标 |
|---|---|
| `aiModelId` | `providers[].models[].sourceId` |
| `agentAvatarId` | `blobs[].blobId`（无头像则省略） |
| `resourcePromptList` | `resources[].sourceId` |
| `enabledMcpIds` | `mcpServers[].sourceId` |
| `subAgents` | `agents[].sourceId`（包内 Agent） |
| `backendIds` / `defaultBackendId` | `backends[].sourceId`；导出时**已清洗**：`backendIds` 仅保留闭包内导出的 resource / local backend，`defaultBackendId` 若非闭包内 resource / local backend 则置 `null`（见 §5.6） |
| `agentParameters.memory_resource_ids` | `resources[].sourceId` |
| `agentParameters.security_review.model_id` | `providers[].models[].sourceId` |

### 5.3 `providers[]`

仅导出被引用到的服务商（`aiModelId` + `security_review.model_id` + KB 根 `attributes.embedding_model_id` 的并集，见 §6.6）。**模型级闭包**：服务商内仅导出被上述引用命中的模型，未引用的模型不导出。模型内嵌于服务商下，模型同样拥有 `sourceId`。

```jsonc
{
  "sourceId": "provider-uuid",
  "name": "OpenAI",
  "apiHost": "https://api.openai.com/v1",
  "use_proxy": false,
  "worker_type": "openai",
  "apiKeyMissing": true,
  "models": [
    {
      "sourceId": "model-uuid",
      "modelId": "gpt-4o",
      "name": "GPT-4o",
      "meta_config": { /* 原样导出 */ },
      "model_type": "chat",
      "starred": false
    }
  ]
}
```

### 5.4 `resources[]`

引用闭包去重后的资源集合，**扁平数组，带全部版本**。字段与后端 `Resource` / `ResourceVersion` 表对齐。

```jsonc
{
  "sourceId": "res-uuid",
  "name": "my-skill",
  "description": null,
  "itemType": "folder",
  "resourceType": "skill",
  "parentId": "parent-res-uuid",
  "sortOrder": 0,
  "kb_id": null,
  "kb_config": null,
  "latestVersionId": "ver-uuid",
  "versions": [
    {
      "sourceId": "ver-uuid",
      "name": "v1",
      "sortOrder": 0,
      "commitMessage": null,
      "contentType": "text",
      "content": "纯文本…",
      "attributes": { /* SubMessageConfig 等，原样导出 */ }
    },
    {
      "sourceId": "ver-uuid-2",
      "name": "v2",
      "sortOrder": 1,
      "contentType": "file",
      "file": {
        "filename": "SKILL.md",
        "mimeType": "text/markdown",
        "size": 1234,
        "blobId": "blob-uuid"
      }
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `parentId` | 包内引用；**指向导出端预先确定的导入目标结构中的父节点**（容器节点或子树内父节点，见 §6.3 / §6.4）。树根（虚拟容器或最顶层资源）为 `null` |
| `kb_id` | **以最终输出的资源文件结构为准**（见 §6.7）：资源位于闭包内某 KB 根（`knowledge_base` 节点）的子树中 → 原样导出，导入端重写为新 KB 根 ID；不在任何 KB 根子树下 → 置 `null` |
| `kb_config` | 与 `kb_id` 同规则：位于 KB 根子树下 → 原样导出并保留（导入后用户重新执行切分 / 向量化）；否则置 `null` |
| `contentType` | 导出端按资源 `resourceType` 推断：`system_prompt` / `submessage_template` → `"text"`（`content` 为直接文本）；`file` → `"file"`（`file` 引用 blob）；KB 根初始配置版本（`knowledge_base`，`content` 为空串）→ `"text"`。**DB 映射**：文件型版本在 DB 中 `content` 列存 File 记录 id（非文件内容），导出时该字段省略、由 `file` 对象承载元信息与 `blobId` 引用；导入时先按 `blobId` 创建 File 记录，再将新 File id 写入版本 `content` 列 |
| `latestVersionId` | 标记 active 版本（`versions[].sourceId`，属包内引用：dry-run 校验存在，导入时重写为新版本 id） |

**虚拟容器节点**：导出端为导入目标结构生成的容器（`<agent名>` / `kb` / `skill` / `prompt` / `memory` / `subagents` / `RB_<backend名>` 等）也以普通资源节点形态出现在 `resources[]` 中：`itemType="folder"`、`resourceType=null`、`kb_id` / `kb_config` / `latestVersionId` 为 `null`、**无 `versions`**，`sourceId` 由导出端生成（不与任何 DB 记录对应，见 §6.3）。导入端将其作为普通 folder 创建，无需区分。

**KB 根节点版本**：KB 根以完整子树形态导出时带版本（DB 中 KB 根的初始配置版本，`content` 为空串，**版本唯一**——KB 根创建后不新增版本），版本 `attributes` **原样导出**（`dimension` / `embedding_rate_limit` 等），其中 `embedding_model_id` 为跨段引用（→ `providers[].models[].sourceId`）：导出端将其所属服务商纳入闭包（§6.6），导入端重写为新模型 id。

**embedding_model_id 悬空**：导出端校验该引用存在 —— 模型已删除时引用悬空，**导出报错**，不导出悬空引用（导入端 dry-run 引用完整性检查仍保留该校验作为防御，见 §7.1 步 4）。

导出时删除文件型版本 `attributes` 中的 `last_ingest_config`（向量索引不迁移，导入后不可 RESUME，需重新 START 切分 / 向量化）。

**KB 子树示例**（KB 根 + 成员文件，位于 `kb/<kb名>/` 容器下，`kb_id` / `kb_config` 随成员保留）：

```jsonc
{
  "sourceId": "kb1",
  "name": "产品文档库",
  "description": null,
  "itemType": "folder",
  "resourceType": "knowledge_base",
  "parentId": "vc-kb",
  "sortOrder": 0,
  "kb_id": null,
  "kb_config": null,
  "latestVersionId": "kv1",
  "versions": [
    {
      "sourceId": "kv1",
      "name": "初始配置",
      "sortOrder": 0,
      "commitMessage": null,
      "contentType": "text",
      "content": "",
      "attributes": {
        "embedding_model_id": "model-uuid",
        "dimension": 1536,
        "embedding_rate_limit": 60
      }
    }
  ]
},
{
  "sourceId": "kf1",
  "name": "产品手册.pdf",
  "description": null,
  "itemType": "resource",
  "resourceType": "file",
  "parentId": "kb1",
  "sortOrder": 0,
  "kb_id": "kb1",
  "kb_config": { "splitter_type": "simple", "chunk_size": 500, "chunk_overlap": 50 },
  "latestVersionId": "kv2",
  "versions": [
    {
      "sourceId": "kv2",
      "name": "v1",
      "sortOrder": 0,
      "commitMessage": null,
      "contentType": "file",
      "file": { "filename": "产品手册.pdf", "mimeType": "application/pdf", "size": 20480, "blobId": "blob-uuid" },
      "attributes": {}
    }
  ]
}
```

> KB 根版本 `attributes.embedding_model_id` 引用 `providers[].models[].sourceId`，其所属服务商必须纳入闭包（§6.6）；成员文件型版本 `attributes` 中的 `last_ingest_config` 已删除。

### 5.5 `mcpServers[]`

不导出 `env` / `headers` 及运行时状态字段（`last_status` / `last_test_at` / `last_error`），其余字段完整。**不导出 McpTool 元数据**（工具 `is_enabled` / `review_mode` 属个人选择，导入后由运行时从 MCP 服务端重新同步）。

```jsonc
{
  "sourceId": "mcp-uuid",
  "name": "filesystem",
  "description": null,
  "transportType": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem"],
  "cwd": null,
  "url": null,
  "timeout": null,
  "sse_read_timeout": null,
  "isEnabled": true
}
```

### 5.6 `backends[]`

仅 `backendType == "resource" | "local"`（ssh / api 含凭据，整个实体不导出，见 §4.2）。两种类型的导出 / 导入规则：

- **resource**：`configData.resource_id` 为资源引用（指向包内 folder 节点，可能是普通 folder、KB 根或 Skill 根——容器归类由挂载来源决定，见 §6.4），导入端映射替换为新资源 id。
- **local**：`configData` 仅含路径配置（`root_dir` / `edit_whitelist` / `edit_blacklist` / `ignore_dirs`），**无任何跨段引用**，导出端原样导出、导入端原样落库；`root_dir` 指向导出机本地路径，导入端不校验存在性，导入后用户需确认 / 调整目标机上的 `root_dir` 配置（见 §4.2）。

**导出端同步清洗 Agent 字段（不做原样导出）**：Agent 的 `backendIds` 仅保留闭包内导出的 backend id（ssh / api 引用移除）；`defaultBackendId` 若非闭包内导出的 backend 则导出为 `null`。导入端无需再过滤，原样落库即可。

```jsonc
// resource 类型（configData.resource_id 为跨段引用）
{
  "sourceId": "backend-uuid",
  "name": "workspace",
  "description": null,
  "backendType": "resource",
  "configData": {
    "resource_id": "res-uuid",
    "edit_whitelist": ["/workspace/"],
    "edit_blacklist": null
  },
  "tools_config": { "execute": { "enabled": false, "require_review": true } }
}
```

```jsonc
// local 类型（configData 无跨段引用，原样导出 / 导入）
{
  "sourceId": "backend-uuid",
  "name": "local_home",
  "description": null,
  "backendType": "local",
  "configData": {
    "root_dir": "~",
    "edit_whitelist": null,
    "edit_blacklist": null,
    "ignore_dirs": [".git", "node_modules"]
  },
  "tools_config": { "execute": { "enabled": false, "require_review": true } }
}
```

### 5.7 `blobs[]`

```jsonc
{
  "blobId": "blob-uuid",
  "filename": "SKILL.md",
  "mimeType": "text/markdown",
  "size": 1234,
  "encoding": "base64",
  "data": "aGVsbG8gd29ybGQ="
}
```

`size` 为原始字节数；导入端解码后校验与 `size` 一致（**以 `blobs[].size` 为校验权威**；§5.4 版本 `file.size` 为导出冗余信息，不参与校验）。

## 6. 导出规则（闭包与目标结构）

### 6.1 Agent 闭包

主 Agent（`itemType == "agent"`）+ `subAgents` 递归展开（去重）。**Agent 本体位置导出后不再携带**（`parentId` / `sortOrder` 不导出），由导入端按 §5.2 固定规则放置。

### 6.2 Backend 闭包

Agent 闭包内所有 Agent 的 `backendIds` 中 `backendType == "resource" | "local"` 的并集（去重）；ssh / api 类型不导出（含凭据，见 §4.2）。**导出时同步清洗 Agent 字段**：`backendIds` 仅保留闭包内 id（ssh / api 引用移除），`defaultBackendId` 若非闭包内 id 则导出为 `null`（见 §5.6）。

### 6.3 资源闭包与目标结构（导出端预先确定）

资源闭包的来源（按 Agent 逐个收集，主 Agent 与每个 subAgent 各一份）：

- `resourcePromptList` 引用的资源；
- `agentParameters.memory_resource_ids` 引用的资源；
- `backends[]`（仅 resource 类型）`configData.resource_id` 引用的 folder（local 类型不挂载资源，不进入资源闭包）。

**导出端预先构建"导入目标结构"**：在包内虚拟出容器节点（`itemType="folder"`、`resourceType=null`、无版本，`sourceId` 为导出端生成的包内唯一 UUID），并将所有真实资源节点的 `parentId` **直接指向目标结构中的父节点**。导入端不推导、不重组，按包内 `parentId` 拓扑建树即可。

**去重**：全部按 `sourceId` 取并集去重——同一真实资源被多处引用时**只导出一份**（放置位置见 §6.4 优先级），所有引用方（`resourcePromptList` / `memory_resource_ids` / `configData.resource_id`）在导入时统一重写指向该份。

**子树展开（两阶段认领，先目录后叶子）**：`resourceType == "skill" | "knowledge_base"` 的节点及被 resource 类型 backend 挂载的 folder 导出**完整子树**（含全部子孙节点与版本，嵌套的 skill / kb 亦完整导出）；其余被引用的叶子资源（file / system_prompt / submessage_template）仅导出节点本身。

认领分两阶段进行：

1. **目录型认领**：全部目录型挂载（kb 根 / skill 根 / backend 挂载的 folder）按 **DB 资源树深度升序（外层优先）** 依次处理；每棵被认领的树**整体**入闭包（树根 + 全部子孙），其成员**绝不外提**——即使某成员同时被其他挂载（prompt / memory / backend）直接引用，也不再单独认领，该挂载的引用在导入时统一重写指向树内成员（§6.4 优先级）。
2. **叶子认领**：目录认领完成后，叶子挂载仅认领**未被任何已认领树包含**的资源。

同一节点被多个挂载命中时，按认领顺序（深度相同 → 挂载收集顺序）取第一个归属，其余挂载引用重写指向该份。由此保证：包内每个真实资源恰好一份；导出的树根两两无祖先关系（树间不存在父子关系）；**任何被引用资源都保留在其原始子树内，父子关系永不因去重而断裂**（如 backend 挂载的 folder 内含被 `resourcePromptList` 挂载的 KB 根时，KB 根整体留在该 folder 子树内，`resourcePromptList` 引用重写指向树内 KB 根）。

### 6.4 目标结构形态与分类（挂载来源决定容器）

每个 Agent 的资源命名空间（主 Agent → `<改名后主Agent名>/`；subAgent → `<改名后主Agent名>/subagents/<subagent名>/`，**递归嵌套**）内部按**挂载来源**组织：

```
<agent名>/
  RB_<backend名>/<folder名>/   ← backend 挂载的 folder（完整子树）
  kb/<KB根名>/                ← resourcePromptList 挂载的 KB 根（完整子树）
  skill/<Skill根名>/          ← resourcePromptList 挂载的 Skill 根（完整子树）
  prompt/<叶子名>              ← resourcePromptList 挂载的叶子（file / system_prompt / submessage_template）
  memory/<叶子名>              ← memory_resource_ids 挂载的叶子（FILE / SYSTEM_PROMPT / SUBMESSAGE_TEMPLATE）
  subagents/<subagent名>/      ← subAgent 的资源命名空间（递归同构）
```

分类判定（对一个 Agent 的挂载列表逐项判定，**仅用于确定树根的容器归属**）：

| 挂载来源 | 目标容器 | 说明 |
|---|---|---|
| `resourcePromptList`（resourceType == `knowledge_base`） | `kb/<名>/` | 容器归类**以挂载来源为准，而非资源自身形态**："它是 KB"不等于放 `kb/`，只有被 `resourcePromptList` 挂载才放 `kb/` |
| `resourcePromptList`（resourceType == `skill`） | `skill/<名>/` | 同上 |
| `resourcePromptList`（其余：file / system_prompt / submessage_template） | `prompt/<名>` | 叶子 |
| `memory_resource_ids` | `memory/<名>` | 叶子；与 `prompt/` 分目录，互不冲突 |
| backend `configData.resource_id`（**resource 类型**，任意 FOLDER，含 KB 根 / Skill 根） | `RB_<backend名>/<folder名>/` | 外层容器统一加 `RB_` 前缀，与固定容器名（`kb` 等）及资源名天然隔离；backend 配置名全局唯一，加前缀后仍唯一；folder 名为内层根目录名；**local 类型 backend 不挂载资源，不产生容器** |

**优先级（同一真实资源被多处引用时）**：

| 层级 | 规则 |
|---|---|
| 1. 目录包含关系（最高） | 目录型认领按 DB 树深度**外层优先**（§6.3）：外层目录树整体认领后，其内部被挂载的目录 / 叶子一律作为树内成员，不再单独认领——**包含关系优先于挂载来源分类**（如 backend 挂载的 folder 内含被 `resourcePromptList` 挂载的 KB 根，KB 根留在 folder 子树内而非移入 `kb/`） |
| 2. 认领顺序（同节点 tie-break） | 深度相同或同一节点被多个挂载命中时，按挂载**收集顺序**取第一个归属（主 Agent 空间 > subAgent 空间；同 Agent 内 `resourcePromptList > memory_resource_ids > backend`），其余挂载引用重写指向该份——归属不影响结果正确性 |

**容器归类仅作用于树的根节点**：树内成员的挂载来源不再决定其位置（跟随树根所在空间与容器），其挂载引用一律重写指向树内成员。

**固定容器名**（`kb` / `skill` / `prompt` / `memory` / `subagents`）为保留名。容器名为规范定义的结构常量，均通过 `validate_path_safe_name` 非法字符校验（不与用户创建资源时对保留字（`skills` / `memories` 等）的限制冲突）。

**空资源 Agent**：某 Agent（主或 sub）**自身及其全部 subAgent（递归）均无任何挂载资源**（`resourcePromptList` / `memory_resource_ids` / resource backend 的 `configData.resource_id` 均为空）→ 不生成其资源命名空间容器：主 Agent 本体直接放目标文件夹；subAgent 不生成 `subagents/<名>/` 容器。**只要自身或任一后代 subAgent 存在挂载资源，该命名空间容器就必须创建**——后代 subAgent 的资源路径依赖祖先容器（上文递归嵌套），不能因祖先自身"空资源"而省略。

### 6.5 名称校验与唯一性保证（导出端）

- **名称合法性**：目标结构中出现的全部名称（固定容器名、backend 名、subagent 名、资源名、`<改名后主Agent名>`）逐一过 `validate_path_safe_name`；**任一非法 → 导出报错**（DB 中资源名创建时已过同名/路径校验，正常情况下不会触发；仅当数据被绕过校验篡改时出现，此时拒绝导出而非导出脏数据）。
- **导入可行性预检**：主 Agent 名长度 > 91 字符 → **导出报错**（导入端必然构造 `<主Agent原名>_subagent` 文件夹名，9 字符后缀超过 100 上限将导致该包永远无法导入；`_N` 改名后缀属导入环境相关冲突，导出端不预检）。
- **同级重名**：同一容器下同级资源重名（DB 被篡改、绕过挂载校验）→ **导出报错**。正常路径下由挂载校验保证不重名：单个 Agent 挂载列表内 KB 互不重名、Skill 互不重名、叶子（file / system_prompt / submessage_template）共享同名池互不重名（`validate_mounted_resources`）、memory 资源互不重名（`validate_memory_resources`）；backend 名全局唯一且外层容器统一加 `RB_` 前缀（见 §6.4），不与固定容器名冲突；不同 Agent 命名空间相互隔离——因此**目标结构内天然无同级重名，导入端无需同名改名**。

### 6.6 服务商闭包

所有 Agent 的 `aiModelId` + `security_review.model_id` + KB 根（以完整子树形态导出）版本 `attributes.embedding_model_id` 所属服务商（去重）。**模型级闭包**：仅导出上述引用命中的模型，服务商下未引用的模型不导出（见 §5.3）。`embedding_model_id` 引用悬空（模型不存在）→ 导出报错（见 §5.4）。

### 6.7 kb_id / kb_config 规则（以最终输出结构为准）

- 资源**位于闭包内某 KB 根（`knowledge_base` 节点）的子树中**（其父链上存在 KB 根）→ `kb_id` / `kb_config` **原样导出**，导入端将 `kb_id` 重写为新 KB 根 id；
- 资源**不在任何 KB 根子树下**（如 `file` 被挂载但其 KB 根不在闭包内，叶子化进 `prompt/`）→ `kb_id` / `kb_config` **置空**，导入后为无 KB 归属的独立资源（用户可手动移入知识库，移动时系统自动补 `kb_id` / `kb_config`）。

判定只看**最终输出结构中的位置**，与资源在导出前 DB 中的原始位置无关。

### 6.8 其余闭包与清理

- **MCP 闭包**：所有 Agent 的 `enabledMcpIds`。
- **blob 闭包**：资源文件型版本内容 + Agent 头像，按 **File 记录**去重（同一 File 记录只导出一份，见 §4.3）。
- **`last_ingest_config` 清理**：导出时删除文件型版本 `attributes` 中的 `last_ingest_config`（向量索引不迁移，导入后不可 RESUME）。
- **悬空引用**：导出端不做任何过滤/清理 —— `subAgents` / `resourcePromptList` / `enabledMcpIds` / `memory_resource_ids` / `security_review.model_id` / `agentAvatarId` / `latestVersionId` 中指向已删除实体的引用照常原样导出（`backendIds` / `defaultBackendId` 例外：导出时清洗，见 §6.2 / §5.6）；导入端在 dry-run 引用完整性检查（§7.1 步 4）中校验全部引用存在，缺失即拒绝导入。名称校验与同级重名校验（§6.5）及 KB 根 `embedding_model_id` 悬空校验（§5.4，悬空 → 导出报错）为上述"不清理"原则的例外。

## 7. 导入规则

### 7.1 流程

**预检模式（dry-run）**：导入 API 支持 `preview=true`，执行下列 1–4 步后即返回结果，不写入任何数据：

1. 解压 gzip，校验 `format` 为固定值；`format` / `formatVersion` / `mambochatVersion` / `exportedAt` 缺失 → 格式错误，拒绝导入；`formatVersion` 大于当前支持版本 → 拒绝并提示升级平台（见 §8）。
2. `mambochatVersion` 低于当前版本时警告，不阻断。
3. 加载 `blobs[]`，建立 `blobId → bytes` 索引并校验 `size` 一致（每个 `blobId` 对应一个 File 记录，多引用方共享同一 file id，见 §5.4 DB 映射）。
4. 引用完整性检查（所有 `blobId` 引用及全部**非空** `sourceId` 引用均存在：`aiModelId` / `security_review.model_id` / `embedding_model_id` / `resourcePromptList` / `memory_resource_ids` / `enabledMcpIds` / `subAgents` / `backendIds` / `defaultBackendId` / `parentId` / `latestVersionId` / `kb_id` / `configData.resource_id`；**`null` 引用不校验、导入后保持 `null`**；`backendIds` / `defaultBackendId` 导出时已清洗（§5.6），校验其非空值必指向 `backends[]`；缺失即拒绝，见 §6.8）+ 冲突预扫描（§7.2）。返回：改名建议清单、缺少 apiKey 的服务商清单、**导入目录树预览**（直接展示包内目标结构，供用户确认）。
5. 正式导入（仅 `preview=false` 时执行）：按序创建，每成功创建一个实体即记录 `(sourceId, newId, 实体类型)` 至本次导入会话（返回 `importSessionId`）：
   1. `providers`（apiKey 写入占位符 `"********"`，见 §4.2；导入报告列出全部服务商供 UI 提示补填）
   2. `resources`（**按包内 `parentId` 拓扑序建树**：虚拟容器节点创建为普通 folder（`itemType=folder`、`resourceType=null`、无版本）→ 子树成员保留 `resourceType` / `kb_id` / `kb_config`（`kb_id` 重写为新 KB 根 ID）→ 文件型版本经 File 服务落库；**KB 根节点调用 `create_knowledge_base` 等价逻辑创建**：校验 embedding 模型存在 / 类型为 embedding / dimension 受支持，校验失败则该项报错；`embedding_model_id` 传入重写后的新模型 id，`dimension` 以重写后模型 `meta_config.embedding_dimension` 推导为准（正常与导出 attributes 一致，attributes 中的 `dimension` 不参与校验），`embedding_rate_limit` 取自导出 attributes；KB 根版本**唯一**——创建即生成"初始配置"版本，随后**原地更新**该版本的 `attributes` / `content` 以匹配包内版本数据并设置 `latestVersionId`，不新增版本；其余带版本资源按包内版本数据重建版本（创建后调用 `batch_update_versions_order` 恢复包内 `sortOrder`）与 `latestVersionId`）
   3. `mcpServers`
   4. `backends`（resource 类型：`configData.resource_id` 映射替换；local 类型：`configData` 无跨段引用，原样落库）
   5. `agents`（主 Agent 放目标文件夹（Agent 树）；subAgent 平铺进 `<主Agent原名>_subagent` 文件夹（与主 Agent 同级）；重写全部引用字段；`backendIds` / `defaultBackendId` 包内已清洗（§5.6），重写映射后原样落库；头像经 File 服务落库）
6. 返回导入报告：成功/失败清单、缺少 apiKey 的服务商列表。

### 7.2 名称冲突处理

导出侧不做任何改名（名称校验在导出端完成，见 §6.5）；包内目标结构已保证**同一容器内同级无重名**（挂载校验 + 导出端同级重名检查）。导入侧仅需处理**与导入环境相关的冲突**，调用方可通过 `nameOverrides` 覆盖自动改名结果（见 §7.1 步 4）。

| 实体 | 冲突检测范围 | 处理 |
|---|---|---|
| Backend | 全局（DB unique） | `原名_N`（N 从 1 起，跳过已存在的编号） |
| 主 Agent 资源命名空间容器 | 目标文件夹内 | 容器名 = 改名后的主 Agent 名，冲突 → `原名_N`；主 Agent 及全部 subAgent 均无资源时不建容器 |
| 包内其它容器与资源（固定目录名 / backend 名 / subagent 名 / 资源名） | — | **不改名**（包内已保证同级唯一；跨命名空间目录隔离，不同空间同名不冲突） |
| Agent | 目标文件夹内同级 | `原名_N` |
| subAgent 文件夹 | 目标文件夹内（与主 Agent 同级） | `<主Agent原名>_subagent`，冲突 → `<主Agent原名>_subagent_N`；subAgent 自身不处理名称冲突（新建文件夹内不会重名，若真冲突属用户责任） |
| AIProvider | 全局 | `原名_N` |
| McpServer | — | 不改名（DB 无唯一约束，重复挂载属用户行为） |
| Skill | — | 不改名（资源名不变，frontmatter 无需联动） |

命名统一规则：所有改名结果必须通过 `validate_path_safe_name`（禁止 `/` `\` 控制字符、`.` `..`、系统保留字）且不超过对应名称长度上限（100 字符，含 `_N` 后缀与 `<原名>_subagent` 文件夹名）；**改名结果超长 → 导入失败并报错**（不做截断）；`_N` 后缀中 `_` 为下划线，`N` 从 1 开始。

### 7.3 安全限制

- 包文件大小上限 100 MB；解码后总内容上限 500 MB；单个 blob 上限 20 MB（与 Skill ZIP 导入防线一致）。
- base64 解码后字节数与 `size` 字段不一致 → 拒绝。
- 所有名称字段导入前过 `validate_path_safe_name`；改名结果超长（>100 字符）→ 拒绝（见 §7.2）。

### 7.4 失败处理与恢复

现有 CRUD 层（`FileService` / `resource_crud` / `provider_crud` 等）在函数内部各自提交事务，导入**不依赖单一大事务**，采用"可恢复 + 可清理"策略：

1. **预检先行**：可预知的失败（格式错误、引用缺失、blob 校验失败、名称冲突）在 dry-run 阶段全部暴露，用户确认后才正式导入；执行期失败仅剩系统级异常。
2. **会话记录**：正式导入按序创建实体并记录至本次 `importSessionId`；任一步失败立即中止，返回结构化报告：
   ```
   { importSessionId, failedPhase, failedEntity, error, created: [已创建实体清单] }
   ```
3. **失败后的两个动作**（前端提供）：
   - **清理并重试**：调用清理接口（按 `importSessionId`），按创建逆序删除本会话实体：agents → backends → mcpServers → resources → providers → 关联 File 记录；清理后重新导入。
   - **保留已导入部分**：已完整创建的实体（服务商、资源树等）保留，用户修复问题后重导剩余部分；重复实体为"同名不同 id"，可容忍或由用户手动删除。
4. **agent 阶段特殊性**：agent 最后创建且引用已全部重写为新 id —— 前置阶段成功后，已创建的 agent 引用完整，视为导入完成，无需回滚。

## 8. 兼容性与扩展性

- `formatVersion` 语义：值为本规范最后一次变更时的 mambochat 版本（当前 `"1.3.0"`），仅在规范本身变更时 bump（见 §5.1）。导入端接受 `formatVersion <= 当前支持版本`（兼容旧版本导出的包）；`formatVersion > 当前支持版本` → 拒绝，提示用户升级平台。同一版本内的格式差异由"忽略未知字段/段"（见下）承担，不另设小版本号。
- 同版本内的向后兼容扩展：`backends[]` 在 1.3.0 内扩展为允许 `backendType == "local"`（resource 仍为原语义）。旧包（仅 resource）导入不受影响；扩展前的导入实现无法识别 local 类型（会以错误类型建库并报资源引用错误），用户升级到包含该扩展的同一版本实现后即可正常导入，故不 bump formatVersion。
- 未知字段：导入端 pydantic 以 `extra='ignore'` 解析。
- 段级扩展：未来新增实体（如知识库）直接新增顶层段，旧导入端忽略。
- JSON Schema 文件随应用发布（如 `backend/schemas/agent_package_schema_v1.json`），`$schema` 以相对路径引用，仅用于校验与 IDE 提示。

## 9. 完整示例

以下示例展示新目标结构：主 Agent "Demo Agent"（Mambo）挂载 1 个 Skill 根（`r1`，含 `SKILL.md`）、1 个叶子（`r2`，system_prompt）、1 个 Resource Backend（`bk1`，挂载普通 folder `f1`，含子文件 `f2`）、1 个 Local Backend（`bk2`，不挂载资源）、1 个 memory 资源（`m1`）；subAgent "helper"（`a2`）独有 1 个叶子（`s2`）。`sourceId` 使用简短占位符，真实导出为 UUID；`vc-*` 为导出端虚拟的容器节点。

```jsonc
{
  "$schema": "./agent_package_schema_v1.json",
  "format": "mambochat.agent-package",
  "formatVersion": "1.3.0",
  "mambochatVersion": "1.3.0",
  "exportedAt": "2026-05-01T12:00:00+08:00",
  "description": "Demo Agent 分享包",
  "agents": [
    {
      "sourceId": "a1",
      "name": "Demo Agent",
      "description": "主 Agent",
      "itemType": "agent",
      "AgentType": "Mambo",
      "systemPrompt": "你是 Demo Agent",
      "modelParameters": { "temperature": 0.7 },
      "agentParameters": {
        "include_general_purpose": false,
        "enable_planning": true,
        "enable_memory": false,
        "enable_summarization": false,
        "enable_show": true,
        "memory_resource_ids": ["m1"],
        "summarization_config": null,
        "security_review": { "enabled": false, "model_id": null },
        "version_control": { "enabled": false, "auto_snapshot": true },
        "mcp_direct_tool_threshold": 15
      },
      "aiModelId": "m1",
      "agentAvatarId": "b2",
      "resourcePromptList": ["r1", "r2"],
      "enabledMcpIds": ["mc1"],
      "subAgents": ["a2"],
      "backendIds": ["bk1", "bk2"],
      "defaultBackendId": "bk1"
    },
    {
      "sourceId": "a2",
      "name": "helper",
      "description": "子 Agent",
      "itemType": "agent",
      "AgentType": "ReActAgent",
      "systemPrompt": "你是 helper",
      "modelParameters": {},
      "agentParameters": null,
      "aiModelId": "m1",
      "resourcePromptList": ["s2"],
      "enabledMcpIds": [],
      "subAgents": [],
      "backendIds": []
    }
  ],
  "providers": [
    {
      "sourceId": "p1",
      "name": "OpenAI",
      "apiHost": "https://api.openai.com/v1",
      "use_proxy": false,
      "worker_type": "openai",
      "apiKeyMissing": true,
      "models": [
        {
          "sourceId": "m1",
          "modelId": "gpt-4o",
          "name": "GPT-4o",
          "meta_config": { "context_length": 128000 },
          "model_type": "chat",
          "starred": true
        }
      ]
    }
  ],
  "resources": [
    // ---- 虚拟容器节点（导出端生成，导入端创建为普通 folder）----
    { "sourceId": "vc-agent", "name": "Demo Agent", "itemType": "folder", "resourceType": null, "parentId": null, "sortOrder": 0, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-skill", "name": "skill", "itemType": "folder", "resourceType": null, "parentId": "vc-agent", "sortOrder": 0, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-prompt", "name": "prompt", "itemType": "folder", "resourceType": null, "parentId": "vc-agent", "sortOrder": 1, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-memory", "name": "memory", "itemType": "folder", "resourceType": null, "parentId": "vc-agent", "sortOrder": 2, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-bk1", "name": "RB_workspace", "itemType": "folder", "resourceType": null, "parentId": "vc-agent", "sortOrder": 3, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-sub", "name": "subagents", "itemType": "folder", "resourceType": null, "parentId": "vc-agent", "sortOrder": 4, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-sub-a2", "name": "helper", "itemType": "folder", "resourceType": null, "parentId": "vc-sub", "sortOrder": 0, "kb_id": null, "kb_config": null, "latestVersionId": null },
    { "sourceId": "vc-sub-a2-prompt", "name": "prompt", "itemType": "folder", "resourceType": null, "parentId": "vc-sub-a2", "sortOrder": 0, "kb_id": null, "kb_config": null, "latestVersionId": null },

    // ---- 主 Agent 空间：Skill 子树（skill/）----
    {
      "sourceId": "r1",
      "name": "my-skill",
      "description": null,
      "itemType": "folder",
      "resourceType": "skill",
      "parentId": "vc-skill",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": null
    },
    {
      "sourceId": "r3",
      "name": "SKILL.md",
      "description": null,
      "itemType": "resource",
      "resourceType": "file",
      "parentId": "r1",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": "rv2",
      "versions": [
        {
          "sourceId": "rv2",
          "name": "v1",
          "sortOrder": 0,
          "commitMessage": null,
          "contentType": "file",
          "file": {
            "filename": "SKILL.md",
            "mimeType": "text/markdown",
            "size": 1234,
            "blobId": "b1"
          },
          "attributes": {}
        }
      ]
    },

    // ---- 主 Agent 空间：叶子（prompt/）----
    {
      "sourceId": "r2",
      "name": "main-prompt",
      "description": null,
      "itemType": "resource",
      "resourceType": "system_prompt",
      "parentId": "vc-prompt",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": "rv1",
      "versions": [
        {
          "sourceId": "rv1",
          "name": "v1",
          "sortOrder": 0,
          "commitMessage": null,
          "contentType": "text",
          "content": "你是 Demo Agent，请遵循以下规则……",
          "attributes": null
        }
      ]
    },

    // ---- 主 Agent 空间：memory 资源（memory/）----
    {
      "sourceId": "m1",
      "name": "mem-notes",
      "description": null,
      "itemType": "resource",
      "resourceType": "system_prompt",
      "parentId": "vc-memory",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": "mv1",
      "versions": [
        {
          "sourceId": "mv1",
          "name": "v1",
          "sortOrder": 0,
          "commitMessage": null,
          "contentType": "text",
          "content": "长期记忆内容",
          "attributes": null
        }
      ]
    },

    // ---- 主 Agent 空间：Backend 挂载 folder 子树（workspace/）----
    {
      "sourceId": "f1",
      "name": "docs",
      "description": null,
      "itemType": "folder",
      "resourceType": null,
      "parentId": "vc-bk1",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": null
    },
    {
      "sourceId": "f2",
      "name": "guide.md",
      "description": null,
      "itemType": "resource",
      "resourceType": "file",
      "parentId": "f1",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": "fv1",
      "versions": [
        {
          "sourceId": "fv1",
          "name": "v1",
          "sortOrder": 0,
          "commitMessage": null,
          "contentType": "file",
          "file": {
            "filename": "guide.md",
            "mimeType": "text/markdown",
            "size": 7,
            "blobId": "b3"
          },
          "attributes": null
        }
      ]
    },

    // ---- subAgent "helper" 空间：独有叶子（subagents/helper/prompt/）----
    {
      "sourceId": "s2",
      "name": "helper-prompt",
      "description": null,
      "itemType": "resource",
      "resourceType": "system_prompt",
      "parentId": "vc-sub-a2-prompt",
      "sortOrder": 0,
      "kb_id": null,
      "kb_config": null,
      "latestVersionId": "sv1",
      "versions": [
        {
          "sourceId": "sv1",
          "name": "v1",
          "sortOrder": 0,
          "commitMessage": null,
          "contentType": "text",
          "content": "你是 helper",
          "attributes": null
        }
      ]
    }
  ],
  "mcpServers": [
    {
      "sourceId": "mc1",
      "name": "filesystem",
      "description": null,
      "transportType": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "cwd": null,
      "url": null,
      "timeout": null,
      "sse_read_timeout": null,
      "isEnabled": true
    }
  ],
  "backends": [
    {
      "sourceId": "bk1",
      "name": "workspace",
      "description": null,
      "backendType": "resource",
      "configData": {
        "resource_id": "f1",
        "edit_whitelist": ["/workspace/"],
        "edit_blacklist": null
      },
      "tools_config": { "execute": { "enabled": false, "require_review": true } }
    },
    {
      "sourceId": "bk2",
      "name": "local_home",
      "description": null,
      "backendType": "local",
      "configData": {
        "root_dir": "~",
        "edit_whitelist": null,
        "edit_blacklist": null,
        "ignore_dirs": [".git", "node_modules"]
      },
      "tools_config": { "execute": { "enabled": false, "require_review": true } }
    }
  ],
  "blobs": [
    {
      "blobId": "b1",
      "filename": "SKILL.md",
      "mimeType": "text/markdown",
      "size": 13,
      "encoding": "base64",
      "data": "IyBTa2lsbCBOYW1lCg=="
    },
    {
      "blobId": "b2",
      "filename": "avatar.png",
      "mimeType": "image/png",
      "size": 70,
      "encoding": "base64",
      "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    },
    {
      "blobId": "b3",
      "filename": "guide.md",
      "mimeType": "text/markdown",
      "size": 7,
      "encoding": "base64",
      "data": "IyBHdWlkZQ=="
    }
  ]
}
```

> 导入后的资源目录结构：

```
目标文件夹/
  Demo Agent/                       ← 虚拟容器 vc-agent（主 Agent 资源命名空间）
    skill/my-skill/                ← vc-skill / r1（Skill 子树）
      SKILL.md                      ← r3
    prompt/main-prompt              ← vc-prompt / r2（叶子）
    memory/mem-notes                ← vc-memory / m1（memory 资源）
    RB_workspace/docs/              ← vc-bk1 / f1（backend "workspace" 挂载的 folder 子树）
      guide.md                      ← f2
    subagents/helper/               ← vc-sub / vc-sub-a2（subAgent "helper" 资源命名空间）
      prompt/helper-prompt          ← vc-sub-a2-prompt / s2
  Demo Agent_subagent/              ← subAgent 本体（§5.2，与主 Agent 同级）
    helper                          ← agent a2
```

> Local Backend `bk2` 不挂载资源，不产生任何资源目录（§6.4）；导入后仅作为 Agent 的 backend 配置落库。

### 9.1 嵌套场景示例（backend folder 内含 KB 根）

主 Agent "Demo Agent" 通过 `resourcePromptList` 挂载 KB 根 `r1`；subAgent "helper" 的 backend `bk1` 挂载 folder `f1`，而 DB 树中 `f1` 是 `r1` 的父节点（`f1 → r1 → kf1`）。按 §6.3 两阶段认领，`f1` 深度更浅（外层优先），先整体认领 `f1 → r1 → kf1` 为一棵树，挂到 subAgent 空间的 `RB_workspace/f1/` 下；主 Agent 对 `r1` 的挂载不再单独认领，导入时重写指向树内 KB 根——**父子关系完整保留**。

```jsonc
// resources[] 相关片段（虚拟容器节点省略）
{
  "sourceId": "f1", "name": "docs", "itemType": "folder", "resourceType": null,
  "parentId": "vc-bk1", "sortOrder": 0, "kb_id": null, "kb_config": null, "latestVersionId": null
},
{
  "sourceId": "r1", "name": "知识库", "itemType": "folder", "resourceType": "knowledge_base",
  "parentId": "f1", "sortOrder": 0, "kb_id": null, "kb_config": null, "latestVersionId": "kv1",
  "versions": [ /* KB 根初始配置版本，attributes.embedding_model_id 指向 providers */ ]
},
{
  "sourceId": "kf1", "name": "手册.pdf", "itemType": "resource", "resourceType": "file",
  "parentId": "r1", "sortOrder": 0, "kb_id": "r1",
  "kb_config": { "splitter_type": "simple", "chunk_size": 500, "chunk_overlap": 50 },
  "latestVersionId": "kv2",
  "versions": [ /* 文件型版本 */ ]
}
```

```
目标文件夹/
  Demo Agent/                       ← 主 Agent 资源命名空间（subAgent 有资源，容器必须创建）
    subagents/helper/
      RB_workspace/docs/            ← f1（backend 挂载的 folder，完整子树）
        知识库/                     ← r1（KB 根；主 Agent resourcePromptList 引用重写指向此处）
          手册.pdf                  ← kf1（位于 KB 根子树内，kb_id 原样保留并按 §6.7 重写）
  Demo Agent_subagent/              ← subAgent 本体
    helper                          ← agent a2
```
