# MamboChat 会话导出规范 v1

## 1. 概述

本规范定义 MamboChat 会话导出文件的格式：一个 UTF-8 编码的 JSON 文档，包含单个会话的名称、注入后的系统提示词、活跃路径上的消息（含子消息）及文件附件二进制载荷，用于在不同 MamboChat 实例之间迁移会话（导出后可重新导入为新会话）。

- 文件扩展名：`.json`
- 编码：UTF-8（无 BOM）
- 顶层格式标识：`format = "mambochat.chat-export"`
- 设计目标：**导出的文件可以被本规范定义的导入流程完整还原**；Markdown / HTML 属展示型导出，不参与导入，不受本规范约束。

## 2. 文件与编码

- 文件为单个 JSON 文档（`application/json`），**不压缩**（保持可读性；文件附件以 base64 内嵌于 `blobs[]` 段，见 §4.3）。
- JSON 使用带缩进的可读格式导出（导入端解析时对空白不敏感）。
- 时间字段统一使用 ISO-8601 字符串（含时区，如 `"2026-05-01T12:00:00+08:00"`）。

## 3. 顶层结构

```jsonc
{
  "format": "mambochat.chat-export",
  "formatVersion": "1.3.0",
  "mambochatVersion": "1.3.0",
  "exportedAt": "2026-05-01T12:00:00+08:00",
  "chat": {
    "name": "Demo Chat",
    "createdAt": "2026-05-01T10:00:00+08:00",
    "chatMode": "normal",
    "systemPrompt": "……"
  },
  "messages": [],
  "blobs": []
}
```

## 4. 通用约定

### 4.1 消息范围：仅活跃线性路径

- 只导出会话的**活跃路径**消息（与后端 `get_messages_by_chat` 返回的线性列表一致），**不导出**分支树、非活跃分支、VersionSnapshot 等历史痕迹。
- `messages[]` 为**有序数组**（按活跃路径自前向后），导入时按下标顺序重建 `parentId` 链，因此消息段**不携带** `parentId` / `lastActiveAt`。

### 4.2 状态清洗

子消息 `status` 导出时统一清洗中间态：`generating` / `pending_review` / `waiting` → `failed`（与复制会话 `duplicate_chat_with_messages` 的逻辑一致）。其余状态原样导出。

### 4.3 blobs 载荷段

- 所有二进制内容（File 类型子消息对应的文件本体）统一存放在顶层 `blobs[]` 段，JSON 主体区域保持纯结构、可读。
- File 类型子消息**不携带** `content`（DB 中该字段存 File 记录 id，属导出端内部标识），改为携带 `file` 对象（`filename` / `mimeType` / `size` / `blobId`）。
- 导出端按 **File 记录**（即 `blobId`）去重：同一 File 记录被多条子消息引用时只导出一份（引用方共用同一 `blobId`）；不同 File 记录即使内容完全相同也分别导出。
- 导入端先建立 `blobId → bytes` 索引，再按序创建实体（先建 File 记录，再将新 File id 写入子消息 `content`）。

### 4.4 资源内容注入

- 会话的 `resource_prompt_list` 中挂载的 `system_prompt` 与 `submessage_template` 两类资源，导出时将其 `latest_version.content` **注入** `chat.systemPrompt`（拼接顺序：会话自带 `systemPrompt` → `system_prompt` 资源内容 → `submessage_template` 资源内容，各段以空行分隔），与前端 `getFullSystemPrompt()` 行为一致。
- 资源本体**不导出**（不进入本格式；资源/Agent 等实体迁移由 `.mamboagent` 包承担）。
- 资源内容读取失败（资源已删除等）：跳过该资源，不阻断导出。

### 4.5 外部依赖不导出

以下字段**不导出**（导入端不校验、不还原，导入后为默认值/空）：

