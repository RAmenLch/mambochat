# ![mambo](doc/img/logo_hajimi.svg) MamboChat (曼波茶)

![Version](https://img.shields.io/badge/version-1.2.0-blue)
![License](https://img.shields.io/badge/license-GPLv3-green)
![Vue](https://img.shields.io/badge/frontend-Vue3%20%2B%20ElementPlus-42b883)
![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python3.11-009688)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)

**MamboChat** 是一款开源的支持 Linux/Windows 部署的 Web 对话平台，可集成多服务商 API，实现电脑与手机网页端同步访问，数据云端存储让配置与历史记录多端共享，同时具备知识库与 MCP 调用能力。

**MamboChat** is a web-based chat platform that integrates multiple service provider APIs, supporting Linux/Windows deployment with seamless access via desktop and mobile browsers. Data is stored on the server, enabling synchronized configuration and conversation history across all devices, while also featuring knowledge base and MCP integration capabilities.

[中文文档](./README.md) | [English Documentation](./doc/README_EN.md)

## ✨ 核心功能
**MamboChat** 安装后功能使用预览: [使用教程](doc/使用教程.md)  

*   **🤖 多模型聚合管理**
    *   支持 OpenAI、Google、DeepSeek 等多种服务商接口。关于不同模型的验证测试报告: [验证记录](doc/CheckRecord.md)
    *   支持自定义 API Host 和代理设置。
    *   支持对话模型与 Embedding 向量模型的统一管理。
    *   支持模型收藏与分组。
*   **📚 本地知识库 (RAG)**
    *   支持上传 Markdown、TXT、PDF、Word 等多种格式文档。
    *   内置文件切分、向量化与语义检索功能（BM25 + 向量检索 + RRF）。
    *   支持在对话中动态挂载，可同时挂载多个知识库。
*   **🔌 MCP (Model Context Protocol) 支持**
    *   实现了 MCP 协议，支持扩展 AI 的能力。
    *   支持添加自定义 MCP 服务器。
    *   支持 MCP 工具调用审核模式（Human-in-the-Loop），可在工具执行前人工确认。
*   **🤖 智能 Agent**
    *   **对话型 Agent (ReAct)**：基于工具调用进行推理，可挂载知识库、MCP 工具和 Skill 技能包。
    *   **复杂型 Agent (Deep)**：基于 [deepagents](https://github.com/langchain-ai/deepagents) 项目，具备文件读写、命令执行、嵌套子agent调用等能力，可用于复杂任务执行与远程服务器运维。
    *   支持 Agent 挂载资源、MCP 工具、Skill 技能包，并可与远程 Backend 协同工作。
*   **🔧 远程 Backend**
    *   **SSH Backend**：通过 SSH/SFTP 连接远程 Linux 服务器，让 Agent 直接操作远程文件和执行命令。
    *   **API Client**：在本地运行客户端，通过 WebSocket 反向连接服务器，无需公网 IP 即可将本地文件暴露给 Agent。
*   **📦 Skill 技能包**
    *   创建和导入 Skill 扩展 Agent 能力。
    *   支持从本地文件、ZIP 压缩包或 GitHub 仓库导入。
*   **💬 强大的对话体验**
    *   支持流式响应与 Markdown/代码高亮渲染，支持mermaid和svg代码块图片渲染。
    *   **多模态支持**：支持图片、文件上传与解析，支持生图模型输出图片。
    *   **会话管理**：支持文件夹分类、拖拽排序、会话搜索、批量归档。
    *   **编辑器模式**：支持 Monaco Editor 代码编辑器模式。
    *   **消息分支**：支持消息编辑与重新生成，每次编辑保留历史分支，对话不再丢失。
    *   **会话复制**：支持将会话复制（可截断到指定消息），方便基于已有对话进行新探索。
    *   **压缩对话**：支持压缩历史对话以节省 Token。
*   **🛠️ 资源与提示词管理**
    *   统一管理 System Prompts、消息模板、Skill 技能包。
    *   支持资源的版本控制与回滚。
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

## 🚀 快速开始 (Windows 一键启动)
1.  **克隆源码或通过github下载压缩包**
    ```bash
    git clone https://github.com/RAmenLch/mambochat.git
    cd mambochat
    ```
2.  **双击或右键点击"在终端中打开"(WIN11)并执行命令**
    ```bash
    PS C:\mambochat> .\build_and_start.bat
    ```
    **如果是下载的发布版压缩包如`mambochat-v120-winx64.zip`,则双击或执行该文件**
    ```bash
    PS C:\mambochat> .\start.bat
    ```    
> build_and_start.bat 检查并下载依赖后启动  start.bat 直接启动
> 注: 该脚本未在不同环境下经历测试,若出现问题欢迎创建 Issue

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
    # 以及安装 MCP Server 相关依赖
    uv pip install -r ../MCP_SERVER/ddgs/pyproject.toml
    uv pip install -r ../MCP_SERVER/knowledge_base/pyproject.toml
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

## 🤝 贡献

欢迎任何形式的贡献！如果您有好的想法、发现了 Bug，或者希望添加新功能，请随时提交 Pull Request 或创建 Issue。

## 👨‍💻 开发计划
- [ ] 抽象关键功能，支持插件能力
- [ ] 强化 Agent 能力 
- [ ] 构建角色扮演插件
- [ ] 持续修复和优化
