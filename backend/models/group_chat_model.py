# backend/models/group_chat_model.py

from sqlalchemy import (
    Column, String, TEXT, DateTime, ForeignKey, Integer, JSON, Boolean,
    UniqueConstraint, Index,
)

from backend.models.base_model import Base, generate_uuid
from backend.config.timezone_config import get_configured_now
from backend.schemas.enums import GroupStatus, GroupMailState


class GroupState(Base):
    """
    群组运行状态。每个群组父节点（Chat.itemType=folder, folderType=group）对应一行。
    """
    __tablename__ = "GroupState"

    groupId = Column(String(36), ForeignKey("Chat.id", ondelete="CASCADE"), primary_key=True)
    # 调度状态：ready / paused / deleting；等待审核等具体原因由 pauseReason 表示
    status = Column(String(20), nullable=False, default=GroupStatus.READY.value)
    pauseReason = Column(String(50), nullable=True)
    # 当前逻辑轮次，等待审核时仍保留（不代表有线程持续执行）
    activeTaskId = Column(String(36), nullable=True)
    # 自动邮件轮次上限
    autoRoundLimit = Column(Integer, nullable=False, default=50)
    # 实际启动的自动邮件逻辑轮次次数（同轮恢复不重复增加）
    autoRoundCount = Column(Integer, nullable=False, default=0)
    # 邮件投递模式：auto=轮次正常结束后自动投递；review=需用户逐封审核后才投递
    mailMode = Column(String(20), nullable=False, default="auto")
    # 群内 FIFO 队列序号分配
    nextTaskSeq = Column(Integer, nullable=False, default=0)
    # 已投递邮件的严格展示顺序分配
    nextMailSeq = Column(Integer, nullable=False, default=0)
    # 乐观并发版本 & 前端通知对账版本
    version = Column(Integer, nullable=False, default=0)

    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    updatedAt = Column(DateTime, nullable=False, default=get_configured_now, onupdate=get_configured_now)


class GroupTask(Base):
    """
    群组排队命令 + 逻辑生成轮次。首版不额外拆分 job/run 两套表。
    """
    __tablename__ = "GroupTask"

    __table_args__ = (
        UniqueConstraint("groupId", "sequence", name="uq_grouptask_group_sequence"),
        # requestId 为 NULL 时 SQLite 允许多个 NULL，故不用于幂等
        UniqueConstraint("groupId", "requestId", "memberChatId", name="uq_grouptask_idem"),
        # 等待中的邮件任务合并键；离开 queued 后清空
        UniqueConstraint("coalesceKey", name="uq_grouptask_coalesce"),
        Index("ix_grouptask_group_state", "groupId", "state"),
        Index("ix_grouptask_member", "memberChatId"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    groupId = Column(String(36), ForeignKey("Chat.id", ondelete="CASCADE"), nullable=False, index=True)
    memberChatId = Column(String(36), nullable=False)

    # 群内 FIFO 顺序
    sequence = Column(Integer, nullable=False)
    # user_message / mail_notice / regenerate / edit_regenerate
    kind = Column(String(30), nullable=False)
    # queued / running / waiting_review / ... / skipped
    state = Column(String(20), nullable=False)
    # 用户命令幂等键
    requestId = Column(String(64), nullable=True)
    # 完整输入副本、附件引用、编辑内容、目标消息等
    payload = Column(JSON, nullable=True)

    # 对接现有消息
    baseMessageId = Column(String(36), nullable=True)
    userMessageId = Column(String(36), nullable=True)
    assistantMessageId = Column(String(36), nullable=True)

    # 等待中的邮件任务合并键：groupId:memberChatId
    coalesceKey = Column(String(80), nullable=True)

    # 首次启动时冻结的收件记录 ID 列表
    snapshotReceiptIds = Column(JSON, nullable=True)
    # 区分尚未冻结（NULL）与冻结结果为空（空数组）
    snapshotTakenAt = Column(DateTime, nullable=True)
    # 本轮是否实际调用 readMails
    mailReadRequested = Column(Boolean, nullable=False, default=False)
    # 原轮次恢复次数（用于排查，非自动无限重试）
    attemptCount = Column(Integer, nullable=False, default=0)

    startedAt = Column(DateTime, nullable=True)
    finishedAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, nullable=False, default=get_configured_now)

    errorCode = Column(String(50), nullable=True)
    errorMessage = Column(TEXT, nullable=True)


class GroupMail(Base):
    """
    待发箱与已发送邮件共用实体。staged 不向收件人和群公共邮件流暴露。
    """
    __tablename__ = "GroupMail"

    __table_args__ = (
        # 同一轮次内工具调用标识唯一，用于重放幂等
        UniqueConstraint("sourceTaskId", "toolCallId", name="uq_groupmail_task_toolcall"),
        # 真正投递时分配的群内展示顺序
        UniqueConstraint("groupId", "sequence", name="uq_groupmail_group_sequence"),
        Index("ix_groupmail_group_state", "groupId", "state"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    groupId = Column(String(36), ForeignKey("Chat.id", ondelete="CASCADE"), nullable=False, index=True)
    sourceTaskId = Column(String(36), nullable=False, index=True)

    # 发送成员身份，由服务端绑定
    senderChatId = Column(String(36), nullable=False)
    senderAliasSnapshot = Column(String(64), nullable=False)
    # [{memberChatId, memberName}] 规范化去重后的完整收件列表及顺序
    recipientSnapshot = Column(JSON, nullable=False)

    title = Column(String(255), nullable=True)
    content = Column(TEXT, nullable=False)

    # 附件引用快照（与群/发件人后端无关，统一指向中心库 File.id）：
    # [{fileId, filename, mimeType, sizeBytes}]；解析失败项为 [{path, error}]
    attachments = Column(JSON, nullable=True)

    toolCallId = Column(String(100), nullable=False)
    # 本轮工具调用的稳定顺序
    toolCallOrder = Column(Integer, nullable=False, default=0)

    # staged / reviewing / deferred / sent / rejected / discarded
    state = Column(String(20), nullable=False, default=GroupMailState.STAGED.value)
    # 真正投递时分配
    sequence = Column(Integer, nullable=True)

    # 审核模式：用户审核时间与拒绝原因
    reviewedAt = Column(DateTime, nullable=True)
    rejectReason = Column(TEXT, nullable=True)

    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
    sentAt = Column(DateTime, nullable=True)


class GroupMailReceipt(Base):
    """
    每位收件成员的独立收件状态，可被轮次快照引用。
    """
    __tablename__ = "GroupMailReceipt"

    __table_args__ = (
        UniqueConstraint("mailId", "recipientChatId", name="uq_gmr_mail_recipient"),
        Index("ix_gmr_recipient_read", "recipientChatId", "readAt"),
        Index("ix_gmr_notification", "notificationTaskId"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    mailId = Column(String(36), ForeignKey("GroupMail.id", ondelete="CASCADE"), nullable=False, index=True)
    recipientChatId = Column(String(36), nullable=False)

    readAt = Column(DateTime, nullable=True)
    readByTaskId = Column(String(36), nullable=True)
    # 此收件记录已登记到哪个自动任务，避免“仍未读”造成无限通知
    notificationTaskId = Column(String(36), nullable=True)

    createdAt = Column(DateTime, nullable=False, default=get_configured_now)
