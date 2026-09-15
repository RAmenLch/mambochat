"""尾部工具调用中间件 (Tail Tool Middleware)。

在 ReAct 循环正常收尾(``after_agent``)之后,以**与主 agent 完全一致的上下文
与参数、同一模型**独立发起一次模型调用:在其尾部追加一条合成 user 消息,要求
模型调用通用工具 ``tail_tool`` 完成若干"尾部任务";收集这些调用(可选直接执行),
后本轮结束,不跳回 tools、不回路。

设计要点:

- **触发点在 ``after_agent``**:它是图的 exit node,在整个 ReAct 循环结束
  (模型给出无 tool_calls 的最终回答)之后只运行一次。``awrap_model_call``
  是循环内、每次模型调用都会经过的包装层,不能在那里触发。
- **复用上下文/参数以命中缓存**:在 ``awrap_model_call`` 里**仅记录**生效后的
  ``ModelRequest`` 与最终 ``ModelResponse``(**不持有 handler 闭包**——跨节点调用
  不安全);在 ``aafter_agent`` 里用同一 ``request`` 的 system/tools/model_settings
  **直接**再调一次模型,仅在尾部追加(最终回答 + 触发语)。因此请求前缀逐字节相同
  → 缓存命中。
- **不污染正文**:尾部这次调用带 ``lc_source`` 标记,Worker 消费 ``messages`` 流时会
  过滤掉,不会被当作正文渲染(与 summarization 同机制)。
- **尾部消息不写入 state**:触发语与尾部调用只用于这次 side call,绝不写回
  ``state["messages"]``,因此不进入下一轮上下文。
- **通用工具 ``tail_tool(task, arguments)`` 屏蔽具体任务描述**:工具表里只常驻
  这一个通用工具(主调用与尾部调用一致 → 工具区不破坏缓存),具体尾部任务的结构
  由触发语在尾部内联说明(相当于 mcp.py 的 ``mcp_get_tool_description``,但落在
  尾部、零主上下文成本)。
- **尾部任务来源**:
  - ``tasks``:纯说明型任务(如 suggest,无执行器),``result`` 即模型产出的 arguments;
  - ``tools``:可选的真实 ``StructuredTool`` 列表——既提供结构(``.args``/描述),
    也可由中间件在尾部直接执行(``execute_tools=True`` 时)。
- **结果回传**:经自定义状态频道 ``_tail_tool_event`` 输出,由下游消费。
- **未调用策略**:模型未调用 ``tail_tool`` 时,按 ``fail_mode`` 静默失败或产出失败事件。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Annotated, Any, Awaitable, Callable, Literal, Optional

from typing_extensions import NotRequired, TypedDict

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import OmitFromInput
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from backend import schemas
from backend.crud import message_crud
from backend.models.base_model import generate_uuid
from backend.schemas import enums as schemas_enums
from backend.schemas.message import McpToolContent, SubMessageConfig
from backend.services.stream_manager_service import stream_manager

logger = logging.getLogger(__name__)


_TAIL_TOOL_DESCRIPTION = (
    "尾部任务产出工具。**仅**在系统明确要求时使用:在回答结束之后,按系统给出的"
    "任务清单逐项产出。每个任务调用一次,``task`` 填任务名,``arguments`` 填符合"
    "该任务结构要求的参数对象。不要在正文作答阶段调用本工具。"
)

#: 正文阶段误调用 ``tail_tool`` 时返回的引导语(提示模型不要在此阶段调用)。
_BODY_CALL_GUIDANCE = (
    "该工具仅在收尾阶段由系统要求时调用;正文作答阶段请勿调用,请直接正常作答。"
)

#: 通用尾部工具名(常量;常驻工具表,主/尾两次调用一致)。
TAIL_TOOL_NAME = "tail_tool"

#: 尾部模型调用在 stream metadata 上的 ``lc_source`` 标记。Worker 消费 ``messages``
#: 流时据此过滤,避免尾部输出被当作正文渲染(与 summarization 同机制)。
TAIL_LC_SOURCE = "tail_tool"

_HEADER = "[AUTO_USER]:进入尾部任务阶段,与正文工作无关,请完成以下尾部任务:"

_FOOTER = (
    "说明: \n"
    "1. 本阶段为尾部任务,在生成后自动执行,与正文无关,请勿在本阶段处理正文中的工作,"
    "只需完成 上述 {count} 个任务\n"
    "2. 请简洁快速的完成任务,避免复杂思考\n"
    "3. 请尽量并行执行工具"
)


class TailToolInput(BaseModel):
    """Args schema for the generic ``tail_tool``."""

    task: str = Field(description="尾部任务名(取自系统给出的任务清单)")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="该任务的参数对象,结构见任务清单中给出的 arguments 说明/JSON Schema",
    )


@dataclass
class TailTaskSpec:
    """纯说明型尾部任务(无执行器,如 suggest)。

    Args:
        name: 任务名(``tail_tool`` 的 ``task`` 取值)。
        instruction: 自然语言说明。
    """

    name: str
    instruction: str = ""


@dataclass
class TailToolConfig:
    """尾部工具中间件的配置。

    Args:
        enabled: 是否启用。
        tasks: 尾部任务的"使用说明"清单(名称 + 具体指令)。用于表达工具描述**覆盖不到**
            的具体使用要求(如"给出 3~5 条""按用户要求的数量")。
        tools: 可选的真实工具列表(``StructuredTool``/``BaseTool``),提供参数结构
            (``.args``)并在尾部执行。与 ``tasks`` **按名称合并**:同名时 task 提供
            指令、tool 提供结构 + 执行器。
        fail_mode: 模型未调用时的行为——``"silent"`` 静默失败(不产出事件);
            ``"message"`` 产出带失败信息的 ``_tail_tool_event``。
        fail_message: ``fail_mode="message"`` 时使用的失败文案。
        trigger_prompt: 完全自定义的触发语(``None`` 时按 ``tasks``/``tools`` 拼装)。
        execute_tools: 是否由中间件在尾部直接执行 ``tools`` 中的真实工具。
        max_rounds: 尾部工具执行的**最大轮数**(阈值)。``1``=单轮(默认,与旧行为一致);
            ``>1`` 时循环"调用模型 → 执行工具 → 回灌结果 → 再调用",直到模型不再调用
            或达到该轮数。``suggest`` 启用时由 ``merge_suggest_into_tail_config`` 强制为 1。
    """

    enabled: bool = True
    tasks: list[TailTaskSpec] = field(default_factory=list)
    tools: list[BaseTool] = field(default_factory=list)
    fail_mode: Literal["silent", "message"] = "silent"
    fail_message: str = ""
    trigger_prompt: Optional[str] = None
    execute_tools: bool = True
    max_rounds: int = 1


def _tail_event_last_wins(a: Optional[dict], b: Optional[dict]) -> Optional[dict]:
    """``_tail_tool_event`` 频道的 reducer(整体替换,last-wins)。"""
    return b


class TailToolState(TypedDict):
    """尾部工具中间件的状态 schema。"""

    _tail_tool_event: Annotated[NotRequired[dict], OmitFromInput, _tail_event_last_wins]


def build_tail_tool_middleware(
    config: Optional[dict],
    *,
    session_factory: Optional[Callable[[], Any]] = None,
    message_id: Optional[str] = None,
) -> Optional["TailToolMiddleware"]:
    """由 ``AgentConfig.tail_tool_config`` 字典构造中间件。

    ``config`` 为空或既无 ``tasks`` 也无 ``tools`` 时返回 ``None``(Builder 据此跳过挂载)。结构::

        {
            "enabled": True,
            "tasks": [{"name": "suggest", "instruction": "..."}],
            "tools": [<StructuredTool>, ...],   # 可选,进程内对象
            "fail_mode": "silent" | "message",
            "fail_message": "",
            "trigger_prompt": None,
            "execute_tools": True,
            "max_rounds": 1,
        }
    """
    if not config:
        return None
    tasks = [
        TailTaskSpec(
            name=t["name"],
            instruction=t.get("instruction", ""),
        )
        for t in (config.get("tasks") or [])
    ]
    tools = list(config.get("tools") or [])
    if not tasks and not tools:
        return None
    return TailToolMiddleware(
        TailToolConfig(
            enabled=config.get("enabled", True),
            tasks=tasks,
            tools=tools,
            fail_mode=config.get("fail_mode", "silent"),
            fail_message=config.get("fail_message", ""),
            trigger_prompt=config.get("trigger_prompt"),
            execute_tools=config.get("execute_tools", True),
            max_rounds=config.get("max_rounds", 1),
        ),
        session_factory=session_factory,
        message_id=message_id,
    )


class TailToolMiddleware(AgentMiddleware):
    """见模块文档。"""

    state_schema = TailToolState

    def __init__(
        self,
        config: TailToolConfig,
        *,
        session_factory: Optional[Callable[[], Any]] = None,
        message_id: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._tool_name = TAIL_TOOL_NAME
        self._tools_by_name: dict[str, BaseTool] = {t.name: t for t in config.tools}
        # 尾部真实工具(直接调用)子消息落库所需的会话工厂与父消息 ID(可选)。
        self._session_factory = session_factory
        self._message_id = message_id
        # 每次运行从 request.tools 解析出的真实工具(供直调执行 + 子消息 schema)。
        self._real_tools_by_name: dict[str, BaseTool] = {}

        # 捕获自最近一次 awrap_model_call(仅记录 request/response 数据,不持有 handler 闭包)
        self._last_request: Any = None
        self._last_response: Any = None

        self._tail_tool: Optional[StructuredTool] = None
        if config.enabled:
            self._tail_tool = self._build_tool()
            self.tools = [self._tail_tool]

    # ------------------------------------------------------------------
    # 通用工具
    # ------------------------------------------------------------------

    def _build_tool(self) -> StructuredTool:
        return StructuredTool.from_function(
            name=self._tool_name,
            description=_TAIL_TOOL_DESCRIPTION,
            func=self._noop,
            coroutine=self._anoop,
            args_schema=TailToolInput,
            infer_schema=False,
        )

    @staticmethod
    def _noop(task: str, arguments: Optional[dict] = None) -> str:  # noqa: ARG004
        # 工具函数只在"正文误调用"时被执行(尾部 side-call 不走 tools 节点)
        return _BODY_CALL_GUIDANCE

    @staticmethod
    async def _anoop(task: str, arguments: Optional[dict] = None) -> str:  # noqa: ARG004
        return _BODY_CALL_GUIDANCE

    # ------------------------------------------------------------------
    # 捕获(awrap_model_call):仅记录,绝不触发
    # ------------------------------------------------------------------

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        # 仅记录本次请求/响应数据;不捕获 handler 闭包(跨节点调用不安全)
        self._last_request = request
        response = await handler(request)
        self._last_response = response
        return response

    # ------------------------------------------------------------------
    # 触发(after_agent):独立进行一次调用
    # ------------------------------------------------------------------

    async def aafter_agent(self, state: Any, runtime: Any) -> Optional[dict[str, Any]]:
        if not self._config.enabled:
            return None

        request = self._last_request
        response = self._last_response
        # 用后即清,避免跨运行残留
        self._last_request = None
        self._last_response = None

        if request is None:
            return None

        # 从 request.tools 解析真实工具(与主调用同一份工具表)。
        self._real_tools_by_name = self._real_tools(request)

        tail_messages = self._build_tail_messages(request, response)

        max_rounds = max(1, int(self._config.max_rounds or 1))
        all_calls: list[dict[str, Any]] = []
        for _ in range(max_rounds):
            try:
                ai = await self._invoke_tail_model(request, tail_messages)
            except Exception as exc:  # noqa: BLE001 - 尾部失败不应影响主回答
                logger.warning("尾部工具调用失败: %s", exc, exc_info=True)
                if all_calls:
                    break
                return self._failure_event(str(exc))

            calls = self._collect_calls(ai)
            executed = await self._execute_calls(calls) if calls else False
            all_calls.extend(calls)
            # 落库本轮尾部产出(思考 / 正文 / 工具调用),统一标 is_tail_tool → 由尾部面板渲染。
            await self._persist_tail_round(ai, calls)
            if not executed:
                # 无调用或本轮无任何可执行器:再循环也无新信息,停止。
                break
            # 回灌本轮调用与结果,作为下一轮的前缀扩展(仅追加 → 前缀不变,仍命中缓存)。
            tail_messages.append(ai)
            tail_messages.extend(self._build_tool_messages(calls))

        if not all_calls:
            return self._failure_event(None)
        return {"_tail_tool_event": {"status": "ok", "calls": all_calls, "error": None}}

    @staticmethod
    def _real_tools(request: Any) -> dict[str, BaseTool]:
        """从 ``request.tools`` 中解析真实工具(名称 → 工具对象)。"""
        result: dict[str, BaseTool] = {}
        for tool in getattr(request, "tools", None) or []:
            name = getattr(tool, "name", None)
            if name:
                result[name] = tool
        return result

    async def _invoke_tail_model(self, request: Any, tail_messages: list[Any]) -> Any:
        """直接调用模型(不经图内 handler)。

        用 ``lc_source`` 标记本次调用,Worker 消费 ``messages`` 流时会过滤掉,避免
        尾部输出被当作正文渲染(与 summarization 同机制)。``system_message`` /
        ``tools`` / ``model_settings`` 均复用主调用的 ``request``,保证请求前缀逐字节
        一致(命中缓存)。
        """
        tools = list(getattr(request, "tools", None) or [])
        model_settings = getattr(request, "model_settings", None) or {}
        if tools:
            bound = request.model.bind_tools(
                tools,
                tool_choice=getattr(request, "tool_choice", None),
                **model_settings,
            )
        else:
            bound = request.model.bind(**model_settings)
        messages = list(tail_messages)
        if request.system_message is not None:
            messages = [request.system_message, *messages]
        return await bound.ainvoke(
            messages, config={"metadata": {"lc_source": TAIL_LC_SOURCE}}
        )

    # ------------------------------------------------------------------
    # 组装触发语
    # ------------------------------------------------------------------

    def _build_tail_messages(self, request: Any, response: Any) -> list[Any]:
        """主前缀(``request.messages``)+ 最终回答 + 触发语。

        直接复用 ``request.messages``(而非 ``state["messages"]``),以兼容上下文
        编辑/摘要类中间件对消息列表的裁剪,保证前缀与主调用一致。
        """
        messages = list(request.messages)
        if response is not None and getattr(response, "result", None):
            answer = response.result[-1]
            if isinstance(answer, AIMessage):
                messages.append(answer)
        messages.append(HumanMessage(content=self._build_trigger()))
        return messages

    def _build_trigger(self) -> str:
        if self._config.trigger_prompt:
            return self._config.trigger_prompt
        tasks = list(self._iter_tail_tasks())
        lines = [_HEADER]
        for index, (name, instruction, args_schema) in enumerate(tasks, start=1):
            lines.append(self._format_task(index, name, instruction, args_schema))
        lines.append(_FOOTER.format(count=len(tasks)))
        return "\n".join(lines)

    def _iter_tail_tasks(self):
        """按名称合并 ``tasks`` 与 ``tools``:同名时 task 提供指令、tool 提供结构。

        顺序:先按 ``tasks`` 顺序,再追加未出现在 tasks 中的 ``tools``。
        任务名仅作**标签**,不要求等于工具名——具体调用哪个工具由模型按指令/工具表自行决定。
        """
        seen: set[str] = set()
        for spec in self._config.tasks:
            seen.add(spec.name)
            tool = self._tools_by_name.get(spec.name)
            args_schema = self._tool_args_schema(tool) if tool is not None else None
            instruction = spec.instruction or (tool.description if tool is not None else "")
            yield spec.name, instruction, args_schema
        for tool in self._config.tools:
            if tool.name in seen:
                continue
            yield tool.name, tool.description or "", self._tool_args_schema(tool)

    def _format_task(
        self,
        index: int,
        name: str,
        instruction: str,
        args_schema: Optional[dict[str, Any]],
    ) -> str:
        description = instruction or ""
        if name in self._tools_by_name:
            # 该任务绑定了尾部可执行工具(config.tools),模型需经通用工具 tail_tool 调用。
            args_json = (
                json.dumps(args_schema, ensure_ascii=False, sort_keys=True)
                if args_schema
                else "{}"
            )
            tail_tool = (
                "<tail_tool><description>该工具请使用tail_tool工具调用</description>"
                f"<arguments>{args_json}</arguments></tail_tool>"
            )
        else:
            # 未绑定工具:直接调用当前工具表中的同名/合适工具即可,无需 tail_tool。
            tail_tool = "<tail_tool><description>无需调用tail_tool工具</description></tail_tool>"
        return "\n".join(
            [
                f"<task{index}>",
                f"<name>{name}</name>",
                f"<description>{description}</description>",
                tail_tool,
                f"</task{index}>",
            ]
        )

    @staticmethod
    def _tool_args_schema(tool: BaseTool) -> Optional[dict[str, Any]]:
        try:
            args = tool.args
        except Exception:  # noqa: BLE001
            return None
        return args or None

    # ------------------------------------------------------------------
    # 收集与执行
    # ------------------------------------------------------------------

    def _collect_calls(self, ai: Any) -> list[dict[str, Any]]:
        """收集本轮**全部**工具调用。

        - ``tail_tool`` 调用:按 ``task`` / ``arguments`` 展开(``via="tail_tool"``);
        - 其它调用:视为对真实工具的直接调用(``via="direct"``)。
        """
        calls: list[dict[str, Any]] = []
        if ai is None:
            return calls
        for tool_call in getattr(ai, "tool_calls", None) or []:
            name = tool_call.get("name")
            if not name:
                continue
            args = tool_call.get("args") or {}
            if name == self._tool_name:
                calls.append(
                    {
                        "task": str(args.get("task", "")),
                        "arguments": self._coerce_arguments(args.get("arguments")),
                        "tool_call_id": tool_call.get("id", ""),
                        "via": "tail_tool",
                    }
                )
            else:
                calls.append(
                    {
                        "task": name,
                        "arguments": args if isinstance(args, dict) else {},
                        "tool_call_id": tool_call.get("id", ""),
                        "via": "direct",
                    }
                )
        return calls

    @staticmethod
    def _coerce_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    async def _execute_calls(self, calls: list[dict[str, Any]]) -> bool:
        """在尾部直接执行可解析到执行器的调用。

        执行器解析顺序:① ``request.tools`` 中的同名真实工具(直接调用);
        ② ``config.tools`` 中注入的尾部专属工具。

        Returns:
            本轮是否至少真正执行了一个工具。``False`` 表示没有命中任何可执行器
            (如纯说明型任务或未绑定的工具),上层据此停止多轮循环。
        """
        executed_any = False
        for call in calls:
            call["status"] = "ok"
            call["output"] = None
            call["error"] = None
            tool = self._real_tools_by_name.get(call["task"]) or self._tools_by_name.get(
                call["task"]
            )
            if tool is None:
                continue
            if not self._config.execute_tools:
                call["status"] = "skipped"
                continue
            try:
                output = await tool.ainvoke(call["arguments"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("尾部工具 '%s' 执行失败: %s", call["task"], exc, exc_info=True)
                call["status"] = "error"
                call["error"] = str(exc)
                continue
            executed_any = True
            call["output"] = (
                output
                if isinstance(output, str)
                else json.dumps(output, ensure_ascii=False, default=str)
            )
        return executed_any

    # ------------------------------------------------------------------
    # 落库(真实工具直接调用的子消息)
    # ------------------------------------------------------------------

    async def _persist_tail_round(self, ai: Any, calls: list[dict[str, Any]]) -> None:
        """落库本轮尾部产出为 ``is_tail_tool`` 子消息(复用 Reasoning/Normal/McpTool/File)。

        带 ``is_tail_tool=True`` 的子消息不进正文/时间线,仅由助手消息底部的尾部折叠面板渲染,
        从而与正文**复用同一套子消息与组件**。
        """
        if self._session_factory is None or not self._message_id:
            return
        # 1) 思考(reasoning)
        ak = getattr(ai, "additional_kwargs", None) or {}
        reasoning = ak.get("reasoning_content") or ak.get("reasoning")
        if reasoning:
            try:
                await self._create_sub(
                    schemas_enums.SubMessageType.REASONING.value,
                    str(reasoning),
                    sort_order=87,
                    config=SubMessageConfig(
                        context_participation_length=0, is_tail_tool=True, is_minimal=True
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("尾部思考落库失败: %s", exc, exc_info=True)
        # 2) 正文(content)
        content = getattr(ai, "content", None)
        if isinstance(content, str) and content.strip():
            try:
                await self._create_sub(
                    schemas_enums.SubMessageType.NORMAL.value,
                    content,
                    sort_order=88,
                    config=SubMessageConfig(context_participation_length=0, is_tail_tool=True),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("尾部正文落库失败: %s", exc, exc_info=True)
        # 3) 工具调用(直调工具表工具 / 经通用工具 tail_tool 调用)
        await self._persist_tool_calls(calls)

    async def _create_sub(
        self, sub_type: str, content: str, *, sort_order: int, config: SubMessageConfig
    ) -> None:
        sub_id = generate_uuid()
        async with self._session_factory() as db:
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=self._message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content=content,
                    sortOrder=sort_order,
                    type=sub_type,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    config=config,
                ),
                sub_message_id=sub_id,
            )
            payload = schemas.message.SubMessage.model_validate(db_sub).model_dump(mode="json")
        await stream_manager.publish(self._message_id, {"type": "create", "sub_message": payload})

    async def _persist_tool_calls(self, calls: list[dict[str, Any]]) -> None:
        """把尾部工具调用落库为 ``is_tail_tool`` 子消息。

        - ``via == "direct"``:模型直调工具表中的工具(如 show),按其真实名称落库;
        - ``via == "tail_tool"``:模型经通用工具 ``tail_tool`` 调用(如 suggest),
          落库为 ``name="tail_tool"``、``arguments={task, arguments}`` 的子消息,
          与 ``mcp_call_tool`` 的包装结构一致,前端据此拆包显示。

        带 ``is_tail_tool=True`` 的子消息不进正文/时间线(前端时间线会跳过),仅由助手
        消息底部的尾部折叠面板渲染——从而与正文复用同一套子消息组件。
        """
        if self._session_factory is None or not self._message_id:
            return
        for call in calls:
            try:
                if call.get("via") == "tail_tool":
                    await self._persist_tail_tool_call(call)
                else:
                    await self._persist_one(call)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "尾部工具 '%s' 子消息落库失败: %s", call.get("task"), exc, exc_info=True
                )

    async def _persist_tail_tool_call(self, call: dict[str, Any]) -> None:
        """把经通用工具 ``tail_tool`` 的调用落库为 ``MCP_TOOL`` 子消息(仿 ``mcp_call_tool``)。

        ``name`` 恒为 ``tail_tool``,``arguments`` 为 ``{"task": ..., "arguments": ...}``;
        前端 ``unpackMcpToolCall`` 据此拆出内层任务名与参数并标记为尾部工具。
        """
        content = McpToolContent(
            tool_call_id=call.get("tool_call_id") or "",
            name=TAIL_TOOL_NAME,
            arguments={
                "task": call.get("task") or "",
                "arguments": call.get("arguments") or {},
            },
            input_schema=self._tool_args_schema(self._tail_tool) if self._tail_tool else None,
        )
        if call.get("output") is not None:
            content.result = call["output"]
        content.is_error = call.get("status") == "error"

        sub_id = generate_uuid()
        async with self._session_factory() as db:
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=self._message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content=content.to_json_string(),
                    sortOrder=90,
                    type=schemas_enums.SubMessageType.MCP_TOOL.value,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    config=SubMessageConfig(context_participation_length=0, is_tail_tool=True),
                ),
                sub_message_id=sub_id,
            )
            payload = schemas.message.SubMessage.model_validate(db_sub).model_dump(mode="json")
        await stream_manager.publish(self._message_id, {"type": "create", "sub_message": payload})

    async def _persist_one(self, call: dict[str, Any]) -> None:
        name = call.get("task") or ""
        tool = self._real_tools_by_name.get(name)
        content = McpToolContent(
            tool_call_id=call.get("tool_call_id") or "",
            name=name,
            arguments=call.get("arguments") or {},
            input_schema=self._tool_args_schema(tool) if tool is not None else None,
        )
        if call.get("output") is not None:
            content.result = call["output"]
        content.is_error = call.get("status") == "error"

        sub_id = generate_uuid()
        async with self._session_factory() as db:
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=self._message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content=content.to_json_string(),
                    sortOrder=90,
                    type=schemas_enums.SubMessageType.MCP_TOOL.value,
                    status=schemas_enums.MessageStatus.COMPLETED,
                    config=SubMessageConfig(context_participation_length=0, is_tail_tool=True),
                ),
                sub_message_id=sub_id,
            )
            payload = schemas.message.SubMessage.model_validate(db_sub).model_dump(mode="json")
        await stream_manager.publish(self._message_id, {"type": "create", "sub_message": payload})

        # show → 额外落一条 FILE 子消息(同样带 is_tail_tool,由尾部面板渲染)。
        if name == "show" and not content.is_error:
            await self._persist_show_file(call.get("output"))

    async def _persist_show_file(self, output: Optional[str]) -> None:
        if not output:
            return
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(data, dict):
            return
        if data.get("status") == "pending":
            file_cfg = SubMessageConfig(
                context_participation_length=0,
                is_tail_tool=True,
                pending_file_path=data.get("path"),
                pending_file_timeout=data.get("timeout", 300),
                show_tool_mode=data.get("mode", "Normal"),
            )
            status = schemas_enums.MessageStatus.WAITING
            file_content = ""
        elif data.get("file_id"):
            file_cfg = SubMessageConfig(
                context_participation_length=0,
                is_tail_tool=True,
                show_tool_mode=data.get("mode", "Normal"),
            )
            status = schemas_enums.MessageStatus.COMPLETED
            file_content = data["file_id"]
        else:
            return

        sub_id = generate_uuid()
        async with self._session_factory() as db:
            db_sub = await message_crud.create_sub_message(
                db,
                message_id=self._message_id,
                sub_message_data=schemas.message.SubMessageCreate(
                    id=sub_id,
                    content=file_content,
                    sortOrder=91,
                    type=schemas_enums.SubMessageType.FILE.value,
                    status=status,
                    config=file_cfg,
                ),
                sub_message_id=sub_id,
            )
            payload = schemas.message.SubMessage.model_validate(db_sub).model_dump(mode="json")
            # File 子消息需附带 file_info,前端据此立即渲染(见 executor/handlers.py 同款处理)
            if file_content:
                from backend.services.file_service import FileService

                file_service = FileService(db)
                file_record = await file_service.get_file(file_content)
                if file_record:
                    payload["file_info"] = file_service.convert_to_schema(file_record).model_dump(
                        mode="json"
                    )
        await stream_manager.publish(self._message_id, {"type": "create", "sub_message": payload})

    @staticmethod
    def _build_tool_messages(calls: list[dict[str, Any]]) -> list[Any]:
        """为上一轮每个 ``tail_tool`` 调用构造 ``ToolMessage``,供下一轮模型查看结果。

        每条 ``tool_call`` 都必须有对应结果,否则下一轮模型调用会因消息结构非法而报错;
        无输出 / 被跳过的任务给出占位说明。
        """
        messages: list[Any] = []
        for call in calls:
            if call.get("status") == "error":
                content = f"[error] {call.get('error') or ''}"
            elif call.get("output") is not None:
                content = call["output"]
            else:
                content = "[skipped] 该任务无可用执行器(仅产出参数)"
            messages.append(
                ToolMessage(
                    content=str(content),
                    tool_call_id=call.get("tool_call_id") or "",
                )
            )
        return messages

    # ------------------------------------------------------------------
    # 失败事件
    # ------------------------------------------------------------------

    def _failure_event(self, error: Optional[str]) -> Optional[dict[str, Any]]:
        if self._config.fail_mode == "message":
            message = self._config.fail_message or error or "尾部任务未产出。"
            return {
                "_tail_tool_event": {
                    "status": "error",
                    "calls": [],
                    "error": message,
                }
            }
        return None
