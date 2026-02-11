## 1. AI Model & Provider Configuration  
### Configuring Providers and Models  
(1) **Enter Settings**  
Click the configuration button to enter the system settings page.  
![Enter Settings](img/进入配置页面.png)  
(2) **Add Provider**  
Click the "Add Provider" button.  
![Add Provider](img/新增服务商.png)  
(3) **Configure Provider**  
Fill in the provider's configuration details.  
![Configure Provider](img/配置服务商.png)  
(4) **Model Configuration (Optional)**  
![Model Config](img/模型配置.png)  
> **Note**: OpenRouter's API usually returns detailed model info, so extra config might not be needed. For other platforms, this step is recommended to set parameters or enable multimodal features like image input (MamboChat v1.1.0 currently supports image input only).  

## 2. Conversations  
(1) **New Chat**  
Right-click in the chat list and select "New Chat".  
![New Chat](img/新建会话.png)  
(2) **Chat Settings**  
Click the chat settings button to set System Prompts and other features.  
![Chat Settings](img/会话配置.png)  
(3) **Chat Folders**  
Use folders to organize your chats.  
![Chat Folders](img/分组会话使用.png)  
(4) **File Upload & Multimodal Output**  
Supports text file uploads and multimodal content generation.  
![File Upload](img/文件写入和图片输出.png)  
(5) **Image Upload & Parsing**  
**Critical**: You must configure `image` in the input modality settings, or image data will not be sent to the API.  
![Image Modality Config](img/配置图片输入模态.png)  
Once configured, you can send images to the AI.  
![Send Image](img/输入图片.png)  
(6) **Context Compression**  
Edit the prompt used for context compression in the global settings.  
![Compression Settings](img/在全局配置页面编辑压缩上下文.png)  
When a conversation gets long:  
![Long Context](img/压缩上下文1.png)  
Use context compression to seamlessly optimize costs and maintain focus.  
![Compressed Context](img/压缩上下文2.png)  

## 3. Global Settings  
Manage global parameters here.  
![Global Settings 1](img/全局配置1.png)  
![Global Settings 2](img/全局配置2.png)  

## 4. Resource Library  
### System Prompts  
(1) **Create Resource**  
Create a new System Prompt resource.  
![Create Prompt](img/系统提示词1.png)  
(2) **Mount Resource**  
Mount the resource to the System Prompt slot.  
![Mount Prompt](img/系统提示词2.png)  
(3) **Use Case**  
Ideal for complex logic that needs to be reused across sessions.  
![Prompt Use Case](img/系统提示词3.png)  

### Message Templates  
(1) **Create Template**  
Create a new Message Template resource.  
![Create Template](img/消息模板1.png)  
(2) **Mount Template**  
Mount the template in the chat interface.  
![Mount Template](img/消息模板2.png)  
(3) **Principle & Function**  
I. **Model Attention Distribution**  
![Attention](img/注意力.png)  
LLMs typically focus on the beginning and end of the context, often ignoring the middle. The system prompt (beginning) is more likely to be "forgotten" than the latest messages.  
II. **Template Principle**  
Placing critical settings in the latest message is effective but causes token bloat if repeated in history.  
MamboChat solves this: setting "Participation Length" to 1 ensures the template is only sent in the *current* turn and removed in the next.  
![Template Logic](img/消息模板原理.png)  
This makes templates a highly efficient, dynamic system prompt.  
(4) **Flexible Usage**  
Adjust templates on the fly using the input bar.  
![Flexible Template](img/消息模板3.png)  
Example: Mount a "Coding Style" template only when generating code.  
![Template Example](img/消息模板4.png)  

### Knowledge Base  
(1) **Create & Upload**  
Configure the vector model (modify `SUP_DIM` in [kb_service.py](../backend/services/kb_service.py) for higher dimensions if needed).  
![Vector Config](img/向量模型配置.png)  
Enter dimensions based on your API model.  
![Vector Config 2](img/向量模型配置2.png)  
Create a Knowledge Base and upload a document.  
![Create KB](img/知识库1.png)  
(2) **Embedding**  
Configure chunking strategy and start the embedding task.  
![Embedding](img/知识库2.png)  
(3) **Verify Retrieval**  
Test the retrieval (uses BM25 + Vector Search + RRF).  
![Test Retrieval](img/知识库3.png)  
(4) **AI Auto-Retrieval**  
Let the AI handle it. Mount the Knowledge Base to your current chat.  
![Mount KB](img/知识库4.png)  
Ask a question, and the AI will automatically retrieve relevant info.  
![KB Result](img/知识库5.png)  

## 5. MCP Configuration  
Configure remote or local MCP servers in settings.  
![MCP Config](img/MCP1.png)  
> **Note**: When using Docker, be mindful of network and volume isolation.  
Enable it in the chat interface to use.  
![MCP Enable](img/MCP2.png)
