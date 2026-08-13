# ![mambo](doc/img/logo_hajimi.svg) MamboChat (曼波茶)

![Version](https://img.shields.io/badge/version-1.3.0-blue)
![License](https://img.shields.io/badge/license-GPLv3-green)
![Vue](https://img.shields.io/badge/frontend-Vue3%20%2B%20ElementPlus-42b883)
![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python3.11-009688)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)

**MamboChat** 是一款开源的支持 Linux/Windows 部署的 Web Harness 平台，可集成多服务商 API，实现电脑与手机网页端同步访问，数据云端存储让配置与历史记录多端共享，同时具备 vite coding 及角色扮演的能力。

**MamboChat** is an open-source web harness platform supporting Linux/Windows deployment. It integrates multiple service provider APIs for synchronized access from desktop and mobile browsers, stores data on the server so that configuration and conversation history are shared across devices, while also featuring vite coding and role-play capabilities.

[中文文档](./README.md) | [English Documentation](./doc/README_EN.md)

## ✨ 核心功能
**MamboChat** 安装后功能使用预览：[使用教程](doc/使用教程.md)  

*   **🤖 多模型聚合管理**
    *   支持 OpenAI、Google、DeepSeek 等多种服务商接口。关于不同模型的验证测试报告：[验证记录](doc/CheckRecord.md)
    *   支持自定义 API Host 和代理设置。
    *   支持对话模型与 Embedding 向量模型的统一管理。
    *   支持模型收藏与分组。
    *   支持自动识别模型能力（上下文长度、看图、思考模式），国产模型接入更省心。
*   **🤖 Mambo 智能体（Mambo Agent）**
    *   **复杂任务执行**：具备文件读写、命令执行、嵌套子智能体调用等能力，可用于复杂任务执行与远程服务器运维。
    *   **实时文件展示**：AI 读取文件/图片时可实时展示。图片展示有 GalGame 模式。
    *   **AI 安全预审**：可指定审核模型，仅危险操作需要人工确认。可自定义审核条件。
    *   **资源版本快照**：文件写入/修改/删除自动保留版本，随时可回滚。
    *   **长期记忆**：可挂载专属记忆资源，AI 记住长期偏好并写回新学内容。
    *   **对话自动压缩**：链式摘要压缩历史对话，压缩后进行中的计划不丢失。
    *   **MCP 智能接入**：工具较少时直接暴露，较多时自动切换按需查询模式。
    *   支持挂载资源、MCP 工具、Skill 技能包，并可与 SSH / Local / Resource / API 四种 Backend 协同工作。
*   **🔧 LLM 运行时工作环境（Backend）**
    *   **SSH Backend**：通过 SSH/SFTP 连接远程 Linux 服务器，让 Agent 直接操作远程文件和执行命令。
    *   **API Client/Backend**：在本地运行 Windows 客户端，通过 WebSocket 反向连接服务器，可在 NAT 内网环境中，让公网 Agent 直接操作本机。
    *   **Resource Backend**：基于资源管理页面的虚拟文件系统，更直观且绝对安全。
    *   **Local Backend**：直接操作部署本地的目标文件目录，可执行命令，并内置 Mambo 命令行工具。
*   **📚 本地知识库 (RAG)**
    *   支持上传 Markdown、TXT、PDF、Word 等多种格式文档。
    *   内置文件切分、向量化与语义检索功能（BM25 + 向量检索 + RRF）。
    *   支持在对话中动态挂载，可同时挂载多个知识库。
*   **🔌 MCP (Model Context Protocol) 支持**
    *   支持添加自定义 MCP 服务器。
    *   支持 MCP 工具调用审核模式（Human-in-the-Loop），可在工具执行前人工确认。
    *   支持根据工具数量阈值自动切换使用方式（少则直接暴露，多则按需查询）。
*   **🛠️ 资源与提示词管理**
    *   统一管理 System Prompts、消息模板、Skill 技能包。
    *   支持资源的版本控制与回滚。
*   **📦 Skill 技能包**
    *   创建和导入 Skill 扩展 Agent 能力。
    *   支持从本地文件、ZIP 压缩包或 GitHub 仓库导入。
*   **💬 强大的对话体验**
    *   支持流式响应与 Markdown/代码高亮渲染，支持 mermaid 和 svg 代码块图片渲染。
    *   **多模态支持**：支持图片、文件上传与解析，支持生图模型输出图片。
    *   **会话管理**：支持文件夹分类、拖拽排序、会话搜索、批量归档。
    *   **编辑器模式**：支持 Monaco Editor 代码编辑器模式。
    *   **消息分支**：支持消息编辑与重新生成，每次编辑保留历史分支，对话不再丢失。
    *   **会话复制**：支持将会话复制（可截断到指定消息），方便基于已有对话进行新探索。
    *   **会话导入导出**：支持将会话导出为 JSON 文件备份，并重新导入。
    *   **压缩对话**：支持压缩历史对话以节省 Token。
    *   **联网搜索**：会话设置支持联网搜索开关（"仅读网页"与"搜索+读网页"两种模式），网络请求支持走代理。
    *   **TAB 补全**：基于 Resource Backend 的 Tab 补全能力。
    *   **报文查看**：直观的报文日志查看功能，帮助你更深入地理解 Agent 逻辑。
*   **⌨️ mambo 命令行工具**
    *   提供 `mambo` CLI，可使 LLM 管理服务商/模型、资源、Skill、MCP 与 Agent 配置。
*   **⚙️ 全局个性化**
    *   自定义用户与 AI 头像。
    *   全局代理配置。
*   **📱 多端适配**
    *   完整的移动端界面，自动适配桌面与手机浏览器。
    *   支持中英文界面切换。

## 🚀 快速开始 (Docker 部署)

本项目提供了 `docker-compose.yml`，可一键启动服务。

### 前置要求
*   Docker Engine
*   Docker Compose

### 启动步骤

1.  **克隆仓库**
    ```bash
    git clone https://github.com/RAmenLch/mambochat.git
    cd mambochat
    ```

2.  **启动服务**
    ```bash
    docker compose up -d --build
    ```

3.  **访问应用**
    打开浏览器访问：`http://localhost:24911`

    *   数据持久化目录：
        *   `./DB`: 存放 SQLite 数据库文件。
        *   `./uploads`: 存放上传的文件和头像。

## 🚀 快速开始 (Windows 桌面客户端)

MamboChat 提供 Windows 桌面客户端安装包，一键安装即可使用，无需手动配置 Python 环境。

### 安装步骤

1. **下载安装包**
   从 [Releases](https://github.com/RAmenLch/mambochat/releases) 页面下载最新版本的安装包（`MamboChat-Setup-x.x.x.exe`）。

2. **运行安装程序**
   双击 `MamboChat-Setup-1.3.0.exe`，按向导完成安装（可选择自定义安装目录）。

3. **启动应用**
   安装完成后，从桌面快捷方式或开始菜单启动 MamboChat。
   ![桌面端](doc/img/桌面端.png)

4. **桌面客户端配置**
[桌面客户端配置文档](doc/DesktopSettings.md)

> 桌面客户端已内嵌完整的 Python 运行时环境、前端资源、后端代码及 MCP Server，开箱即用。
> 所有用户数据（数据库、上传文件、配置文件）存储在 `%APPDATA%/MamboChat/` 目录下。



## 💻 本地开发指南

如果你需要进行二次开发，可以分别启动前后端服务。

### 后端

1.  进入后端目录：
    ```bash
    cd backend
    ```
2.  安装依赖：
    ```bash
    uv pip install -r pyproject.toml
    ```
3.  设置环境变量并启动：
    ```bash
    export PYTHONPATH=$PYTHONPATH:$(pwd)/..
    uvicorn backend.main:app --reload --port 8000
    ```

### 前端

1.  进入前端目录：
    ```bash
    cd frontend/mambo
    ```
2.  安装依赖：
    ```bash
    npm install
    ```
3.  启动开发服务器：
    ```bash
    npm run dev
    ```

### 从源码构建桌面客户端

1. **准备环境**（下载 Python/Node.js 运行时、安装前后端依赖、构建前端）：
   ```bash
   build_and_start.bat
   ```
   > 脚本会自动完成环境初始化并启动服务，等待前后端均启动成功后，关闭两个弹出的服务窗口即可。

2. **配置环境变量**：
   在执行 `npm` 命令之前，请确保系统已配置 Node.js 和 npm 的环境变量。如果 `build_and_start.bat` 脚本下载的 Node.js 未自动添加到 `PATH`，需手动将 `runtime/node` 目录添加到系统环境变量中，否则后续 `npm install` 等命令将无法执行。

3. **构建桌面客户端**：
   ```bash
   cd desktop
   npm install
   npm run dist:win    # 输出 NSIS 安装包 + 便携版到 release/
   ```


## 🤝 贡献

欢迎任何形式的贡献！如果您有好的想法、发现了 Bug，或者希望添加新功能，请随时提交 Pull Request 或创建 Issue。

## 👨‍💻 开发计划
- [ ] 抽象关键功能，支持插件能力
- [ ] 强化 Agent 长程能力/ 路由Agent
- [ ] 强化角色扮演能力
- [ ] 持续修复和优化
