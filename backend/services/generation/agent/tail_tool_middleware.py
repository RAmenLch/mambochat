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
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

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

_HEADER = "本轮回答已结束。请调用 `{tool}` 完成以下尾部任务:"
_FOOTER = (
    "请**在同一条回复中一次性**为下列每个任务各调用一次 `{tool}`(多条 tool_calls、并行),"
    "不要分多次、不要等待返回结果。`task` 填任务名,`arguments` 填参数对象(JSON)。"
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
        args_schema: 该任务 ``arguments`` 的 JSON Schema(可选,内联进触发语)。
        example: ``arguments`` 示例(可选,内联进触发语)。
    """

    name: str
    instruction: str = ""
    args_schema: Optional[dict[str, Any]] = None
    example: str = ""


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
    """

    enabled: bool = True
    tasks: list[TailTaskSpec] = field(default_factory=list)
    tools: list[BaseTool] = field(default_factory=list)
    fail_mode: Literal["silent", "message"] = "silent"
    fail_message: str = ""
    trigger_prompt: Optional[str] = None
    execute_tools: bool = True


def _tail_event_last_wins(a: Optional[dict], b: Optional[dict]) -> Optional[dict]:
    """``_tail_tool_event`` 频道的 reducer(整体替换,last-wins)。"""
    return b


class TailToolState(TypedDict):
    """尾部工具中间件的状态 schema。"""

    _tail_tool_event: Annotated[NotRequired[dict], OmitFromInput, _tail_event_last_wins]


def build_tail_tool_middleware(config: Optional[dict]) -> Optional["TailToolMiddleware"]:
    """由 ``AgentConfig.tail_tool_config`` 字典构造中间件。

    ``config`` 为空或既无 ``tasks`` 也无 ``tools`` 时返回 ``None``(Builder 据此跳过挂载)。结构::

        {
            "enabled": True,
            "tasks": [{"name": "suggest", "instruction": "...", "args_schema": {...}, "example": "..."}],
            "tools": [<StructuredTool>, ...],   # 可选,进程内对象
            "fail_mode": "silent" | "message",
            "fail_message": "",
            "trigger_prompt": None,
            "execute_tools": True,
        }
    """
    if not config:
        return None
    tasks = [
        TailTaskSpec(
            name=t["name"],
            instruction=t.get("instruction", ""),
            args_schema=t.get("args_schema"),
            example=t.get("example", ""),
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
        )
    )


class TailToolMiddleware(AgentMiddleware):
    """见模块文档。"""

    state_schema = TailToolState

    def __init__(self, config: TailToolConfig) -> None:
        super().__init__()
        self._config = config
        self._tool_name = TAIL_TOOL_NAME
        self._tools_by_name: dict[str, BaseTool] = {t.name: t for t in config.tools}

        # 捕获自最近一次 awrap_model_call(仅记录 request/response 数据,不持有 handler 闭包)
        self._last_request: Any = None
        self._last_response: Any = None

        if config.enabled:
            self.tools = [self._build_tool()]

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

        tail_messages = self._build_tail_messages(request, response)

        try:
            ai = await self._invoke_tail_model(request, tail_messages)
        except Exception as exc:  # noqa: BLE001 - 尾部失败不应影响主回答
            logger.warning("尾部工具调用失败: %s", exc, exc_info=True)
            return self._failure_event(str(exc))

        calls = self._collect_calls(ai)
        if not calls:
            return self._failure_event(None)
        await self._execute_calls(calls)
        return {"_tail_tool_event": {"status": "ok", "calls": calls, "error": None}}

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
        lines = [_HEADER.format(tool=self._tool_name)]
        for name, instruction, args_schema, example in self._iter_tail_tasks():
            lines.append(self._format_task(name, instruction, args_schema, example))
        lines.append(_FOOTER.format(tool=self._tool_name))
        return "\n".join(lines)

    def _iter_tail_tasks(self):
        """按名称合并 ``tasks`` 与 ``tools``:同名时 task 提供指令、tool 提供结构。

        顺序:先按 ``tasks`` 顺序,再追加未出现在 tasks 中的 ``tools``。
        """
        seen: set[str] = set()
        for spec in self._config.tasks:
            seen.add(spec.name)
            tool = self._tools_by_name.get(spec.name)
            args_schema = spec.args_schema or (
                self._tool_args_schema(tool) if tool is not None else None
            )
            instruction = spec.instruction or (tool.description if tool is not None else "")
            yield spec.name, instruction, args_schema, spec.example
        for tool in self._config.tools:
            if tool.name in seen:
                continue
            yield tool.name, tool.description or "", self._tool_args_schema(tool), ""

    @staticmethod
    def _format_task(
        name: str,
        instruction: str,
        args_schema: Optional[dict[str, Any]],
        example: str,
    ) -> str:
        lines = [f"- {name}: {instruction}" if instruction else f"- {name}"]
        if args_schema:
            lines.append(
                "    arguments(JSON Schema): "
                + json.dumps(args_schema, ensure_ascii=False, sort_keys=True)
            )
        if example:
            lines.append(f"    示例: {example}")
        return "\n".join(lines)

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
        calls: list[dict[str, Any]] = []
        if ai is None:
            return calls
        for tool_call in getattr(ai, "tool_calls", None) or []:
            if tool_call.get("name") != self._tool_name:
                continue
            args = tool_call.get("args") or {}
            calls.append(
                {
                    "task": str(args.get("task", "")),
                    "arguments": self._coerce_arguments(args.get("arguments")),
                    "tool_call_id": tool_call.get("id", ""),
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

    async def _execute_calls(self, calls: list[dict[str, Any]]) -> None:
        """对 ``tools`` 中已注册的尾部任务,在尾部直接执行其真实工具。"""
        for call in calls:
            call["status"] = "ok"
            call["output"] = None
            call["error"] = None
            tool = self._tools_by_name.get(call["task"])
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
            call["output"] = (
                output
                if isinstance(output, str)
                else json.dumps(output, ensure_ascii=False, default=str)
            )

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
