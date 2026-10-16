# backend/schemas/group_chat.py

import unicodedata
import re
from datetime import datetime
from typing import Optional, List, Any, Dict

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.schemas.enums import (
    GroupMailMode, GroupStatus, GroupPauseReason, GroupTaskKind, GroupTaskState, GroupMailState,
)


# --- 别名约束 ---

MEMBER_ALIAS_MIN_LEN = 1
MEMBER_ALIAS_MAX_LEN = 64

# 群组保留成员：Master 代表「用户本人」，不是 Agent。成员给 Master 发信即为给用户发信；
# 用户本人的群发言会记为一封来自 Master 的邮件。该别名不允许被普通成员占用。
MASTER_ALIAS = "Master"
# Master 成员在成员列表中的排序权重（置顶）
MASTER_SORT_ORDER = -1

# 禁止的控制字符、换行、'@' 和英文逗号
_FORBIDDEN_ALIAS_CHARS = re.compile(r"[\x00-\x1f\x7f@,]")


def normalize_member_alias(raw: str) -> str:
    """
    对成员别名进行首尾去空白与 Unicode NFC 规范化，并校验字符合法性。
    别名即邮箱地址，规范化后区分大小写。允许中文与内部空格。
    """
    if raw is None:
        raise ValueError("member_alias_required")
    alias = unicodedata.normalize("NFC", str(raw)).strip()
    if not alias:
        raise ValueError("member_alias_empty")
    if len(alias) > MEMBER_ALIAS_MAX_LEN:
        raise ValueError("member_alias_too_long")
    if _FORBIDDEN_ALIAS_CHARS.search(alias):
        raise ValueError("member_alias_invalid_chars")
    return alias


# --- 创建 ---

class GroupMemberCreate(BaseModel):
    agentId: str = Field(..., description="选中的 Agent ID；允许同一 Agent 重复选择")
    memberAlias: str = Field(..., description="成员邮箱地址/别名")

    @field_validator("memberAlias")
    @classmethod
    def _validate_alias(cls, v: str) -> str:
        return normalize_member_alias(v)


class GroupChatCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parentId: Optional[str] = Field(None, description="群组父节点所在的父文件夹；None/root 表示根目录")
    autoRoundLimit: int = Field(50, ge=1, description="自动邮件轮次上限，正整数")
    mailMode: GroupMailMode = Field(
        GroupMailMode.AUTO, description="邮件投递模式：auto=自动投递；review=需用户逐封审核"
    )
    members: List[GroupMemberCreate] = Field(..., min_length=3, description="成员列表，N > 2")

    @model_validator(mode="after")
    def _normalize_parent(self):
        if self.parentId == "root":
            object.__setattr__(self, "parentId", None)
        return self


# --- 响应 ---

class GroupMemberResponse(BaseModel):
    chatId: str
    memberAlias: str
    agentId: Optional[str] = None
    agentName: Optional[str] = None
    name: str
    sortOrder: int
    unreadCount: int = 0
    pendingCount: int = 0
    # 是否为保留的「用户本人」成员（Master）：无 Agent、不参与生成调度
    isUser: bool = False


class GroupMailAttachment(BaseModel):
    """群组邮件附件（引用中心库文件）。"""
    fileId: str
    filename: Optional[str] = None
    mimeType: Optional[str] = None
    sizeBytes: Optional[int] = None
    url: Optional[str] = Field(None, description="由消息组装层填充的下载地址，供前端展示")


class GroupMailResponse(BaseModel):
    id: str
    groupId: str
    sourceTaskId: str
    senderChatId: str
    senderAliasSnapshot: str
    recipientSnapshot: List[Dict[str, Any]] = Field(default_factory=list)
    title: Optional[str] = None
    content: str
    attachments: List[GroupMailAttachment] = Field(default_factory=list)
    state: GroupMailState
    sequence: Optional[int] = None
    createdAt: datetime
    sentAt: Optional[datetime] = None
    # 审核模式：用户审核时间与拒绝原因
    reviewedAt: Optional[datetime] = None
    rejectReason: Optional[str] = None


