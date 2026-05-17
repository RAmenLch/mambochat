# ![mambo](img/logo_hajimi.svg) MamboChat

![Version](https://img.shields.io/badge/version-1.2.4-blue)
![License](https://img.shields.io/badge/license-GPLv3-green)
![Vue](https://img.shields.io/badge/frontend-Vue3%20%2B%20ElementPlus-42b883)
![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python3.11-009688)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](../docker-compose.yml)

**MamboChat** is a web-based chat platform that integrates multiple service provider APIs, supporting Linux/Windows deployment with seamless access via desktop and mobile browsers. Data is stored on the server, enabling synchronized configuration and conversation history across all devices, while also featuring knowledge base and MCP integration capabilities.

[中文文档](../README.md) | [English Documentation](./README_EN.md)

## ✨ Core Features

**Feature Preview & Usage**: [User Guide](./Tutorial_EN.md)

*   **🤖 Multi-Model Aggregation**
    *   Support for multiple providers including OpenAI, Google, DeepSeek, etc. See [Verification Records](./CheckRecord_EN.md) for model compatibility.
    *   Custom API Host and proxy configuration.
    *   Unified management for chat and embedding models.
    *   Model favorites and grouping.
*   **📚 Local Knowledge Base (RAG)**
    *   Upload documents in Markdown, TXT, PDF, Word, and other formats.
    *   Built-in file chunking, vector embedding, and semantic search (BM25 + vector retrieval + RRF).
    *   Dynamically mount knowledge bases during conversations. Multiple knowledge bases can be mounted simultaneously.
*   **🔌 MCP (Model Context Protocol) Support**
    *   Native implementation of MCP to extend AI capabilities.
    *   Supports custom MCP servers (Stdio/SSE connections).
    *   Supports MCP tool review mode (Human-in-the-Loop), allowing manual confirmation before tool execution.
*   **🤖 Intelligent Agents**
    *   **Conversational Agent (ReAct)**: Reasoning through tool calls, with support for knowledge bases, MCP tools, and Skill packs.
    *   **Advanced Agent (Deep)**: Based on the [deepagents](https://github.com/langchain-ai/deepagents) project, capable of reading/writing files, executing commands, nested sub-agent invocation, and performing remote server operations.
    *   Agents can be equipped with resources, MCP tools, Skill packs, and can collaborate with remote Backends.
*   **🔧 Remote Backend**
    *   **SSH Backend**: Connect to remote Linux servers via SSH/SFTP, enabling the Agent to directly operate remote files and execute commands.
    *   **API Client**: Run a client locally that connects to the server via WebSocket — no public IP required to expose your local files to the Agent.
*   **📦 Skill Packs**
    *   Create and import Skills to extend Agent capabilities.
    *   Import from local files, ZIP archives, or GitHub repositories.
*   **💬 Robust Conversation Experience**
    *   Stream responses with Markdown and code highlighting, supporting mermaid and svg code block image rendering.
    *   **Multimodal Support**: Image/file upload and parsing. Support for image generation models.
    *   **Session Management**: Folder categorization, drag-and-drop sorting, search, and batch archiving.
    *   **Editor Mode**: Integrated Monaco Editor.
    *   **Message Branching**: Edit and regenerate messages while preserving the full edit history — conversations are never lost.
    *   **Conversation Copying**: Duplicate conversations (with optional truncation) to explore new directions from existing dialogues.
    *   **Context Compression**: Compresses conversation history to save tokens.
*   **🛠️ Resource & Prompt Management**
    *   Unified management for System Prompts, Message Templates, and Skill packs.
    *   Version control and rollback for resources.
*   **⚙️ Global Personalization**
    *   Custom avatars for users and AI.
    *   Global proxy configuration.
*   **📱 Multi-Device Support**
    *   Full mobile interface with automatic adaptation for desktop and mobile browsers.
    *   Chinese and English language switching.

## 🚀 Quick Start (Docker)

Use the provided `docker-compose.yml` to launch the service instantly.

### Prerequisites
*   Docker Engine
*   Docker Compose

### Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/RAmenLch/mambochat.git
    cd mambochat
    ```

2.  **Start Services**
    ```bash
    docker compose up -d --build
    ```

3.  **Access the Application**
    Visit `http://localhost:24911` in your browser.

    *   **Persistence**:
        *   `./DB`: SQLite database files.
        *   `./uploads`: Uploaded files and avatars.

## 🚀 Quick Start (Windows Desktop Client)

MamboChat provides a Windows desktop client installer — just install it and you're ready to go, no manual Python setup required.

### Installation Steps

1. **Download the installer**
   Get the latest version from the [Releases](https://github.com/RAmenLch/mambochat/releases) page (`MamboChat-Setup-x.x.x.exe`).

2. **Run the installer**
   Double-click `MamboChat-Setup-1.2.4.exe` and follow the wizard (you can choose a custom install directory).

3. **Launch MamboChat**
   After installation, start MamboChat via the desktop shortcut or Start Menu.
   ![Desktop Client](img/桌面端.png)

4. **Desktop Client Settings**
   [Desktop Client Configuration Guide](./DesktopSettings_EN.md)

> The desktop client comes bundled with a complete Python runtime, frontend resources, backend code, and MCP Server — ready to use out of the box.
> All user data (databases, uploaded files, config files) is stored under `%APPDATA%/MamboChat/`.


## 💻 Local Development Guide

If you need to do secondary development, you can start the frontend and backend services separately.

### Backend

1.  Navigate to the backend directory:
    ```bash
    cd backend
    ```
2.  Install dependencies:
    ```bash
    uv pip install -r pyproject.toml
    # Install MCP Server dependencies
    uv pip install -r ../MCP_SERVER/ddgs/pyproject.toml
    uv pip install -r ../MCP_SERVER/knowledge_base/pyproject.toml
    ```
3.  Set environment variables and start:
    ```bash
    export PYTHONPATH=$PYTHONPATH:$(pwd)/..
    uvicorn backend.main:app --reload --port 8000
    ```

### Frontend

1.  Navigate to the frontend directory:
    ```bash
    cd frontend/mambo
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Start the development server:
    ```bash
    npm run dev
    ```

### Build Desktop Client from Source

1. **Prepare environment** (download Python/Node.js runtimes, install frontend/backend dependencies, build frontend):
   ```bash
   build_and_start.bat
   ```
   > This script will automatically initialize the environment and start services. Once both frontend and backend are running, close the two service windows.

2. **Configure environment variables**:
   Before running `npm` commands, make sure Node.js and npm are in your system `PATH`. If the `build_and_start.bat` script does not automatically add the downloaded Node.js to `PATH`, you need to manually add the `runtime/node` directory to your system environment variables; otherwise, subsequent `npm install` and related commands will fail.

3. **Build the desktop client**:
   ```bash
   cd desktop
   npm install
   npm run dist:win    # Outputs NSIS installer + portable edition to release/
   ```

## 🤝 Contributing

Contributions are welcome! Whether you have ideas, found a bug, or want to add a feature, feel free to submit a Pull Request or create an Issue.

## 👨‍💻 Roadmap
- [ ] Abstract key functionalities to support plugin capabilities
- [ ] Enhance Agent capabilities
- [ ] Build a role-playing plugin
- [ ] Ongoing bug fixes and optimizations.
