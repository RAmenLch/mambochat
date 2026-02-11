## 1. AI Model & Provider Configuration  
### Configuring Providers and Models  
(1) **Enter Settings**  
Click the configuration button to enter the system settings page.  
![Enter Settings](img_en/Enter_Settings.png)  
(2) **Add Provider**  
Click the "Add Provider" button.  
![Add Provider](img_en/Add_Provider.png)  
(3) **Configure Provider**  
Fill in the provider's configuration details.  
![Configure Provider](img_en/Configure_Provider.png)  
(4) **Model Configuration (Optional)**  
![Model Config](img_en/Model_Config.png)
> **Note**: OpenRouter's API usually returns detailed model info, so extra config might not be needed. For other platforms, this step is recommended to set parameters or enable multimodal features like image input (MamboChat v1.1.1 currently supports image input only).  

## 2. Conversations  
(1) **New Chat**  
Right-click in the chat list and select "New Chat".  
![New_Chat](img_en/New_Chat.png)  
(2) **Chat Settings**  
Click the chat settings button to set System Prompts and other features.  
![Chat Settings](img_en/Chat_Settings.png)  
(3) **Chat Partitions**  
Use Chat Partitions to organize your chats.  
![Chat Partitions](img_en/Chat_Partitions.png)  
(4) **File Upload & Multimodal Output**  
Supports text file uploads and multimodal content generation.(Text File and Image File)  
![File Upload](img/文件写入和图片输出.png)  
(5) **Image Upload & Parsing**  
**Critical**: You must configure `image` in the input modality settings, or image data will not be sent to the API.  
![Image Modality Config](img_en/Image_Modality_Config.png)  
Once configured, you can send images to the AI.  
![Send Image](img_en/Send_Image.png)  
(6) **Context Compression**  
Edit the prompt used for context compression in the global settings.  
![Compression Settings](img_en/Compression_Settings.png)  
When a conversation gets long:  
![Long Context](img_en/Long_Context.png)  
Use context compression to seamlessly optimize costs and maintain focus. Click "Compress History" to asynchronously generate a summary. After clicking the "Enable" button, the summary will replace this message and the history above it and be sent to the llm-api. 
![Compressed Context](img_en/Compressed_Context.png)  

## 3. Global Settings  
Manage global parameters here.  
![Global Settings 1](img_en/Global_Settings_1.png)  
![Global Settings 2](img_en/Global_Settings_2.png)  

## 4. Resource Library  
### System Prompts  
(1) **Create Resource**  
Create a new System Prompt resource.  
![Create Prompt](img_en/Create_Prompt.png)  
(2) **Mount Resource**  
Mount the resource to the System Prompt slot.  
![Mount Prompt](img/系统提示词2.png)  
(3) **Use Case**  
Ideal for complex logic that needs to be reused across sessions.  
![Prompt Use Case](img_en/Prompt_Use_Case.png)  

### Message Templates  
(1) **Create Template**  
Create a new Message Template resource.  
![Create Template](img_en/Create_Template.png)  
(2) **Mount Template**  
Mount the template in the chat interface.  
![Mount Template](img_en/Mount_Template.png)  
(3) **Principle & Function**  
I. **Model Attention Distribution**  
![Attention](img/注意力.png)  
LLMs typically focus on the beginning and end of the context, often ignoring the middle. The system prompt (beginning) is more likely to be "forgotten" than the latest messages.  
II. **Template Principle**  
Placing critical settings in the latest message is effective but causes token bloat if repeated in history.  
MamboChat solves this: setting "Participation Length" to 1 ensures the template is only sent in the *current* turn and removed in the next.  
![Template Logic](img_en/Template_Logic.png)  
This makes templates a highly efficient, dynamic system prompt.  
(4) **Flexible Usage**  
Adjust templates on the fly using the input bar.  
![Flexible Template](img/消息模板3.png)  
Example: Mount a "Coding Style" template only when generating code.  
![Template Example](img/消息模板4.png)  

### Knowledge Base  
(1) **Create & Upload**  
Configure the vector model (modify `SUP_DIM` in [kb_service.py](../backend/services/kb_service.py) for higher dimensions if needed).  
![Vector Config](img_en/Vector_Config.png)  
Enter dimensions based on your API model.  
![Vector Config 2](img/向量模型配置2.png)  
Create a Knowledge Base and upload a document.  
![Create KB](img_en/Create_KB.png)  
(2) **Embedding**  
Configure chunking strategy and start the embedding task.  
![Embedding](img/知识库2.png)  
(3) **Verify Retrieval**  
Test the retrieval (uses BM25 + Vector Search + RRF).  
![Test Retrieval](img_en/Test_Retrieval.png)  
(4) **AI Auto-Retrieval**  
Let the AI handle it. Mount the Knowledge Base to your current chat.  
![Mount KB](img_en/Mount_KB.png)  
Ask a question, and the AI will automatically retrieve relevant info.  
![KB Result](img/知识库5.png)  

## 5. MCP Configuration  
Configure remote or local MCP servers in settings.  
![MCP Config](img/MCP1.png)  
> **Note**: When using Docker, be mindful of network and volume isolation.  

Enable it in the chat interface to use.  
![MCP Enable](img/MCP2.png)
