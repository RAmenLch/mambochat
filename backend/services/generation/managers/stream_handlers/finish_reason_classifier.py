# backend/services/generation/managers/stream_handlers/finish_reason_classifier.py

from enum import Enum
from typing import Optional, Set, Dict, Any


class FinishReasonCategory(Enum):
    """finish_reason 分类结果"""
    NORMAL = "normal"
    ABNORMAL = "abnormal"


class FinishReasonClassifier:
    """
    finish_reason 分类器。
    聚合各 LLM 提供商的 finish_reason / stop_reason 语义，统一分类为 NORMAL 或 ABNORMAL。

    已知提供商规范:
    - OpenAI:        stop, length, tool_calls, content_filter, function_call(deprecated)
    - Claude:        end_turn, max_tokens, stop_sequence, tool_use, pause_turn, refusal
    - DeepSeek:      stop, length, content_filter, tool_calls, insufficient_system_resource
    - GLM(兼容):     stop, tool_calls, length, sensitive, network_error, model_context_window_exceeded
    - OpenRouter:    tool_calls, stop, length, content_filter, error (+ native_finish_reason)
    """

    NORMAL_REASONS: Set[str] = {
        "stop", "tool_calls", "function_call",
        "end_turn", "tool_use", "stop_sequence",
    }

    ABNORMAL_REASONS: Set[str] = {
        "length", "max_tokens", "content_filter",
        "insufficient_system_resource", "sensitive",
        "network_error", "model_context_window_exceeded",
        "error", "refusal", "pause_turn",
    }

    USER_MESSAGES: Dict[str, str] = {
        "length": "生成因达到最大输出长度而被截断，内容可能不完整。",
        "max_tokens": "生成因达到最大 Token 限制而被截断，内容可能不完整。",
        "content_filter": "生成因内容安全过滤而被终止，部分内容可能被屏蔽。",
        "insufficient_system_resource": "因服务端系统资源不足，生成被终止。请稍后重试。",
        "sensitive": "生成因触发内容安全策略而被终止。",
        "network_error": "因网络错误导致生成中断。请检查网络后重试。",
        "model_context_window_exceeded": "因超出模型上下文窗口长度，生成被终止。请精简对话或缩短输入内容。",
        "error": "因服务端错误导致生成中断。请稍后重试。",
        "refusal": "模型拒绝生成该内容。",
        "pause_turn": "生成被暂停（pause_turn）。",
    }

    DEFAULT_MESSAGE_TEMPLATE = "生成异常终止（原因：{reason}）"

    @classmethod
    def classify(cls, reason: Optional[str]) -> FinishReasonCategory:
        """
        对 finish_reason 进行分类。
        已知正常值 -> NORMAL，已知异常值 -> ABNORMAL，未知值默认 -> ABNORMAL。
        """
        if not reason:
            return FinishReasonCategory.NORMAL
        reason_lower = reason.lower()
        if reason_lower in {r.lower() for r in cls.NORMAL_REASONS}:
            return FinishReasonCategory.NORMAL
        return FinishReasonCategory.ABNORMAL

    @classmethod
    def get_user_message(cls, reason: Optional[str]) -> Optional[str]:
        """
        返回面向用户的异常提示消息。
        仅在 ABNORMAL 分类下返回非 None 值。
        """
        if not reason or cls.classify(reason) == FinishReasonCategory.NORMAL:
            return None
        return cls.USER_MESSAGES.get(reason.lower(), cls.DEFAULT_MESSAGE_TEMPLATE.format(reason=reason))

    @classmethod
    def extract_from_metadata(cls, metadata: Any) -> Optional[str]:
        """
        从 AIMessage.response_metadata 中提取 finish_reason。
        兼容各提供商在 response_metadata 中的不同 key 命名:
        - OpenAI / DeepSeek / GLM / OpenRouter: "finish_reason"
        - Claude (langchain): "stop_reason"

        注意: langchain_core merge_dicts 对相同 key 的字符串值会执行 += 拼接,
        导致多个连续 chunk 的相同 finish_reason 被累积为重复串 (如 "stopstop")。
        此处通过已知 reason 的反向乘法匹配将其归一化。
        """
        if not metadata or not isinstance(metadata, dict):
            return None
        # ---- 内部辅助：归一化可能因 merge_dicts 而重复拼接的 reason ----
        def _normalize(reason_str: str) -> str:
            # 对于每个已知 reason，检查当前值是否为其 N 次精确重复
            for known in sorted(
                {*cls.NORMAL_REASONS, *cls.ABNORMAL_REASONS},
                key=len,
                reverse=True,  # 先匹配长串，避免 tool_calls 被 tool 误匹配
            ):
                known_len = len(known)
                total_len = len(reason_str)
                if total_len > known_len and total_len % known_len == 0:
                    if reason_str == known * (total_len // known_len):
                        return known
            return reason_str
        # ----------------------------------------------------------------
        # 优先查找 finish_reason (OpenAI 兼容体系)
        reason = metadata.get("finish_reason")
        if reason:
            return _normalize(str(reason))
        # 兜底查找 stop_reason (Claude 体系)
        reason = metadata.get("stop_reason")
        if reason:
            return _normalize(str(reason))
        return None
