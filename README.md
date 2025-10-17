# LLM-API Client (Mambo) - v1.0.1

[![版本](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/RAmenLch/mambochat/releases/tag/v1.0.1)
[![许可证](https://img.shields.io/badge/license-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![技术栈](https://img.shields.io/badge/Tech-FastAPI%20%26%20Vue%203-brightgreen)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](docker-compose.yml)

一个功能完善、配置灵活、体验丝滑的本地化大语言模型（LLM）API 客户端。它允许您通过一个统一的界面，连接、管理并与来自不同服务商的多个大语言模型进行高效交互。

---

## 📸 界面预览

<!-- 📸 TODO: 请将这里的说明替换为您的实际截图 -->

|                   聊天主界面                    |
|:------------------------------------------:| 
| ![会话.png](doc/img/%E4%BC%9A%E8%AF%9D.png)  |
|   **流畅的流式对话与精细的消息控制以及支持拖拽排序与层级管理的会话列表**    |

|                         配置页面以及API配置页面                          | 
|:--------------------------------------------------------------:| 
| ![系统设置.png](doc/img/%E7%B3%BB%E7%BB%9F%E8%AE%BE%E7%BD%AE.png)  |
|            **一站式管理，支持API自动发现模型以及灵活的全局默认设置与独立的会话参数**            |


## ✨ 核心功能

本项目旨在提供编者能用得爽的的本地化 LLM 聊天体验，核心功能包括：

#### ⚙️ 全局与服务商管理

*   **统一管理中心**：在一个界面中完成服务商的创建及其下属模型的添加、修改和删除。
*   **API 自动发现**：一键从兼容 OpenAI 规范的 API Host 自动抓取可用模型列表。
*   **连接测试**：在配置凭证时即时验证 API Host 和 Key 的有效性。
*   **全局默认模型**：可指定一个全局模型，作为新会话的默认选项，并在原模型被删除时作为**无感回退**的保障。
*   **新会话默认参数**：可配置全局默认的 `Temperature`、`Top P`、上下文数量等参数，应用于所有新创建的会话。

#### 🗂️ 会话与层级管理

*   **文件夹支持**：创建文件夹对会话进行分类，支持无限层级。
*   **自由拖拽**：通过拖拽轻松调整会话和文件夹的顺序及层级关系。
*   **会话复制**: 一键复制包含完整历史消息的新会话。
*   **草稿自动保存**：输入框中未发送的内容在切换会话后会自动缓存和恢复。

#### 💬 聊天交互与消息控制

*   **核心聊天功能**：
    *   支持**流式响应** (`Server-Sent Events`)，实时渲染 AI 回复。
    *   支持随时为当前会话**更换 AI 模型**。
    *   支持为每个会话独立配置 **System Prompt** 和模型参数。
*   **生成过程控制**：
    *   在 AI 生成回复时可随时**中断**。
    *   对 AI 的最新回复进行**重新生成**。
*   **精细化消息操作**（通过悬浮菜单）：
    *   对任意消息进行**复制**和**删除**。
    *   支持**编辑**用户和 AI 的消息内容，提供代码块单独修改的功能。
    *   支持单个消息多分块输入，这样修改发送的内容就更方便了。
    *   对用户消息，提供“**保存并重新发送**”功能，会删除该消息之后的所有对话并重新触发生成。
    *   提供**从指定消息处重新生成**的增强功能。
    

## 🛠️ 技术栈

项目采用不成熟且高效的前后端分离架构。全是让哈基米给我搭的，手码率 0.9%。

*   **后端 (Backend)**:
    *   **框架**: `Python 3.11`, `FastAPI`
    *   **数据库**: `SQLite` (通过 `SQLAlchemy` 异步操作)
    *   **数据校验**: `Pydantic`
    *   **部署**: `Gunicorn` + `Uvicorn`
*   **前端 (Frontend)**:
    *   **框架/库**: `Vue 3` (Composition API, `<script setup>`), `Vite`, `TypeScript`
    *   **UI 组件库**: `Element Plus`
    *   **状态管理**: `Pinia`
    *   **HTTP 请求**: `axios` (标准 API), `@microsoft/fetch-event-source` (SSE 流式处理)
    *   **Markdown**: `markdown-it` (代码高亮)
*   **部署 (Deployment)**: `Docker`, `Docker Compose`

## 🚀 快速开始 (使用 Docker)

我们强烈推荐使用 Docker 进行部署，这是最简单、最快捷的方式。

#### **前提条件**

*   已安装 [Docker](https://docs.docker.com/get-docker/)
*   已安装 [Docker Compose](https://docs.docker.com/compose/install/)

#### **部署步骤**

1.  **克隆本仓库**
    ```bash
    git git@github.com:RAmenLch/mambochat.git
    cd mambochat
    ```

2.  **启动服务**
    使用 `docker-compose` 一键启动前后端服务。
    ```bash
    docker-compose up -d
    ```
    *   后端服务将在 Docker 网络内部的 `8000` 端口运行。
    *   前端服务将被 Nginx 代理，并映射到宿主机的 `24911` 端口。
    *   SQLite 数据库文件 `mambo.dat` 将被持久化存储在项目根目录的 `DB/` 文件夹下。

3.  **开始使用**
    打开浏览器，访问 `http://localhost:24911` 即可开始使用！

    > **提示**: 如果 `24911` 端口已被占用，您可以修改 `docker-compose.yml` 文件中的 `ports` 映射，例如将 `"24911:80"` 修改为 `"your-port:80"`。

## 👨‍💻 开发环境设置

如果您希望在本地进行二次开发，请按以下步骤设置：

#### **1. 后端 (Backend)**

```bash
# 1. 进入后端目录
cd backend

# 2. 创建并激活虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # on Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动开发服务器 (支持热重载)
#    FastAPI 将在 http://127.0.0.1:8000 运行
uvicorn backend.main:app --reload
```

## 👨‍💻 下一步的开发计划
1.  抽象关键功能,支持插件能力
2.  我之初心,构建一个用于角色扮演的插件

## 🐱耄耋靓照
![logo.svg](frontend/mambo/public/logo.svg)