| 字段 | 导入后值 |
|---|---|
| `web_search_mode` | `null`（关闭） |
| `modelParameters` | `null`（创建时按全局默认参数填充） |
| `aiModelId` | `null`（创建时应用全局默认模型） |
| `agentId` | `null` |
| `enabled_mcp_ids` | `[]` |
| `sortOrder` / `parentId` | 由导入端分配（新会话放根目录末尾） |
| `lastOpenedAt` | `null` |
| `itemType` | 恒为 `chat`（仅支持会话，不支持文件夹） |

> `chatMode` **原样导出/导入**：`chatMode=agent` 的会话导入后 `agentId` 为空，需用户手动重新挂载 Agent 后方可正常生成；`normal` 不受影响。

## 5. 数据段定义

### 5.1 元信息

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `format` | string | ✅ | 固定 `"mambochat.chat-export"` |
| `formatVersion` | string | ✅ | 格式版本号，值 = 本规范最后一次变更时的 mambochat 版本（当前 `"1.3.0"`）；兼容规则见 §8 |
| `mambochatVersion` | string | ✅ | 导出时的应用版本（如 `"1.3.0"`），导入端据此做兼容性提示 |
| `exportedAt` | string | ✅ | ISO-8601 导出时间 |
| `chat` | object | ✅ | 会话本体，见 §5.2 |
| `messages` | array | ✅ | 活跃路径消息数组，可为空，见 §5.3 |
| `blobs` | array | ✅ | 文件载荷段，可为空，见 §5.5 |

### 5.2 `chat`

