# 工具测试流程与规范

> **文档说明**: 本文档记录了 Mambo 工具系统的测试流程、规范及用例。
> 每个工具为一个章节，包含用例表格（入参 + 预期返回值）。
>
> **使用方式**: 在运行测试之前，请先按照「第零章」搭建测试环境，记录实际创建的目录结构和文件信息，再逐章执行测试用例。

---

## 目录

- [第零章: 测试环境搭建指南](#第零章-测试环境搭建指南)
- [第一章: `tree` — 目录树展示](#第一章-tree--目录树展示)
- [第二章: `ls` — 目录内容列表](#第二章-ls--目录内容列表)
- [第三章: `read` — 文件内容读取](#第三章-read--文件内容读取)
- [第四章: `grep` — 文本内容搜索](#第四章-grep--文本内容搜索)
- [第五章: `edit` — 文件内容替换](#第五章-edit--文件内容替换)
- [第六章: `write` — 文件写入与创建](#第六章-write--文件写入与创建)

---

# 第零章: 测试环境搭建指南

## 0.1 概述

在运行任何工具测试之前，需要先创建测试环境。本章描述需要创建的文件和目录的**类别与特征**，不规定具体数量和内容——你可根据描述自行创建合适的测试数据。

**重要**: 创建完成后，请记录环境的实际结构（路径、文件大致行数等），后续测试用例将引用这些路径。

---

## 0.2 项目目录 (`demo_project`)

**路径**: `/workspace/demo_project/`

创建一个多层级项目目录，深度 4–5 层，文件和目录混合分布。需要包含以下类别的文件：

| 类别 | 建议数量 | 内容要求 |
|------|---------|---------|
| Python 源文件 | 3–5 个 | 含 `import` 语句、类定义 (`class`)、函数定义 (`def`)，分布在不同子目录中。单个文件建议 30–50 行；另准备一个较大文件（80–120 行，如测试文件） |
| 配置文件 | 2–3 个 | YAML / JSON 格式，含键值对，放在独立子目录 |
| 数据文件 | 2–3 个 | CSV（含表头 + 数据行）、JSON、XML |
| Markdown 文档 | 1–2 个 | 含标题 (`#`)、代码块、段落，建议 50+ 行 |
| 前端资源 | 2–3 个 | CSS / JS / HTML，放在深层静态资源目录（如 `static/css/`、`static/js/`、`templates/`） |
| 隐藏文件 | 2–3 个 | `.` 开头，如 `.gitignore`、`.env.example`、`.gitkeep` |
| 根目录文件 | 若干 | README、License、Dockerfile、Makefile、pyproject.toml 等 |

**特殊要求**:
- 至少包含**一个空文件**（0 字节，可复用 `.gitkeep`）
- 至少包含**一个空目录**（不含任何文件）,若无execute 工具则无此要求
- 至少包含**一个纯文件目录**（目录内只有文件，无子目录，如 `config/`）
- 至少包含**一个纯子目录的目录**（目录内只有子目录，无文件）

---

## 0.3 `edit` 测试 fixture

**路径**: `/workspace/edit_test_fixtures/`

| 文件 | 内容要求 |
|------|---------|
| `single_line.txt` | 包含一个唯一可识别的标记字符串（如首行写 `Hello, World!`），其余内容任意 |
| `multi_occurrence.txt` | 全文包含同一字符串 **至少 5 处**（如多处出现 `apple`），以便测试 `replace_all` |
| `special_chars.txt` | 包含 Unicode、Emoji、Tab 字符、特殊标点符号（`!@#$%^&*()` 等） |
| `config.ini` | INI 风格配置文件，含至少两个 `[section]` 分段标记和若干键值对，内容足够在开头和末尾分别替换 |
| `concurrent_a.txt` | 简单文本，内容任意 |
| `concurrent_b.txt` | 简单文本，内容任意 |
| `concurrent_same.txt` | 包含多个互不相同的标记区域（如 `PART_1`、`PART_2`、`PART_3`），用于并发编辑不同位置 |

---

## 0.4 `write` 测试 fixture

**路径**: `/workspace/write_test_fixtures/`

| 路径 | 说明 |
|------|------|
| `existing_file.txt` | 预存内容的普通文件，用于 `overwrite` 测试 |
| `no_overwrite_dir/` | 已存在的目录 |
| `no_overwrite_dir/file.txt` | 已存在的文件，用于验证默认拒绝覆盖（`overwrite=false`） |
| `concurrent_a.txt` | 并发测试种子文件 |
| `concurrent_b.txt` | 并发测试种子文件 |

---

## 0.5 `tree` 特殊字符测试目录

**路径**: `/workspace/tree_test_dir/`

创建目录，其名称包含 Emoji 和 Unicode 字符（如 `😀 unicode ♥ name`），内部可再嵌套含特殊符号（`!@#`）的子目录及简单文件。

---

## 0.6 环境记录

创建完成后，请记录以下信息供测试引用：

- 项目根目录路径
- 各 Python 源文件的路径及大致行数
- 空文件与空目录的路径
- 含隐藏文件的目录路径
- 纯文件目录 / 纯子目录的路径
- 多层嵌套最深路径


---

# 第一章: `tree` — 目录树展示

## 1.1 工具概述

| 属性 | 说明 |
|------|------|
| **工具名** | `tree` |
| **功能** | 以树形结构展示目录内容，包含文件名和文件大小 |
| **必填参数** | `path` (string) — 要展示的根目录绝对路径 |
| **可选参数** | `depth` (integer, 默认 `3`) — 最大递归深度，必须 ≥ 1 |

## 1.2 参数规范

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | ✅ 是 | — | 绝对路径，必须是**存在的目录**，不能是文件或根目录 `/` |
| `depth` | integer | ❌ 否 | `3` | 递归深度，正整数（≥ 1），无上限 |

## 1.3 返回值规范

### 正常返回

以树形图文本形式返回目录结构，格式如下：

```
文件名 (文件大小)
目录名/
├── 子文件 (大小)
└── 子目录/
    └── ...
```

- **文件**: 显示 `文件名 (大小)`，大小单位自适应（B / KB / MB / GB）
- **目录**: 显示 `目录名/`，递归展开子内容
- **超出 depth 的目录**: 显示为 `目录名/(...)`，不再展开

### 错误返回

| 错误场景 | 返回信息 |
|----------|----------|
| `depth` < 1 | `Invalid depth value: N. Depth must be a positive integer (>= 1).` |
| `path` 是根目录 `/` | `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| `path` 是文件而非目录 | `Path '<path>' is not a directory.` |
| `path` 不存在 | `Path '<path>' not found.` |
| `path` 超出工作区 | `[OUTSIDE_WORKSPACE] 路径超出工作区，所有文件操作必须在 '/workspace/' 下进行` |

---

## 1.4 测试用例

> 测试基准目录: `/workspace/demo_project`（由你自行创建，结构见第零章）

### 1.4.1 正常场景

| # | 用例名称 | path | depth | 预期结果 |
|---|---------|------|-------|----------|
| N1 | 默认深度（不传 depth） | 某个纯文件目录（如 config/） | (不传) | 平铺显示该目录下所有文件，无子目录展开，无 `(...)` |
| N2 | depth=1 浅层展开 | 项目根目录 | `1` | 仅显示根目录下的所有文件和子目录名，子目录后标注 `(...)`，不展开 |
| N3 | depth=2 中层展开 | 项目根目录 | `2` | 展开到第二层：一级子目录下的文件可见，更深子目录标注 `(...)` |
| N4 | depth=3 默认深度（显式传值） | 项目根目录 | `3` | 展开到第三层，第四层及以下标注 `(...)` |
| N5 | depth 足够大，完整展开 | 项目根目录 | 大于实际深度（如 `10`） | 全部文件和目录完整展开，无任何 `(...)` 截断 |
| N6 | depth 远超实际深度 | 项目根目录 | `9999` | 与 N5 完全一致，无溢出/崩溃 |
| N7 | 父级目录 | `/workspace` | `1` | 显示 `/workspace` 下的一级子目录，标注 `(...)` |
| N8 | 纯文件目录 | 某个只含文件的目录 | `3` | 显示全部文件，无树形线条，无 `(...)` |

### 1.4.2 边界/异常场景

| # | 用例名称 | path | depth | 预期结果 |
|---|---------|------|-------|----------|
| E1 | depth=0（非法值） | 项目根目录 | `0` | ❌ `Invalid depth value: 0. Depth must be a positive integer (>= 1).` |
| E2 | depth 为负数 | 项目根目录 | `-1` | ❌ `Invalid depth value: -1. Depth must be a positive integer (>= 1).` |
| E3 | path 为根目录 `/` | `/` | `1` | ❌ `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| E4 | path 为文件（非目录） | 某个具体文件的路径 | `3` | ❌ `Path '...' is not a directory.` |
| E5 | path 不存在（工作区内） | `/workspace/nonexistent/path/xyz` | `3` | ❌ `Path '/workspace/nonexistent/path/xyz' not found.` |
| E6 | path 超出工作区 | `/nonexistent/path/xyz` | `3` | ❌ `[OUTSIDE_WORKSPACE] 路径超出工作区，所有文件操作必须在 '/workspace/' 下进行` |

### 1.4.3 显示格式验证

| # | 验证点 | 预期行为 |
|---|--------|----------|
| F1 | 文件大小单位 | 自适应显示：B / KB / MB / GB，具体值取决于实际文件 |
| F2 | 目录后缀 | 所有目录名后有 `/`，如 `src/`、`config/` |
| F3 | 截断标记 | 超出 depth 的子目录显示 `(...)`，如 `static/(...)` |
| F4 | 树形线条 | 使用 `├──` 和 `└──` 绘制 Unicode 树形线 |
| F5 | 缩进层级 | 每层缩进 4 个空格 |
| F6 | 特殊字符路径 | Emoji、空格、`!@#` 等特殊字符在路径中正常渲染，树形线条不损坏（使用 `/workspace/tree_test_dir/` 验证） |
| F7 | 末尾 `/`（trailing slash） | 路径带 `/` 与不带行为完全一致 |

### 1.4.4 关键行为总结

| 行为 | 说明 |
|------|------|
| `depth` 收敛 | 当 depth > 实际深度时，自动收敛至实际深度，不报错、不追加空层 |
| `depth` 校验 | depth ≤ 0 一律拒绝（含负数） |
| 深度计算 | 从传入 `path` 自身开始算 level 0，其子项为 level 1 |
| 排序 | 同层内「目录组在前、文件组在后」分组；组内按名字 ASCII 升序，点文件（`.` 开头）排在文件组内最前（与 `ls` 一致） |
| 内存/性能 | depth=9999 无性能衰退，不递归创建空节点 |


---

# 第二章: `ls` — 目录内容列表

## 2.1 工具概述

| 属性 | 说明 |
|------|------|
| **工具名** | `ls` |
| **功能** | 列出指定目录下的文件和子目录（单层、非递归），包含文件大小 |
| **必填参数** | `path` (string) — 要列出的目录绝对路径 |
| **可选参数** | 无 |

## 2.2 参数规范

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | string | ✅ 是 | — | 绝对路径，必须是**存在的目录**；不能是文件、根目录 `/`、不存在路径、含 `..` 的路径 |

## 2.3 返回值规范

### 正常返回

每行一个条目，格式为 `完整绝对路径(文件大小)` 或 `完整绝对路径/`：

```
/绝对路径/文件名(文件大小)
/绝对路径/目录名/
```

- **文件**: 显示完整绝对路径 + `(大小)`，大小单位自适应（B / KB / MB / GB）
- **目录**: 显示完整绝对路径 + 尾部 `/`，无大小信息
- **排序**: 「目录组在前、文件组在后」分组排列；组内按名称 ASCII 升序，点文件（`.` 开头）排在文件组内最前
- **隐藏文件**: 点号 `.` 开头的文件/目录正常显示
- **空目录**: 输出为空（无任何条目）

### 错误/警告返回

| 场景 | 返回信息 | 类型 |
|------|----------|------|
| `path` 是根目录 `/` | `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` | ❌ 错误 |
| `path` 是文件（非目录） | `Warning: [NOT_DIR] 目标是文件，不是目录` | ⚠️ 警告 |
| `path` 不存在（在 /workspace 下） | `Warning: [NOT_FOUND] 路径不存在` | ⚠️ 警告 |
| `path` 不在 /workspace 下 | `Warning: [PATH_NOT_UNDER] 路径不在 '/workspace/' 下` | ⚠️ 警告 |
| `path` 含 `..` 路径穿越 | `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` | ❌ 错误 |

## 2.4 测试用例

> 测试基准目录: `/workspace/demo_project`（由你自行创建，结构见第零章）

### 2.4.1 正常场景

| # | 用例名称 | path | 预期结果 |
|---|---------|------|----------|
| N1 | 混合目录（文件+子目录） | 项目根目录 | 列出所有条目：文件显示大小，目录以 `/` 结尾，目录组在前、文件组在后，组内字母序，隐藏文件正常显示 |
| N2 | 纯文件目录 | 只含文件的目录（如 config/） | 列出所有文件（带大小），无目录条目 |
| N3 | 纯子目录的目录 | 只含子目录的目录 | 列出所有子目录（以 `/` 结尾），无文件条目 |
| N4 | 单文件目录 | 只含一个文件的目录 | 列出该文件（带大小） |
| N5 | 含隐藏文件的目录 | 含 `.` 开头文件的目录 | 隐藏文件正常列出 |
| N6 | 父级目录 | `/workspace` | 列出 `/workspace` 下的所有条目 |
| N7 | 路径末尾带 `/` | 项目根目录 + 末尾 `/` | 与 N1 完全一致 |
| N8 | 深层嵌套目录 | 项目中最深的子目录 | 正常列出该目录的所有条目 |

### 2.4.2 边界/异常场景

| # | 用例名称 | path | 预期结果 |
|---|---------|------|----------|
| E1 | 根目录 `/` | `/` | ❌ `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| E2 | path 为文件 | 某个具体文件的路径 | ⚠️ `Warning: [NOT_DIR] 目标是文件，不是目录` |
| E3 | 不存在路径（在 /workspace 下） | `/workspace/nonexistent_dir` | ⚠️ `Warning: [NOT_FOUND] 路径不存在` |
| E4 | 路径不在 /workspace 下 | `/nonexistent/path` | ⚠️ `Warning: [PATH_NOT_UNDER] 路径不在 '/workspace/' 下` |
| E5 | 路径穿越 `..` | `/workspace/../.mambo` | ❌ `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` |

### 2.4.3 显示格式验证

| # | 验证点 | 预期行为 |
|---|--------|----------|
| F1 | 文件大小单位 | 自适应：B / KB / MB / GB，具体值取决于实际文件 |
| F2 | 目录后缀 | 所有目录以 `/` 结尾 |
| F3 | 路径格式 | 完整绝对路径，如 `/workspace/demo_project/src/main.py(大小)` |
| F4 | 排序规则 | 目录组在前、文件组在后；组内按名称 ASCII 升序，点文件（`.` 开头）排在文件组内最前 |
| F5 | 零大小文件 | 显示 `(0 B)` |
| F6 | 隐藏文件 | `.` 开头的文件正常列出 |


---

# 第三章: `read` — 文件内容读取

## 3.1 工具概述

| 属性 | 说明 |
|------|------|
| **工具名** | `read` |
| **功能** | 读取文件内容，支持分页（offset/limit）和行号显示 |
| **必填参数** | `file_path` (string) — 要读取的文件绝对路径 |
| **可选参数** | `offset` (integer, 默认 `0`)、`limit` (integer, 默认 `2000`)、`include_line_numbers` (boolean, 默认 `false`) |
| **支持的文件类型** | 文本文件（纯文本、代码、CSV、JSON、YAML、Markdown 等）；图片、音频、视频、PDF 返回多模态内容块 |

## 3.2 参数规范

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | ✅ 是 | — | 绝对路径，必须是**存在的文件**（非目录），必须在 `/workspace/` 下，不能含 `..` |
| `offset` | integer | ❌ 否 | `0` | 起始行偏移（0-indexed），必须 ≥ 0 且 < 文件总行数 |
| `limit` | integer | ❌ 否 | `2000` | 最大返回行数，必须 ≥ 1；超过剩余行数时返回剩余全部 |
| `include_line_numbers` | boolean | ❌ 否 | `false` | 为 `true` 时每行前缀 `     N	`（5 字符右对齐行号 + Tab） |

### 参数交互规则

| 规则 | 说明 |
|------|------|
| `offset` + `limit` | 分页：跳过 `offset` 行，最多返回 `limit` 行 |
| `offset` ≥ 文件行数 | ❌ 报错（包括 `offset=0` 对空文件） |
| `limit` > 剩余行数 | ✅ 正常返回剩余行，不报错 |
| `offset` > 剩余行数 | ❌ 报错 `偏移量 N 超过文件长度 (M 行)` |

## 3.3 返回值规范

### 正常返回

返回文件纯文本内容（或指定片段）：

```
<文件内容，原样输出>
```

- **不带行号** (`include_line_numbers=false`): 原样输出文件内容
- **带行号** (`include_line_numbers=true`): 每行前缀 `     N	`，N 为 1-indexed 行号，右对齐 5 字符宽度，Tab 分隔
- **空文件**: 两种情况均返回空字符串
- **offset/limit**: 只返回指定范围的行，行号仍然反映原始文件行号（不受 offset 影响）
- **文件末尾换行**: 保留原文件的末尾换行行为

### 错误返回

| 场景 | 返回信息 |
|------|----------|
| `file_path` 不存在 | `Error: [NOT_FOUND] 文件不存在` |
| `file_path` 是目录 | `Error: [IS_DIR] 目标是目录` |
| `file_path` 是根目录 `/` | `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| `file_path` 含 `..` | `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` |
| `file_path` 不在 `/workspace/` 下 | `Error: [PATH_NOT_UNDER] 路径不在 '/workspace/' 下` |
| `offset` < 0 | `Error: [INVALID] offset must be non-negative, got N` |
| `offset` ≥ 文件行数 | `Error: [INVALID] 偏移量 N 超过文件长度 (M 行)` |
| `limit` ≤ 0 | `Error: [INVALID] limit must be positive, got N` |

## 3.4 测试用例

> 测试基准目录: `/workspace/demo_project`（由你自行创建）
>
> **说明**: 测试中涉及时，用 `N` 表示文件的**总行数**（需在测试前自行获取）。

### 3.4.1 正常场景

| # | 用例名称 | file_path | offset | limit | include_line_numbers | 预期结果 |
|---|---------|-----------|--------|-------|----------------------|----------|
| N1 | 基本读取（无可选参数） | 某个 Python 源文件 | (默认) | (默认) | (默认) | 返回全部内容，无行号前缀 |
| N2 | 带行号读取 | 同 N1 文件 | (默认) | (默认) | `true` | 返回全部行，每行带 `     N	` 行号前缀，行号从 1 开始连续 |
| N3 | offset 跳过前几行 | 同 N1 文件 | `5` | (默认) | (默认) | 跳过前 5 行，从第 6 行开始返回剩余全部 |
| N4 | limit 限制行数 | 同 N1 文件 | (默认) | `10` | (默认) | 返回前 10 行 |
| N5 | offset + limit 分页 | 同 N1 文件 | `10` | `5` | (默认) | 返回第 11–15 行（共 5 行） |
| N6 | offset 接近末尾 + 行号 | 同 N1 文件 | `N - 10` | `10` | `true` | 返回最后最多 10 行，行号连续且反映原始行号 |
| N7 | 空文件读取 | 空文件路径 | (默认) | (默认) | (默认) | 返回空字符串 |
| N8 | 小文件 | 2–3 行的小文件 | (默认) | (默认) | (默认) | 返回全部内容 |
| N9 | 含中文/Unicode 的文件 | 含中文的 JSON 或文档 | (默认) | (默认) | (默认) | 返回全部内容，中文字符正常渲染 |
| N10 | 较大文件 + 行号 | 较大 Python 文件（80–120 行） | (默认) | (默认) | `true` | 返回全部行，行号 1–N 连续无截断 |
| N11 | offset 到倒数第二行 | 同 N1 文件 | `N - 2` | (默认) | (默认) | 返回最后 2 行 |
| N12 | offset 到最后一行 | 同 N1 文件 | `N - 1` | (默认) | (默认) | 返回最后 1 行 |
| N13 | limit 超过剩余行数 | 同 N1 文件 | 中间某个值 | 远大于剩余的值 | (默认) | 返回到末尾，不报错 |
| N14 | offset=0 + limit=1 | 同 N1 文件 | `0` | `1` | (默认) | 返回第 1 行 |
| N15 | offset=0 + limit=1 + 行号 | 同 N1 文件 | `0` | `1` | `true` | 返回 `     1	` + 第 1 行内容 |
| N16 | CSV 文件 | CSV 数据文件 | (默认) | (默认) | (默认) | 返回全部内容（表头 + 数据行） |
| N17 | Markdown 文件 | Markdown 文档 | (默认) | (默认) | (默认) | 返回全部内容 |

### 3.4.2 边界/异常场景

| # | 用例名称 | file_path | offset | limit | 预期结果 |
|---|---------|-----------|--------|-------|----------|
| E1 | 文件不存在 | 不存在文件的路径 | (默认) | (默认) | ❌ `Error: [NOT_FOUND] 文件不存在` |
| E2 | 目标是目录 | 某个目录的路径 | (默认) | (默认) | ❌ `Error: [IS_DIR] 目标是目录` |
| E3 | 路径为根目录 `/` | `/` | (默认) | (默认) | ❌ `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| E4 | 路径穿越 `..` | `/workspace/../.mambo/test` | (默认) | (默认) | ❌ `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` |
| E5 | 路径不在 /workspace 下 | `/etc/passwd` | (默认) | (默认) | ❌ `Error: [PATH_NOT_UNDER] 路径不在 '/workspace/' 下` |
| E6 | offset 负数 | 同 N1 文件 | `-1` | (默认) | ❌ `Error: [INVALID] offset must be non-negative, got -1` |
| E7 | limit 负数 | 同 N1 文件 | (默认) | `-5` | ❌ `Error: [INVALID] limit must be positive, got -5` |
| E8 | limit 为零 | 同 N1 文件 | (默认) | `0` | ❌ `Error: [INVALID] limit must be positive, got 0` |
| E9 | offset 等于文件行数 | 同 N1 文件 | `N` | (默认) | ❌ `Error: [INVALID] 偏移量 N 超过文件长度 (N 行)` |
| E10 | offset 超过文件行数 | 同 N1 文件 | `N + 10` | (默认) | ❌ `Error: [INVALID] 偏移量 ... 超过文件长度 (N 行)` |

### 3.4.3 显示格式验证

| # | 验证点 | 预期行为 |
|---|--------|----------|
| F1 | 行号格式 | `include_line_numbers=true` 时，行号为 5 字符右对齐 + Tab，如 `    1	`、`   10	`、`  100	` |
| F2 | 无行号模式 | `include_line_numbers=false`（默认）时，纯内容无前缀 |
| F3 | 内容完整性 | 返回内容与原文件逐行一致，无截断、无额外字符 |
| F4 | 中文/Unicode | 中文、Emoji 正常显示，不乱码 |
| F5 | 行号从 1 开始 | 无论 offset 多少，行号始终反映原始文件的实际行号（1-indexed） |
| F6 | 空文件行为 | 空文件返回空字符串，不报错（offset=0 时，0 行文件的 offset 合法） |

### 3.4.4 `read` vs `ls` vs `tree` 对比

| 维度 | `read` | `ls` | `tree` |
|------|--------|------|--------|
| 操作对象 | 文件内容 | 目录条目 | 目录树 |
| 递归 | — | ❌ 仅单层 | ✅ 多层 |
| 分页 | ✅ offset + limit | ❌ | ❌ |
| 行号 | ✅ include_line_numbers | ❌ | ❌ |
| 文件路径 | ❌ Error | ⚠️ Warning | ❌ Error |
| 不存在路径 | ❌ Error | ⚠️ Warning | ❌ Error |


---

# 第四章: `grep` — 文本内容搜索

## 4.1 工具概述

| 属性 | 说明 |
|------|------|
| **工具名** | `grep` |
| **功能** | 在指定路径下搜索匹配指定模式的文本，支持正则表达式和 glob 文件过滤 |
| **必填参数** | `pattern` (string) — 搜索模式 |
| **可选参数** | `path` (string, 默认 `/workspace`)、`glob` (string, 默认 `null`)、`regex` (boolean, 默认 `true`)、`offset` (integer, 默认 `0`)、`limit` (integer, 默认 `null`) |

## 4.2 参数规范

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `pattern` | string | ✅ 是 | — | 搜索模式；`regex=true` 时为正则表达式，`regex=false` 时为字面量字符串 |
| `path` | string | ❌ 否 | `/workspace` | 搜索范围，可以是目录（递归搜索）或单个文件 |
| `glob` | string | ❌ 否 | `null` | POSIX 风格的文件过滤模式（如 `*.py`、`**/*.json`），用于缩小搜索范围 |
| `regex` | boolean | ❌ 否 | `true` | `true` 时 `pattern` 按 Python 正则处理；`false` 时按精确子串匹配 |
| `offset` | integer | ❌ 否 | `0` | 结果起始索引（0-based），用于分批获取 |
| `limit` | integer | ❌ 否 | `null` | 单次返回的最大匹配数，`null` 表示最多返回硬上限（1000 条） |

### ⚠️ 关键行为规范: `path` 为文件时 `glob` 不生效

> **规范**: 当 `path` 参数指向单个文件（非目录）时，**`glob` 参数被忽略**，该文件必定被搜索。
>
> **原因**: `glob` 的作用是目录扫描时筛选文件。当你已经用 `path` 明确指定了文件，工具认为你就是要搜这个文件，不再用 `glob` 做二次过滤。
>
> 这意味着以下场景结果相同：
> - `path=main.py` + `glob=*.py` → ✅ 搜索（匹配时）
> - `path=main.py` + `glob=*.css` → ✅ 仍然搜索（glob 被忽略）
> - `path=main.py` + `glob=**/*.md` → ✅ 仍然搜索（glob 被忽略）
> - `path=main.py` + 不传 `glob` → ✅ 搜索

## 4.3 返回值规范

### 正常返回

每行一条匹配，格式为 `文件路径:行号: 匹配行内容`：

```
/workspace/demo_project/src/main.py:8: import json
/workspace/demo_project/src/main.py:9: import sys
```

- **有序性**: 按文件路径 → 行号的顺序排列
- **重复**: 每行独立匹配，同一行匹配多次 pattern 仍只输出一条
- **结果上限**: 最多返回 1000 条（硬上限）；配合 `offset`/`limit` 翻页

### 无匹配返回

```
No matches found.
```

### 错误返回

| 场景 | 返回信息 |
|------|----------|
| `path` 不存在 | `Warning: [NOT_FOUND] 路径不存在` |
| `path` 是根目录 `/` | `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| `path` 含 `..` | `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` |

## 4.4 测试用例

> 测试基准目录: `/workspace/demo_project`（由你自行创建）

### 4.4.1 正常场景 — `path` 为目录

| # | 用例名称 | path | glob | pattern | regex | 预期结果 |
|---|---------|------|------|---------|-------|----------|
| N1 | 目录递归搜索 Python 文件 | 含 Python 文件的目录 | `*.py` | `import` | true | 匹配所有含 `import` 的行 |
| N2 | 目录 + `**/*.py` 全递归 | 项目根目录 | `**/*.py` | `class` | true | 匹配所有含 `class` 的行 |
| N3 | 目录 + CSS glob | 项目根目录 | `**/static/**/*.css` | `font` | true | 匹配 CSS 文件中含 `font` 的行 |
| N4 | 目录 + 无 glob（默认全部文件） | config 目录 | (不传) | 某个存在的键名 | true | 匹配所有文件中含该键名的行 |
| N5 | 目录 + 字面量匹配 (`regex=false`) | 含 Python 文件的目录 | `*.py` | `from` | false | 精确匹配含 "from" 的行（正则元字符不转义） |
| N6 | 目录 + glob 不匹配任何文件 | 含 Python 文件的目录 | `*.rst` | `import` | true | `No matches found.` |
| N7 | 目录 + pattern 不匹配 | 含 Python 文件的目录 | `*.py` | `NONEXISTENT_XYZ123` | true | `No matches found.` |
| N8 | `path` 使用默认值 | (不传) | `**/*.md` | `#` | true | 匹配所有 Markdown 文件中的 `#` 标题行 |
| N9 | offset + limit 分页 | 项目根目录 | `**/*.py` | `def` | true | `offset=0, limit=3` 返回前 3 条；`offset=3, limit=3` 返回后续 |

### 4.4.2 正常场景 — `path` 为文件

> **⚠️ 这些用例验证「path 为文件时 glob 被忽略」的行为规范。**

| # | 用例名称 | path | glob | pattern | 预期结果 |
|---|---------|------|------|---------|----------|
| N10 | 文件 + glob 匹配 | 某个 Python 文件 | `*.py` | 文件中存在的字符串 | ✅ 搜索并返回结果 |
| N11 | 文件 + glob 不匹配（扩展名） | 同一个 Python 文件 | `*.css` | 同 N10 pattern | ✅ 仍然搜索并返回结果（glob 被忽略） |
| N12 | 文件 + glob 不匹配（通配符） | 同一个 Python 文件 | `**/test_*.py` | 同 N10 pattern | ✅ 仍然搜索并返回结果（glob 被忽略） |
| N13 | 文件 + glob 不匹配（完全不同） | 同一个 Python 文件 | `**/*.md` | 同 N10 pattern | ✅ 仍然搜索并返回结果（glob 被忽略） |
| N14 | 文件 + 不传 glob | 同一个 Python 文件 | (不传) | 同 N10 pattern | ✅ 搜索并返回结果，与 N10–N13 一致 |
| N15 | 文件 + pattern 不匹配 | 某个文件 | `*.py` | `NONEXISTENT_XYZ123` | `No matches found.` |
| N16 | 文件 + regex=false | 某个 Python 文件 | (不传) | `from` | false | 精确匹配含 "from" 的行 |
| N17 | 非 Python 文件 + glob 不匹配 | 某个 CSS 文件 | `*.py` | 文件中存在的字符串 | ✅ 仍然搜索并返回结果 |

### 4.4.3 边界/异常场景

| # | 用例名称 | path | glob | pattern | 预期结果 |
|---|---------|------|------|---------|----------|
| E1 | path 不存在 | `/workspace/nonexistent` | `*.py` | `test` | ⚠️ `Warning: [NOT_FOUND] 路径不存在` |
| E2 | path 为根目录 | `/` | `*.py` | `test` | ❌ `[PATH_IS_ROOT]` |
| E3 | path 含 `..` | `/workspace/../etc` | `*` | `test` | ❌ `[PATH_TRAVERSAL]` |
| E4 | 空 pattern | 项目根目录 | `*.py` | `` | `[INVALID]` |

### 4.4.4 显示格式验证

| # | 验证点 | 预期行为 |
|---|--------|----------|
| F1 | 输出格式 | `文件绝对路径:行号: 匹配行内容` |
| F2 | 行号 | 1-indexed，反映文件原始行号 |
| F3 | regex 模式 | 支持 Python 正则语法：`.*`、`^`、`$`、字符类、`|` 等 |
| F4 | regex=false 模式 | 按字面量子串匹配，正则元字符（`.`、`*` 等）不转义 |
| F5 | glob 通配符 | 支持 `*`（单层）、`**`（递归）、`?`（单字符）、`[...]`（字符类） |
| F6 | 结果排序 | 按文件路径字母序 → 行号数字序 |


---

# 第五章: `edit` — 文件内容替换

## 5.1 工具概述

| 属性 | 说明 |
|------|------|
| **工具名** | `edit` |
| **功能** | 在已有文件中查找并替换字符串，支持单次和多处替换 |
| **必填参数** | `file_path` (string)、`old_str` (string)、`new_str` (string) |
| **可选参数** | `replace_all` (boolean, 默认 `false`) |

## 5.2 参数规范

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | ✅ 是 | — | 目标文件的绝对路径，必须已存在（不同于 `write` 可创建新文件） |
| `old_str` | string | ✅ 是 | — | 要被替换的精确文本，不能为空 |
| `new_str` | string | ✅ 是 | — | 替换后的文本，可以为空（即删除匹配文本） |
| `replace_all` | boolean | ❌ 否 | `false` | `false` 时要求 `old_str` 在文件中唯一匹配；`true` 时替换所有匹配 |

### 核心语义

- **原子性**: 单次 `edit` 调用是原子的 —— 要么全部替换成功，要么完全不修改文件。
- **精确匹配**: `old_str` 必须完全匹配，包括空白字符（空格、换行、Tab）。
- **唯一性约束**: `replace_all=false` 时，`old_str` 在文件中**仅出现一次**，否则报错。
- **已存在约束**: 目标文件必须已存在。如需创建新文件，使用 `write`。

## 5.3 返回值规范

### 成功返回

```
File edited: <file_path> (<N> replacement(s))
```

- `N`: 实际替换次数（`replace_all=true` 时可 >1，否则 =1）

### 错误返回

| 场景 | 错误码 | 返回信息 |
|------|--------|----------|
| 文件不存在 | `NOT_FOUND` | `Error: [NOT_FOUND] 文件不存在，请用 write() 创建新文件` |
| 目标是目录 | `IS_DIR` | `Error: [IS_DIR] 目标是目录，无法编辑` |
| old_str 为空 | `INVALID` | `Error: [INVALID] old_str 不能为空` |
| old_str 未找到 | `OLD_STR_NOT_FOUND` | `Error: [OLD_STR_NOT_FOUND] 未找到要替换的文本` |
| 多次匹配 (replace_all=false) | `MULTI_OCCURRENCES` | `Error: [MULTI_OCCURRENCES] 匹配到 N 处，请用 replace_all=True 或提供更精确的上下文` |
| 路径含 `..` | `PATH_TRAVERSAL` | `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` |
| 路径为 `/` | `PATH_IS_ROOT` | `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| 路径不在 /workspace | `PATH_NOT_UNDER` | `Error: [PATH_NOT_UNDER] 路径不在 '/workspace/' 下` |

## 5.4 测试用例

> 测试基准目录: `/workspace/edit_test_fixtures/`（由你自行创建，见第零章 0.3 节）
>
> **说明**: 测试用例中引用的 `old_str` 值均为你在创建 fixture 时写入的内容，请根据实际内容调整。

### 5.4.1 正常场景

| # | 用例名称 | file_path | old_str | new_str | replace_all | 预期结果 |
|---|---------|-----------|---------|---------|-------------|----------|
| N1 | 基本单次替换 | `single_line.txt` | 你在文件中写入的唯一标记字符串 | 任意新文本 | (默认) | ✅ `1 replacement(s)` |
| N2 | replace_all 全部替换 | `multi_occurrence.txt` | 文件中重复出现的字符串（如 `apple`） | 任意新文本 | `true` | ✅ 全部匹配处替换，返回实际替换次数 |
| N3 | replace_all=false 唯一匹配 | `config.ini` | 某个具体的键值对 | 修改后的键值对 | `false` | ✅ `1 replacement(s)` |
| N4 | 多行替换 | `single_line.txt` | 文件中相邻的两行（含换行符） | 三行新文本 | (默认) | ✅ `1 replacement(s)`，2 行变为 3 行 |
| N5 | 替换文件开头内容 | `config.ini` | 第一个 `[section]` 标记 | 新的 section 名 | (默认) | ✅ `1 replacement(s)` |
| N6 | 替换文件末尾内容 | `config.ini` | 文件最后一行的键值对 | 修改后的值 | (默认) | ✅ `1 replacement(s)` |
| N7 | 含特殊字符的替换 | `special_chars.txt` | 文件中含特殊符号的某行 | 替换后的文本 | (默认) | ✅ `1 replacement(s)`，特殊字符正确匹配 |
| N8 | replace_all=true 但仅匹配一处 | `special_chars.txt` | 仅出现一次的字符串 | 替换文本 | `true` | ✅ `1 replacement(s)`，与 `replace_all=false` 行为一致 |

### 5.4.2 边界/异常场景

| # | 用例名称 | file_path | old_str | new_str | replace_all | 预期结果 |
|---|---------|-----------|---------|---------|-------------|----------|
| E1 | old_str 未找到 | `single_line.txt` | `NONEXISTENT_STRING_XYZ123` | `replacement` | (默认) | ❌ `[OLD_STR_NOT_FOUND] 未找到要替换的文本` |
| E2 | 多次匹配 replace_all=false | `multi_occurrence.txt` | 文件中重复出现的字符串 | 任意文本 | (默认) | ❌ `[MULTI_OCCURRENCES] 匹配到 N 处，请用 replace_all=True...` |
| E3 | 文件不存在 | 不存在的文件路径 | `test` | `replacement` | (默认) | ❌ `[NOT_FOUND] 文件不存在，请用 write() 创建新文件` |
| E4 | 目标是目录 | fixture 目录路径 | `test` | `replacement` | (默认) | ❌ `[IS_DIR] 目标是目录，无法编辑` |
| E5 | 空 old_str | `single_line.txt` | `` | `something` | (默认) | ❌ `[INVALID] old_str 不能为空` |
| E6 | 空 new_str（删除） | `single_line.txt` | 某行文本 | `` | (默认) | ✅ `1 replacement(s)`，匹配文本被删除 |
| E7 | 路径穿越 `..` | `/workspace/../etc/passwd` | `root` | `hacked` | (默认) | ❌ `[PATH_TRAVERSAL]` |
| E8 | 路径为根目录 | `/` | `test` | `replacement` | (默认) | ❌ `[PATH_IS_ROOT]` |
| E9 | 路径不在 /workspace | `/etc/hostname` | `test` | `replacement` | (默认) | ❌ `[PATH_NOT_UNDER]` |

### 5.4.3 并发场景

> **测试目的**: 验证 `edit` 工具在并发调用时的行为特性。

| # | 用例名称 | 并发策略 | 预期结果 |
|---|---------|----------|----------|
| C1 | 并发编辑不同文件 | 同时 `edit` `concurrent_a.txt` 和 `concurrent_b.txt`（不同 `file_path`） | ✅ 两个都成功，互不影响 |
| C2 | 并发编辑同一文件不同位置 | 同时 `edit` 同一文件的不同 `old_str`（如 `PART_1`、`PART_3`） | ✅ 两个都成功，各自替换独立区域 |
| C3 | 并发编辑同一文件同一位置 | 同时 `edit` 同一文件的相同 `old_str`（如 `PART_2`）；`new_str` 使用**不含 `old_str` 子串**的文本 | ⚠️ 先到成功，后到因 `OLD_STR_NOT_FOUND` 失败 |
| C4 | 混合并发 | 同时 5 个 `edit`：2 个不同文件 + 3 个同一文件不同位置 | ✅ 5 个全部成功，无冲突 |

### 5.4.4 并发行为总结

| 并发模式 | 结果 | 说明 |
|----------|------|------|
| 不同文件 | ✅ 全部成功 | 文件互斥，天然无冲突 |
| 同一文件 + 不同 old_str | ✅ 全部成功 | 工具内部处理了顺序合并 |
| 同一文件 + 相同 old_str | ⚠️ 仅一个成功 | 先完成的修改了文本，后到的找不到 old_str（前提：new_str 不含 old_str 子串） |

> **并发安全建议**: 避免对同一文件的同一位置发起并发编辑。如需批量修改同一文件的不同区域，可以安全并发；但同一区域的修改必须串行。


---

# 第六章: `write` — 文件写入与创建

## 6.1 工具概述

| 属性 | 说明 |
|------|------|
| **工具名** | `write` |
| **功能** | 创建新文件并写入内容；如果目标路径的父目录不存在，自动创建（`mkdir -p` 行为）。默认情况下，若文件已存在则报错，需显式指定 `overwrite=True` 才能覆盖 |
| **必填参数** | `file_path` (string)、`content` (string) |
| **可选参数** | `overwrite` (boolean, 默认 `false`) |

## 6.2 参数规范

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | ✅ 是 | — | 目标文件的绝对路径。父目录自动创建，但路径本身不能是已存在的目录 |
| `content` | string | ✅ 是 | — | 要写入的内容，可以为空字符串（即创建空文件） |
| `overwrite` | boolean | ❌ 否 | `false` | `false` 时若文件已存在则报错；`true` 时直接覆盖，无确认 |

### 核心语义

- **自动 mkdir -p**: 写入 `/a/b/c/file.txt` 时，若 `a/`、`a/b/`、`a/b/c/` 不存在，自动依次创建。
- **不自动覆盖**: 默认 `overwrite=false`，对已存在文件的写入会失败。这是为防止误覆盖而设的安全机制。
- **与 `edit` 分工**: `write` 用于创建新文件或完全替换；`edit` 用于部分替换已有文件内容。
- **空内容合法**: `content=""` 是合法操作，创建空文件。

## 6.3 返回值规范

### 成功返回

```
File written: <file_path>
```

### 错误返回

| 场景 | 错误码 | 返回信息 |
|------|--------|----------|
| 文件已存在 (overwrite=false) | `ALREADY_EXISTS` | `Error: [ALREADY_EXISTS] 文件已存在，请用 edit() 修改或用 overwrite=True 覆盖` |
| 目标是目录 | `IS_DIR` | `Error: [IS_DIR] 目标是目录，无法写入` |
| 路径为空 | `PATH_EMPTY` | `[PATH_EMPTY] 路径不能为空` |
| 路径含 `..` | `PATH_TRAVERSAL` | `[PATH_TRAVERSAL] path 不能包含 '..' 路径穿越` |
| 路径为 `/` | `PATH_IS_ROOT` | `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'` |
| 路径不在 /workspace | `PATH_NOT_UNDER` | `Error: [PATH_NOT_UNDER] 路径不在 '/workspace/' 下` |

## 6.4 测试用例

> 测试基准目录: `/workspace/write_test_fixtures/`（由你自行创建，见第零章 0.4 节）
>
> 产物文件建议放在该目录或其子目录下，与已有 fixture 隔离。

### 6.4.1 正常场景

| # | 用例名称 | file_path | content | overwrite | 预期结果 |
|---|---------|-----------|---------|-----------|----------|
| N1 | 基本写入新文件 | `.../N1_basic.txt` | 任意文本内容 | (默认) | ✅ `File written`，读取验证内容一致 |
| N2 | 自动创建父目录 (1 层) | `.../N2_auto_dir/subdir/file.txt` | 任意文本 | (默认) | ✅ `File written`，`subdir/` 自动创建 |
| N3 | 自动创建深层父目录 (多 层) | `.../N3_deep/a/b/c/d/e/deep_file.txt` | 任意文本 | (默认) | ✅ `File written`，所有层级目录自动创建 |
| N4 | overwrite=True 覆盖已有 | `.../existing_file.txt` | 新内容 | `true` | ✅ `File written`，原内容被替换 |
| N5 | 写入空内容 (空文件) | `.../N5_empty.txt` | `""` | (默认) | ✅ `File written`，文件存在但内容为空 |
| N6 | 多行内容 (含各种字符) | `.../N6_multiline.txt` | 多行文本，含 Unicode、Emoji、HTML 标签、JSON 片段等 | (默认) | ✅ `File written`，所有行正确保留 |
| N7 | 特殊字符 (转义/引号/反斜杠) | `.../N7_special_chars.txt` | 含反斜杠、引号、box-drawing 字符等 | (默认) | ✅ `File written`，特殊字符完整保留 |
| N8 | 写入到已存在目录中 | `.../no_overwrite_dir/new_file.txt` | 任意文本 | (默认) | ✅ `File written`，在已有目录中创建新文件 |

### 6.4.2 边界 / 异常场景

| # | 用例名称 | file_path | content | 预期错误 |
|---|---------|-----------|---------|----------|
| E1 | 覆盖已有文件但未设 overwrite | `.../no_overwrite_dir/file.txt` | 任意文本 | `[ALREADY_EXISTS]` 文件已存在 |
| E2 | 路径含 `..` 穿越 | `.../../escape.txt` | 任意文本 | `[PATH_TRAVERSAL]` |
| E3 | 路径为根目录 `/` | `/` | 任意文本 | `[PATH_IS_ROOT]` |
| E4 | 路径不在 /workspace 下 | `/etc/passwd` | 任意文本 | `[PATH_NOT_UNDER]` |
| E5 | 目标是已存在的目录 | `.../no_overwrite_dir` | 任意文本 | `[IS_DIR]` 目标是目录 |
| E6 | 路径为空字符串 | `""` | 任意文本 | `[PATH_EMPTY]` 路径不能为空 |

### 6.4.3 并发场景

| # | 用例名称 | 操作 | 预期结果 |
|---|---------|------|----------|
| C1 | 并发写入不同文件 | 同时写 `out_a.txt`、`out_b.txt`、`out_c.txt`（不同路径） | ✅ 全部成功，各自内容独立 |
| C2 | 并发写入同一文件 (无 overwrite) | 同时写 `concurrent_same.txt`（3 路） | ⚠️ 先到成功，后到 `ALREADY_EXISTS` |
| C3 | 并发写入同一文件 (overwrite=True) | 同时写 `concurrent_overwrite.txt`（3 路，均设 overwrite=true） | ✅ 全部成功，最终内容为最后完成写入的值 |
| C4 | 混合 5 路并发 | ① 新文件 `unique_a.txt`；②+④ 同文件 `shared.txt`（无 overwrite）；③+⑤ 同文件 `shared_ow.txt`（overwrite=true） | ✅ ①③⑤ 成功；② 成功（先到）；④ `ALREADY_EXISTS`（后到） |

## 6.5 与 `edit` 的协作关系

| 维度 | `write` | `edit` |
|------|---------|--------|
| **用途** | 创建新文件 / 整体替换 | 部分内容替换 |
| **文件不存在时** | 创建 | 报错 `NOT_FOUND` |
| **文件已存在时** | 报错（除非 overwrite=True） | 正常替换 |
| **mkdir -p** | ✅ 自动 | ❌ 不支持 |
| **并发安全** | 先到先得 / last-write-wins | 先到成功 / 后到 OLD_STR_NOT_FOUND |

> **最佳实践**: 创建新文件用 `write`，修改已有文件用 `edit`。需要完全重写已有文件时用 `write(overwrite=True)`。


---

# 附录: 变更记录

| 日期 | 版本 | 变更说明 |
|------|------|---------|
| 2026-01 | v2.0 | 重构文档结构：新增第零章（测试环境搭建指南），统合原附录 A–E；移除硬编码的行数/文件数/大小等具体数值，改为行为描述；移除历史实测结果记录 |
| 2025-01 | v1.0 | 初始版本，含 tree / ls / read / grep / edit / write 六个章节及附录 A–E |