class GroupMailListResponse(BaseModel):
    items: List[GroupMailResponse] = Field(default_factory=list)
    nextAfterSequence: Optional[int] = None
    hasMore: bool = False


class GroupMailReviewResponse(BaseModel):
    """审核模式的邮件审批视图：待审核 + 已决策（被拒 / 已同意待投递）。"""
    pending: List[GroupMailResponse] = Field(default_factory=list)
    decided: List[GroupMailResponse] = Field(default_factory=list)


class GroupMailRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="拒绝原因，必填")


class GroupMailDecisionResponse(BaseModel):
    groupId: str
    mailId: str
    state: GroupMailState
    pendingCount: int = 0
    finalized: bool = False
    version: int = 0


class GroupTaskResponse(BaseModel):
    id: str
    groupId: str
    memberChatId: str
    sequence: int
    kind: GroupTaskKind
    state: GroupTaskState
    requestId: Optional[str] = None
    userMessageId: Optional[str] = None
    assistantMessageId: Optional[str] = None
    attemptCount: int = 0
    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None
    createdAt: datetime
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None


class GroupTaskListResponse(BaseModel):
    items: List[GroupTaskResponse] = Field(default_factory=list)
    total: int = 0


class GroupDetailResponse(BaseModel):
    groupId: str
    name: str
    parentId: Optional[str] = None
    status: GroupStatus
    pauseReason: Optional[GroupPauseReason] = None
    autoRoundLimit: int
    autoRoundCount: int
    # 群累计实际启动过的自动邮件轮次（跨额度周期，仅用于展示）
    totalAutoRoundCount: int = 0
    version: int
    activeTaskId: Optional[str] = None
    members: List[GroupMemberResponse] = Field(default_factory=list)
    unreadCount: int = 0
    queuedCount: int = 0


class GroupCreatedResponse(GroupDetailResponse):
    """创建成功后返回群与完整子节点，避免前端文件夹缓存误判为空。"""
    pass


# --- 群输入 ---

class GroupMessageSendRequest(BaseModel):
    requestId: Optional[str] = Field(None, description="用户命令幂等键")
    content: str = Field(..., min_length=1)
    recipientNames: List[str] = Field(
        default_factory=list,
        description="收件成员别名列表；空数组表示广播给全部成员",
    )
    attachmentFileIds: List[str] = Field(
        default_factory=list,
        description="用户上传的中心库文件 ID 列表，随本轮投递给成员",
    )


class GroupTaskAccepted(BaseModel):
    kind: str = "group_task"
    groupId: str
    taskIds: List[str] = Field(default_factory=list)
    state: GroupTaskState = GroupTaskState.QUEUED


# --- 复制群组 ---

class GroupDuplicateRequest(BaseModel):
    """复制群组到指定邮件为止（粒度=该邮件所属的整轮）。"""
    upToMailId: str = Field(..., description="点中的邮件 id；复制到该邮件所属轮次结束为止")


# --- 控制请求 ---

class GroupSettingsUpdate(BaseModel):
    autoRoundLimit: Optional[int] = Field(None, ge=1)
    resetAutoRoundCount: bool = Field(False, description="显式请求才重置自动轮次计数")
    mailMode: Optional[GroupMailMode] = Field(
        None, description="切换邮件投递模式：只对之后的轮次生效"
    )


class GroupControlResponse(BaseModel):
    groupId: str
    status: GroupStatus
    version: int


# --- 工具参数 (供 generation 层使用) ---

class GroupSendMailItem(BaseModel):
    address: List[str] = Field(..., min_length=1)
    title: Optional[str] = None
    content: str


class GroupSendMailRequest(BaseModel):
    address: List[str] = Field(..., min_length=1, description="非空 MemberName 数组")
    title: Optional[str] = None
    content: str
