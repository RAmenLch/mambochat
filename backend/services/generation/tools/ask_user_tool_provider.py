# backend/services/generation/tools/ask_user_tool_provider.py

import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator, cast, Annotated, NotRequired, Literal

from langchain_core.tools import BaseTool, tool
from langchain.tools import InjectedToolCallId
from langgraph.types import Command, interrupt
from langchain_core.messages import ToolMessage
from pydantic import Field
from typing_extensions import TypedDict

from backend.services.generation.tools.base_tool_provider import BaseToolProvider
from backend.services.generation.core.instructions import (
    BaseInstruction,
    CreateSubMessage, UpdateSubMessageContent,
    UpdateSubMessageStatus,
)
from backend.schemas import enums as schemas_enums
from backend.models.base_model import generate_uuid
from backend.schemas.message import McpToolContent

logger = logging.getLogger(__name__)


class Choice(TypedDict):
    """A single choice option for a multiple choice question."""
    value: Annotated[str, Field(description="The display label for this choice.")]


class Question(TypedDict):
    """A question to ask the user."""
    question: Annotated[str, Field(description="The question text to display.")]
    type: Annotated[
        Literal["text", "multiple_choice"],
        Field(
            description=(
                "Question type. 'text' for free-form input, 'multiple_choice' for "
                "predefined options."
            )
        ),
    ]
    choices: NotRequired[
        Annotated[
            list[Choice],
            Field(
                description=(
                    "Options for multiple_choice questions. Each choice must be an object "
                    'with a "value" field. An "Other" free-form option is always appended automatically.'
                )
            ),
        ]
    ]
    required: NotRequired[
        Annotated[
            bool,
            Field(description="Whether the user must answer. Defaults to true if omitted."),
        ]
    ]


ASK_USER_TOOL_DESCRIPTION = """Ask the user one or more questions when you need clarification or input before proceeding.

Each question can be either:
- "text": Free-form text response from the user
- "multiple_choice": User selects from predefined options (an "Other" option is always available)

For multiple choice questions, provide a "choices" list where each choice is an object with a "value" field, e.g. [{"value": "Option A"}, {"value": "Option B"}].

By default all questions are required. Set "required" to false for optional questions that the user can skip.

Use this tool when:
- You need clarification on ambiguous requirements
- You want the user to choose between multiple valid approaches
- You need specific information only the user can provide
- You want to confirm a plan before executing it

Do NOT use this tool for:
- Simple yes/no confirmations (just proceed with your best judgment)
- Questions you can answer yourself from context
- Trivial decisions that don't meaningfully affect the outcome"""

ASK_USER_SYSTEM_PROMPT = """## `ask_user`

You have access to the `ask_user` tool to ask the user questions when you need clarification or input.
Use this tool sparingly - only when you genuinely need information from the user that you cannot determine from context.

When using `ask_user`:
- Be concise and specific with your questions
- Use multiple choice when there are clear options to choose from
- Use text input when you need free-form responses
- Group related questions into a single ask_user call rather than making multiple calls
- Never ask questions you can answer yourself from the available context"""


def _validate_questions(questions: list[Question]) -> None:
    """验证 ask_user 问题结构"""
    if not questions:
        raise ValueError("ask_user requires at least one question")

    for q in questions:
        question_text = q.get("question") if isinstance(q, dict) else None
        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError("ask_user questions must have non-empty 'question' text")

        question_type = q.get("type") if isinstance(q, dict) else None
        if question_type not in {"text", "multiple_choice"}:
            raise ValueError(f"unsupported ask_user question type: {question_type!r}")

        if question_type == "multiple_choice" and not q.get("choices"):
            raise ValueError(
                f"multiple_choice question {question_text!r} requires a non-empty 'choices' list"
            )

        if question_type == "text" and q.get("choices"):
            raise ValueError(f"text question {question_text!r} must not define 'choices'")