```jsonc
{
  "name": "Demo Chat",
  "createdAt": "2026-05-01T10:00:00+08:00",
  "chatMode": "normal",
  "systemPrompt": "会话自带系统提示词\n\n系统提示词资源内容\n\n消息模板内容"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | ✅ | 会话名称（1–100 字符） |
| `createdAt` | string | ✅ | ISO-8601 创建时间 |
| `chatMode` | string | ✅ | `"normal"` / `"agent"`，原样导出（见 §4.5） |
| `systemPrompt` | string | 否 | **注入后**的完整系统提示词（见 §4.4），无内容时省略 |

### 5.3 `messages[]`

```jsonc
{
  "role": "user",
  "createdAt": "2026-05-01T10:00:00+08:00",
  "subMessages": []
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `role` | string | ✅ | `"user"` / `"assistant"` / `"system"` |
| `createdAt` | string | ✅ | ISO-8601 消息创建时间 |
| `subMessages` | array | ✅ | 有序子消息数组，可为空，见 §5.4 |

### 5.4 `subMessages[]`

仅导出下列 7 种类型；**其余类型（`ZipHistory` / `ReviewTool` / `AskUser` / `SecurityReview` / `Suggest` / `VersionSnapshot`）整条跳过、不导出**。

| 类型 | content 说明 |
|---|---|
| `Normal` | 正文文本（原样） |
| `Reasoning` | 思维链文本（原样） |
| `McpTool` | 工具调用 JSON 字符串（`tool_call_id` / `name` / `arguments` / `result` / `is_error` 等，**完整保留**） |
| `Usage` | token 用量 JSON 字符串（原样） |
| `Error` | 错误信息 JSON 字符串（原样） |
| `TaskSubStep` | 子代理步骤文本（原样） |
| `File` | 不携带 `content`，携带 `file` 对象引用 blob（见下） |

```jsonc
{
  "type": "Normal",
  "content": "你好",
  "config": { "is_collapsed": false, "is_minimal": false },
  "status": "completed",
  "sortOrder": 0,
  "createdAt": "2026-05-01T10:00:00+08:00"
}
```

```jsonc
// File 类型
{
  "type": "File",
  "config": { "pending_file_path": null },
  "status": "completed",
  "sortOrder": 1,
  "createdAt": "2026-05-01T10:00:00+08:00",
  "file": {
    "filename": "report.pdf",
    "mimeType": "application/pdf",
    "size": 20480,
    "blobId": "blob-uuid"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | string | ✅ | 子消息类型（见上表） |
| `content` | string | 否 | 文本内容；`File` 类型必须省略 |
| `config` | object | 否 | 原样导出（`is_collapsed` / `is_minimal` / `context_participation_length` / `task_group_id` 等），无配置时省略 |
| `status` | string | ✅ | 经 §4.2 清洗后的状态 |
| `sortOrder` | int | ✅ | 分区排序 |
| `createdAt` | string | ✅ | ISO-8601 子消息创建时间 |
| `file` | object | File 类型必填 | 文件元信息 + blob 引用，见 §5.5；**仅 `File` 类型携带** |

### 5.5 `blobs[]`

```jsonc
{
  "blobId": "blob-uuid",
  "filename": "report.pdf",
  "mimeType": "application/pdf",
  "size": 20480,
  "encoding": "base64",
  "data": "JVBERi0xLjQK……"
}
```

`size` 为原始字节数；导入端解码后校验与 `size` 一致（**以 `blobs[].size` 为校验权威**；§5.4 子消息 `file.size` 为导出冗余信息，不参与校验）。

## 6. 导出规则

1. **范围**：单个会话（`itemType == "chat"`），仅活跃线性路径消息（§4.1）。
2. **资源注入**：按 §4.4 解析 `resource_prompt_list` 并拼接 `systemPrompt`；`resource_prompt_list` 本身不导出。
3. **子消息过滤**：仅导出 §5.4 列出的 7 种类型；`VersionSnapshot` 恒跳过，其余过滤类型见 §5.4。
4. **状态清洗**：`generating` / `pending_review` / `waiting` → `failed`（§4.2）。
5. **blob 闭包**：遍历活跃路径上 `File` 类型子消息，按 File 记录去重收集（§4.3）；File 记录缺失（文件已被清理）→ 跳过该子消息，不阻断导出。
6. **悬空引用**：`resource_prompt_list` 中资源已删除 → 跳过该资源（§4.4）；其余无引用字段（§4.5 全不导出）。

## 7. 导入规则

### 7.1 流程

1. 解析 JSON，校验 `format` 为固定值；`format` / `formatVersion` / `mambochatVersion` / `exportedAt` / `chat` 缺失 → 格式错误，拒绝导入；`formatVersion` 大于当前支持版本 → 拒绝并提示升级平台（见 §8）。
2. `mambochatVersion` 低于当前版本时警告，不阻断。
3. 加载 `blobs[]`，建立 `blobId → bytes` 索引并校验 `size` 一致（每个 `blobId` 对应一个 File 记录，多引用方共享同一 file id，见 §4.3 DB 映射）。
4. 结构校验：`messages[].subMessages[]` 中 `File` 类型的 `file.blobId` 必须存在于 `blobs[]`；出现未在 §5.4 允许列表中的子消息类型 → **跳过该子消息**（向前兼容，见 §8）；`chat.name` 为空或超长 → 拒绝。
5. 正式导入：
   1. 创建会话：`ChatCreate(name=冲突处理后的名称, systemPrompt=包内值, chatMode=包内值)`，放入**根目录**；其余字段不传（默认值见 §4.5）。
   2. 按 `messages[]` 下标顺序逐条创建消息，`parentId` 指向上一条新消息 id（第一条为 `null`）；`createdAt` 沿用包内值。
   3. 子消息：先为 `File` 类型按 `blobId` 创建 File 记录（`FileService`），将新 File id 写入 `content`；其余字段（`type` / `content` / `config` / `status` / `sortOrder` / `createdAt`）原样落库。
6. 返回导入报告：`{ chatId, name, messageCount, fileCount }`。

### 7.2 名称冲突处理

| 实体 | 冲突检测范围 | 处理 |
|---|---|---|
| 会话 | 根目录内同级 | `原名 (导入)`，冲突 → `原名 (导入)_N`（N 从 1 起，跳过已存在的编号） |

### 7.3 安全限制

- 文件大小上限 100 MB；单个 blob 上限 20 MB（与 Skill ZIP / Agent 包导入防线一致）。
- base64 解码后字节数与 `size` 字段不一致 → 拒绝。
- 子消息 `content` 与 `config` 原样落库，不做内容解析（文本型内容无注入风险；`McpTool` 等 JSON 字符串仅作展示）。

### 7.4 失败处理

- 导入采用单事务：任一步失败整体回滚（会话 + 消息 + 子消息 + File 记录），返回错误信息，不产生半成品会话。
- 文件名冲突 / blob 校验失败等在写入前完成校验，正常流程不会出现执行期失败。

## 8. 兼容性与扩展性

- `formatVersion` 语义：值为本规范最后一次变更时的 mambochat 版本（当前 `"1.3.0"`），仅在规范本身变更时 bump。导入端接受 `formatVersion <= 当前支持版本`；`formatVersion > 当前支持版本` → 拒绝，提示用户升级平台。
- 未知字段：导入端以"忽略未知字段"解析（pydantic `extra='ignore'`）。
- 新增子消息类型：未来新增类型时旧导入端**跳过**未知类型子消息（§7.1 步 4），不阻断整个导入。
- 段级扩展：未来新增顶层段，旧导入端忽略。

## 9. 完整示例

以下示例展示：会话挂载了 1 个 `system_prompt` 资源（内容已注入 `systemPrompt`）；活跃路径 2 条消息；第 2 条消息含 `Normal` 与 `File` 两个子消息，文件本体在 `blobs[]`。`blobId` 使用简短占位符，真实导出为 File 记录 UUID。

```jsonc
{
  "format": "mambochat.chat-export",
  "formatVersion": "1.3.0",
  "mambochatVersion": "1.3.0",
  "exportedAt": "2026-05-01T12:00:00+08:00",
  "chat": {
    "name": "Demo Chat",
    "createdAt": "2026-05-01T10:00:00+08:00",
    "chatMode": "normal",
    "systemPrompt": "你是助手，请用中文回答。\n\n（system_prompt 资源内容）\n\n（submessage_template 资源内容）"
  },
  "messages": [
    {
      "role": "user",
      "createdAt": "2026-05-01T10:00:00+08:00",
      "subMessages": [
        {
          "type": "Normal",
          "content": "请总结这份报告",
          "config": { "is_collapsed": false },
          "status": "completed",
          "sortOrder": 0,
          "createdAt": "2026-05-01T10:00:00+08:00"
        }
      ]
    },
    {
      "role": "assistant",
      "createdAt": "2026-05-01T10:01:00+08:00",
      "subMessages": [
        {
          "type": "Reasoning",
          "content": "用户需要总结报告，先读取附件……",
          "status": "completed",
          "sortOrder": 0,
          "createdAt": "2026-05-01T10:01:00+08:00"
        },
        {
          "type": "Normal",
          "content": "报告核心结论如下：……",
          "status": "completed",
          "sortOrder": 1,
          "createdAt": "2026-05-01T10:01:05+08:00"
        },
        {
          "type": "McpTool",
          "content": "{\"tool_call_id\":\"call_1\",\"name\":\"read_file\",\"arguments\":{\"path\":\"/workspace/report.pdf\"},\"result\":\"PDF 内容……\",\"is_error\":false}",
          "config": { "is_minimal": true },
          "status": "completed",
          "sortOrder": 2,
          "createdAt": "2026-05-01T10:00:30+08:00"
        },
        {
          "type": "File",
          "status": "completed",
          "sortOrder": 3,
          "createdAt": "2026-05-01T10:01:06+08:00",
          "file": {
            "filename": "summary.md",
            "mimeType": "text/markdown",
            "size": 1234,
            "blobId": "b1"
          }
        }
      ]
    }
  ],
  "blobs": [
    {
      "blobId": "b1",
      "filename": "summary.md",
      "mimeType": "text/markdown",
      "size": 1234,
      "encoding": "base64",
      "data": "IyDlhoXlrrnmoIflh4bovpPli70K……"
    }
  ]
}
```

> 导入后：新会话创建于根目录（名称冲突时按 §7.2 处理），2 条消息按序重建链，`summary.md` 还原为可下载的真实文件附件。
