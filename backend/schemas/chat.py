# backend/schemas/chat.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict
import json

from backend.schemas.message import Message, SubMessageCreate
from backend.schemas.enums import MoveAction, ChatMode


# --- Chat Schemas ---

class ChatBase(BaseModel):
    name: str
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = Field(None, description="模型参数，例如 {'temperature': 0.7, 'top_p': 0.9}")
    aiModelId: Optional[str] = None

    itemType: str = Field('chat', description="项目类型: 'chat' 或 'folder'")
    parentId: Optional[str] = Field(None, description="父文件夹的ID")
    sortOrder: int = Field(0, description="排序权重")

    # 资源挂载ID列表
    resource_prompt_list: Optional[List[str]] = Field(None, description="挂载的资源ID列表")

    enabled_mcp_ids: Optional[List[str]] = Field(default_factory=list, description="启用的外部 MCP 服务 ID 列表")
    chatMode: ChatMode = Field(ChatMode.NORMAL, description="聊天模式: 'normal' 或 'agent'")
    agentId: Optional[str] = Field(None, description="绑定的 Agent ID（当 chatMode 为 'agent' 时有效）")

    @field_validator("modelParameters", mode="before")
    @classmethod
    def parse_model_parameters(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

class ChatCreate(ChatBase):
    pass


class Chat(ChatBase):
    id: str
    createdAt: datetime
    lastOpenedAt: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatUpdate(BaseModel):
    """用于更新会话信息，所有字段均为可选"""
    name: Optional[str] = None
    aiModelId: Optional[str] = None
    systemPrompt: Optional[str] = None
    modelParameters: Optional[Dict] = None
    parentId: Optional[str] = None
    sortOrder: Optional[int] = None

    # 资源挂载ID列表
    resource_prompt_list: Optional[List[str]] = None
    # 启用的外部 MCP 服务 ID 列表
    enabled_mcp_ids: Optional[List[str]] = None
    chatMode: Optional[ChatMode] = None
    agentId: Optional[str] = None

# noinspection PyDataclass
class ChatWithMessages(Chat):
    messages: List[Message] = Field(default_factory=list)


class ChatReorderItem(BaseModel):
    id: str
    parentId: Optional[str]
    sortOrder: int


class ChatMoveRequest(BaseModel):
    item_ids: List[str] = Field(..., description="被移动的会话或文件夹ID列表")
    reference_id: str = Field(..., description="参考目标ID，'root'代表根目录")
    action: MoveAction = Field(..., description="移动行为: before, after, inside")


class GenerateRequest(BaseModel):
    sub_messages: List[SubMessageCreate]
    attachedSubmessageResourceIds: Optional[List[str]] = Field(None, description="本次发送时要附加的Submessage模板资源ID列表")


class UpdateMessageResponse(BaseModel):
    """
    用于 /messages/{message_id} (PUT) 端点的响应模型。
    """
    user_message: Message = Field(..., description="被更新的用户消息对象。")
    assistant_message: Optional[Message] = Field(None, description="如果触发了重新生成，则为AI回复创建的占位符消息对象。")


class PrepareGenerateResponse(BaseModel):
    """
    用于 /prepare-generate 端点的响应模型。
    """
    user_message: Message = Field(..., description="新创建的用户消息对象。")
    assistant_message: Message = Field(..., description="为AI回复创建的占位符消息对象。")


# --- Search Schemas ---

class SearchRequest(BaseModel):
    keyword: str = Field(..., description="搜索关键词或正则模式")
    root_id: Optional[str] = Field(None, description="搜索范围的根目录ID，不传则搜索全局")
    enable_regex: bool = Field(False, description="是否启用正则匹配")
    page_num: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class SearchResultItem(BaseModel):
    chat_id: str
    chat_name: str
    chat_path: str
    match_type: str = Field(..., description="匹配类型: 'content', 'title', 'system_prompt'")
    context_text: str = Field(..., description="包含关键词的高亮上下文片段")
    sub_message_id: Optional[str] = Field(None, description="如果是内容匹配，提供跳转到对应子消息的ID")
    created_at: datetime


class SearchResponse(BaseModel):
    total: int
    items: List[SearchResultItem]
