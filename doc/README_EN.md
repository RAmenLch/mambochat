# ![mambo](img/logo_hajimi.svg) MamboChat

![Version](https://img.shields.io/badge/version-1.1.3-blue)
![License](https://img.shields.io/badge/license-GPLv3-green)
![Vue](https://img.shields.io/badge/frontend-Vue3%20%2B%20ElementPlus-42b883)
![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Python3.11-009688)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](../docker-compose.yml)

**MamboChat** is a minimalist yet powerful AI Web platform featuring multi-provider model aggregation, local knowledge base integration (RAG), and MCP (Model Context Protocol) extensions. It is designed to deliver a highly customizable, privacy-focused, and feature-rich conversational AI experience.

[中文文档](../README.md) | [English Documentation](./README_EN.md)

## ✨ Core Features
**Highlights**: MamboChat is a deployable web platform ready for online use! It supports various LLM platform interfaces and comes with numerous practical tools. It offers an excellent user experience!

**Feature Preview & Usage**: [User Guide](./Tutorial_EN.md)

*   **🤖 Multi-Model Aggregation**
    *   Support for multiple providers including OpenAI, Google, DeepSeek, etc. See [Verification Records](./CheckRecord_EN.md) for model compatibility.
    *   Custom API Host and proxy configuration.
    *   Unified management for chat and embedding models.
*   **📚 Local Knowledge Base (RAG)**
    *   Upload documents in Markdown, TXT, and other formats.
    *   Built-in file chunking, vector embedding, and semantic search.
    *   Dynamically mount knowledge bases during conversations.
*   **🔌 MCP (Model Context Protocol) Support**
    *   Native implementation of MCP to extend AI capabilities.
    *   Supports custom MCP servers (Stdio/SSE connections).
*   **💬 Robust Conversation Experience**
    *   Stream responses with Markdown and code highlighting.
    *   **Multimodal Support**: Image/file upload and parsing. Support for image generation models.
    *   **Session Management**: Folder categorization, drag-and-drop sorting, and search.
    *   **Editor Mode**: Integrated Monaco Editor.
    *   **Message Editing**: Edit messages and regenerate responses.
    *   **Context Compression**: Compresses conversation history to save tokens. ✨ **Featured Highlight**
*   **🛠️ Resource & Prompt Management**
    *   Unified management for System Prompts and Message Templates. ✨ **Featured Highlight**
    *   Version control and rollback for resources.
*   **⚙️ Global Personalization**
    *   Custom avatars for users and AI.
    *   Global proxy configuration.

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
    docker-compose up -d
    ```

3.  **Access the Application**
    Visit `http://localhost:24911` in your browser.

    *   **Persistence**:
        *   `./DB`: SQLite database files.
        *   `./uploads`: Uploaded files and avatars.

## 🚀 Quick Start (Windows)

1.  **Clone or Download**
    ```bash
    git clone https://github.com/RAmenLch/mambochat.git
    cd mambochat
    ```
2.  **Run the Script**
    Double-click `start.bat` or run it in a terminal:
    ```bash
    PS C:\mambochat> .\start.bat
    ```
> **Note**: This script may require environment adjustments. If you encounter issues, feel free to open an Issue.

## 💻 Local Development Guide

For secondary development, you can run the frontend and backend separately.

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

## 🤝 Contributing

Contributions are welcome! Whether you have ideas, found a bug, or want to add a feature, feel free to submit a Pull Request or create an Issue.

## 👨‍💻 Roadmap
1. Abstract key functionalities to support a plugin system.
2. Enhance Agent capabilities.
3. **Original Vision**: Build a plugin specifically for role-playing scenarios.
4. Bug fixes and feature reinforcement.
