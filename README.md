# ![mambo](doc/img/logo_hajimi.svg) MamboChat (曼波茶)

![Version](https://img.shields.io/badge/version-1.1.3-blue)
![License](https://img.shields.io/badge/license-GPLv3-green)
![Vue](https://img.shields.io/badge/frontend-Vue3%20%2B%20ElementPlus-42b883)
![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python3.11-009688)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)

**MamboChat** 是一款简约而强大的 AI Web 平台，融合了多服务商模型聚合、本地知识库 (RAG) 与 MCP (Model Context Protocol) 协议扩展。旨在为用户提供高度可定制、隐私安全且功能丰富的 AI 对话体验。

**MamboChat** is a minimalist yet powerful AI Web platform featuring multi-provider model aggregation, local knowledge base integration (RAG), and MCP (Model Context Protocol) extensions. It is designed to deliver a highly customizable, privacy-focused, and feature-rich conversational AI experience.

[中文文档](./README.md) | [English Documentation](./doc/README_EN.md)

## ✨ 核心功能
本应用的优点: 首先是个可部署的Web平台,也就是可以在线使用! 其次支持多种大模型平台接口,并且有很多好用的工具!总之本人用起来很不错!  
**MamboChat** 安装后功能使用预览: [使用教程](doc/使用教程.md)  
*   **🤖 多模型聚合管理**
    *   支持 OpenAI、Google、DeepSeek 等多种服务商接口。关于不同模型的验证测试报告:[验证记录](doc/CheckRecord.md)
    *   支持自定义 API Host 和代理设置。
    *   支持对话模型与 Embedding 向量模型的统一管理。
*   **📚 本地知识库 (RAG)**
    *   支持上传 Markdown, TXT 等多种格式文档。
    *   内置文件切分、向量化与语义检索功能。
    *   支持在对话中动态挂载知识库。
*   **🔌 MCP (Model Context Protocol) 支持**
    *   实现了 MCP 协议，支持扩展 AI 的能力。
    *   支持添加自定义 MCP 服务器。
*   **💬 强大的对话体验**
    *   支持流式响应 与 Markdown/代码高亮渲染。
    *   **多模态支持**：支持图片、文件上传与解析。支持生图模型输出图片。
    *   **会话管理**：支持文件夹分类、拖拽排序、会话搜索。
    *   **编辑器模式**：支持 Monaco Editor 代码编辑器模式。
    *   **编辑对话**：支持消息编辑、重新生成。
    *   **压缩对话**: 支持压缩历史对话。✨ **主推特色功能** 请好好的看着我!
*   **🛠️ 资源与提示词管理**
    *   统一管理 System Prompts、消息模板。 ✨ **主推特色功能** 请好好的看着我!
    *   支持资源的版本控制与回滚。
*   **⚙️ 全局个性化**
    *   自定义用户与 AI 头像。
    *   全局代理配置。

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
1.  **克隆仓库或通过github下载压缩包**
    ```bash
    git clone https://github.com/RAmenLch/mambochat.git
    cd mambochat
    ```
2.  **双击或右键点击"在终端中打开"(WIN11)并执行命令**
    ```bash
      PS C:\mambochat> .\start.bat
    ```
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

## 👨‍💻 下一步的开发计划
1. 抽象关键功能,支持插件能力
2. 强化 Agent 能力
3. 我之初心,构建一个用于角色扮演的插件
4. 修复强化功能