def _parse_answers(
    response: object,
    questions: list,
    tool_call_id: str,
) -> Command[Any]:
    """解析 interrupt 返回值为 Command + ToolMessage"""
    status = "answered"
    answers: list[str] = []

    if not isinstance(response, dict):
        answers = ["(error: invalid ask_user response payload)" for _ in questions]
        status = "error"
    else:
        response_dict = cast("dict[str, Any]", response)
        response_status = response_dict.get("status")
        if isinstance(response_status, str):
            status = response_status

        if "answers" not in response_dict:
            if status == "answered":
                answers = ["(error: missing ask_user answers payload)" for _ in questions]
                status = "error"
        else:
            raw_answers = response_dict["answers"]
            if isinstance(raw_answers, list):
                answers = [str(a) for a in raw_answers]
            else:
                answers = ["(error: invalid ask_user answers payload)" for _ in questions]
                status = "error"

        if status == "cancelled":
            answers = ["(cancelled)" for _ in questions]
        elif status == "answered":
            if len(answers) != len(questions):
                logger.warning(
                    "ask_user answer count mismatch: expected %d, got %d",
                    len(questions), len(answers),
                )
        elif status not in ("answered", "cancelled"):
            answers = [f"(error: invalid ask_user response status {status!r})" for _ in questions]
            status = "error"

    formatted_answers = []
    for i, q in enumerate(questions):
        answer = answers[i] if i < len(answers) else "(no answer)"
        formatted_answers.append(f"Q: {q['question']}\nA: {answer}")
    result_text = "\n\n".join(formatted_answers)
    return Command(
        update={
            "messages": [ToolMessage(result_text, tool_call_id=tool_call_id)],
        }
    )


class AskUserToolProvider(BaseToolProvider):
    """
    AskUser 工具提供者。
    提供 ask_user 工具，允许 AI 在执行过程中向用户提问并等待回答。
    """

    def __init__(self, enable_ask_user: bool):
        self.enable_ask_user = enable_ask_user
        self._tool_name = "ask_user"
        self._tool_sub_msg_map: Dict[str, str] = {}
        self._tool_info_cache: Dict[str, McpToolContent] = {}

    async def get_tools(self) -> List[BaseTool]:
        if not self.enable_ask_user:
            return []

        @tool(self._tool_name, description=ASK_USER_TOOL_DESCRIPTION)
        def ask_user(
            questions: list[Question],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command[Any]:
            """Ask the user one or more questions."""
            _validate_questions(questions)
            ask_request = {
                "type": "ask_user",
                "questions": questions,
                "tool_call_id": tool_call_id,
            }
            import time
            # time.sleep(2)
            response = interrupt(ask_request)
            print(response)
            return _parse_answers(response, questions, tool_call_id)

        return [ask_user]

    def get_system_prompt_injection(self) -> Optional[str]:
        if not self.enable_ask_user:
            return None
        return ASK_USER_SYSTEM_PROMPT

    def matches_tool_name(self, tool_name: str) -> bool:
        return tool_name == self._tool_name

    async def create_call_instruction(
            self,
            tool_call_id: str,
            name: str,
            arguments: Dict[str, Any],
            tool_def: Optional[BaseTool] = None
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        创建 McpTool 类型的子消息，展示 ask_user 工具调用。
        如果该 tool_call_id 已通过 restore_state 恢复（HITL 中断恢复场景），
        则跳过重复创建，避免覆盖已有的子消息映射。
        """
        if tool_call_id in self._tool_sub_msg_map:
            return

        input_schema = tool_def.args if tool_def else None

        content_obj = McpToolContent(
            tool_call_id=tool_call_id,
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, dict) else str(arguments or ""),
            input_schema=input_schema,
        )

        self._tool_info_cache[tool_call_id] = content_obj
        sub_id = generate_uuid()
        self._tool_sub_msg_map[tool_call_id] = sub_id

        yield CreateSubMessage(
            sub_message_id=sub_id,
            type=schemas_enums.SubMessageType.MCP_TOOL.value,
            sortOrder=2,
            status=schemas_enums.MessageStatus.GENERATING,
            initial_content=content_obj.to_json_string(),
            config={"is_minimal": True}
        )

    async def create_result_instruction(
            self,
            tool_call_id: str,
            result_text: str,
            is_error: bool
    ) -> AsyncGenerator[BaseInstruction, None]:
        """
        更新 McpTool 子消息的执行结果和状态。
        """
        sub_id = self._tool_sub_msg_map.get(tool_call_id)
        cached_content = self._tool_info_cache.get(tool_call_id)

        if sub_id and cached_content:
            cached_content.result = result_text
            cached_content.is_error = is_error

            yield UpdateSubMessageContent(
                sub_message_id=sub_id,
                content=cached_content.to_json_string()
            )
            yield UpdateSubMessageStatus(
                sub_message_id=sub_id,
                status=schemas_enums.MessageStatus.COMPLETED
            )

    def restore_state(self, tool_call_id: str, sub_message_id: str, tool_content: Any) -> None:
        self._tool_sub_msg_map[tool_call_id] = sub_message_id
        if isinstance(tool_content, McpToolContent):
            self._tool_info_cache[tool_call_id] = tool_content
