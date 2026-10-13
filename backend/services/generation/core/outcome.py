# backend/services/generation/core/outcome.py

"""
独立的生成业务结束结果。

与 MessageStatus 的区别：MessageStatus 会被"取消"与"正常完成"同样折叠为
COMPLETED，"等待审核"与"等待用户回答"同样折叠为 PENDING_REVIEW，无法据此
判断邮件是否可以投递。群组邮箱提交必须依赖本枚举做出判断。
"""

from enum import Enum


class GenerationOutcome(str, Enum):
    """一次逻辑生成轮次的业务结束结果。"""

    NORMAL_COMPLETED = "normal_completed"  # 完整执行链正常完成（含正常尾部工具），可提交邮件
    CANCELLED = "cancelled"                # 用户停止或被取消，不提交邮件
    FAILED = "failed"                      # 异常结束/异常 finish_reason，不提交邮件
    WAITING_REVIEW = "waiting_review"      # 工具审核中断，暂停群组
    WAITING_USER = "waiting_user"          # ask_user 中断，暂停群组

    @property
    def is_terminal_success(self) -> bool:
        return self is GenerationOutcome.NORMAL_COMPLETED

    @property
    def is_waiting(self) -> bool:
        return self in (GenerationOutcome.WAITING_REVIEW, GenerationOutcome.WAITING_USER)
