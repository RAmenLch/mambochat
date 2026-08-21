# backend/services/generation/worker/chat_worker.py
"""通用 Graph Worker —— 适用于 ReactAgent、Mambo Agent 等不需要 VFS 注入的 Agent 类型。

DeepAgent 需要 VFS files 注入，请使用 deep_agent_chat_worker.DeepAgentChatWorker。
"""

from typing import AsyncGenerator, Tuple, Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, Overwrite

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker, StreamEvent
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.graph_builders.factory import GraphBuilderFactory
from backend.services.generation.core.llm_io import SummarizationEventInfo

# GoalLoopMiddleware 注入的 get_goal 工具调用 ID 前缀
# （对应 mambo_agents.middleware.goal_loop._INJECT_PREFIX = "goal-loop-"）。
_GOAL_LOOP_INJECT_PREFIX = "goal-loop-"

# GoalLoopMiddleware.after_agent 节点名。该节点以"相同消息 id 原地替换"的方式
# 把 get_goal 调用追加到最后一条模型 AIMessage 上并跳回 tools 节点执行
# （after_agent 仅在模型无工具调用的轮次运行，故副本 tool_calls 只含注入的 get_goal）。
# 该分支只提取 goal-loop- 注入调用构造合成消息交给 ToolExecutionHandler，
# 使 get_goal 像 write_plans 等中间件工具一样落库为 MCP_TOOL 子消息，与 state 对齐。
_GOAL_LOOP_AFTER_AGENT_NODE = "GoalLoopMiddleware.after_agent"


class UniversalGraphWorker(AbstractGenerateWorker):
    """通用 Graph Worker：适用于不需要 VFS 文件注入的 Agent（React / Mambo）。

    DeepAgent 请使用 DeepAgentChatWorker。
    """

    async def generate(
            self,
            llm_input: LLMInput
    ) -> AsyncGenerator[Tuple[str, StreamEvent], None]:

        graph_builder = GraphBuilderFactory.get_builder(llm_input.agent_config.agent_type)
        agent = graph_builder.build(llm_input.agent_config, llm_input.run_time_config)

        thread_config: RunnableConfig = {
            "configurable": {
                "thread_id": llm_input.run_time_config.chat_id,
                "checkpoint_ns": "",
            }
        }
        resume_payload = llm_input.agent_config.resume_payload
        # 将父 checkpoint 通过自定义字段传递给 VersionControlMiddleware，
        # 避免被 LangGraph prepare_single_task 的 checkpoint_id=None 覆盖
        vc_parent_cp: Optional[str] = None
        if llm_input.run_time_config.branch_checkpoint_id:
            thread_config["configurable"]["checkpoint_id"] = llm_input.run_time_config.branch_checkpoint_id
            vc_parent_cp = llm_input.run_time_config.branch_checkpoint_id
        else:
            # 正常对话：从 checkpointer 查询上一次的 checkpoint_id
            _cq_config = {"configurable": {"thread_id": llm_input.run_time_config.chat_id}}
            try:
                cp_tuple = await agent.checkpointer.aget_tuple(_cq_config)
                if cp_tuple and cp_tuple.checkpoint:
                    vc_parent_cp = cp_tuple.checkpoint["id"]
            except Exception:
                pass

        # 将父 checkpoint 存入自定义字段，避免被 LangGraph per-task config 覆盖
        if vc_parent_cp:
            thread_config["configurable"]["version_control_ckpt_id"] = vc_parent_cp

        if llm_input.agent_config.recover_from_error:
            input_data = None
        else:
            # When resuming from an interrupt (ask_user / HITL), skip
            # aupdate_state — it creates a new checkpoint that drops the
            # pending INTERRUPT write, preventing the interrupted task
            # from being rescheduled, and can re-trigger the model node
            # via _summarization_event channel version bump.
            if not resume_payload:
                # Sync _summarization_event with context_builder's rebuilt event
                # - None → clear stale event from previous run
                # - non-None → overwrite with recalculated cutoff_index from DB
                updated_config = await agent.aupdate_state(
                    thread_config,
                    {"_summarization_event": llm_input.context.auto_summarization_event},
                )
                # For time-travel: sync the forked checkpoint_id so astream()
                # continues from the updated state, not the original replay target.
                updated_cp_id = updated_config["configurable"].get("checkpoint_id")
                if updated_cp_id:
                    thread_config["configurable"]["checkpoint_id"] = updated_cp_id
                messages = self._convert_messages(llm_input.context.messages)
                input_data = {"messages": Overwrite(value=messages)}
            else:
                input_data = Command(resume=resume_payload)

        # goal_loop 的 after_agent 副本已在上述分支单独处理（只提取 get_goal 注入调用），
        # model/tools 节点发射的 messages 天然唯一，直接透传给 Handler 链。
        async for stream_event in agent.astream(
                input=input_data,
                config=thread_config,
                stream_mode=["messages", "updates", "custom"],
                version="v2"
        ):
            if not isinstance(stream_event, dict):
                continue
            mode = stream_event.get("type")
            event = stream_event.get("data")

            if mode == "updates" and isinstance(event, dict):
                # GoalLoopMiddleware.after_agent：其 messages 是"模型 AIMessage 的原地替换副本"
                # （同一 id，追加了注入的 get_goal 调用）。正文在 updates 模式下不会重复落库
                # （provider decoder 的 get_text_content 在 updates 模式返回 None），因此只需
                # 提取 goal-loop- 前缀的注入调用，构造"纯调用"合成消息交给 ToolExecutionHandler，
                # 使 get_goal 像 write_plans 等中间件工具一样落库为 MCP_TOOL 子消息，与 state 对齐。
                if _GOAL_LOOP_AFTER_AGENT_NODE in event:
                    after_update = event[_GOAL_LOOP_AFTER_AGENT_NODE]
                    if isinstance(after_update, dict) and "messages" in after_update:
                        for message in after_update["messages"]:
                            if isinstance(message, AIMessage):
                                injected = [
                                    tc for tc in (message.tool_calls or [])
                                    if str(tc.get("id", "")).startswith(_GOAL_LOOP_INJECT_PREFIX)
                                ]
                                if injected:
                                    # 保留原消息 id：run_uuid 归属原模型轮次，
                                    # context_builder 才能把 get_goal 归入同一 assistant 轮重建。
                                    # content 用空串：updates 模式 decoder 不产出正文，
                                    # 空 content 不会被 TextAndReasoningHandler 落库。
                                    synthetic = AIMessage(
                                        id=getattr(message, "id", None),
                                        content="",
                                        tool_calls=injected,
                                    )
                                    yield mode, synthetic
                    continue
                if "model" in event:
                    model_update = event["model"]
                    if isinstance(model_update, dict):
                        # Extract summarization event (complete cumulative state, last-wins)
                        if "_summarization_event" in model_update:
                            summary = model_update["_summarization_event"]
                            last_msg = summary.get("last_summarized_message")
                            if last_msg is not None:
                                yield "summarization", SummarizationEventInfo(
                                    last_zip_message=last_msg,
                                    event=summary,
                                )
                        if "messages" in model_update:
                            for message in model_update["messages"]:
                                yield mode, message
                if "tools" in event:
                    tools_update = event["tools"]
                    if isinstance(tools_update, dict):
                        # Extract summarization event from compact_conversation tool (complete cumulative state, last-wins)
                        if "_summarization_event" in tools_update:
                            summary = tools_update["_summarization_event"]
                            last_msg = summary.get("last_summarized_message")
                            if last_msg is not None:
                                yield "summarization", SummarizationEventInfo(
                                    last_zip_message=last_msg,
                                    event=summary,
                                )
                        if "messages" in tools_update:
                            for message in tools_update["messages"]:
                                yield mode, message
                if "MamboPlanMiddleware.after_model" in event:
                    after_update = event["MamboPlanMiddleware.after_model"]
                    if isinstance(after_update, dict) and "messages" in after_update:
                        for message in after_update["messages"]:
                            yield mode, message
                if "__interrupt__" in event or "HumanInTheLoopMiddleware.after_model" in event or "AutoSecurityReviewMiddleware.after_model" in event:
                    yield mode, event
            elif mode == "messages" and isinstance(event, (list, tuple)) and len(event) > 0:
                msg = event[0]
                meta = event[1] if len(event) > 1 else {}
                # Filter out summarization model outputs (both chunks and final messages)
                if isinstance(meta, dict) and meta.get("lc_source") == "summarization":
                    continue
                yield mode, msg
            elif mode == "custom":
                # 版本控制备份事件：VersionControlMiddleware 发射的 BackupEvent
                if isinstance(event, dict) and event.get("type") == "backup":
                    yield "version_snapshot", event
                # 子代理内部事件：mambo_agents SubAgentMiddleware 发射的 custom stream_writer 事件
                elif isinstance(event, dict) and event.get("type") == "subagent_event":
                    chunk = event.get("chunk", {})
                    if isinstance(chunk, dict):
                        for key in list(chunk.keys()):
                            if key.endswith(".after_model"):
                                after_data = chunk[key]
                                if isinstance(after_data, dict):
                                    tool_msgs = [
                                        m for m in after_data.get("messages", [])
                                        if hasattr(m, "tool_call_id")
                                    ]
                                    if tool_msgs:
                                        rewritten = dict(chunk)
                                        del rewritten[key]
                                        tools_entry: dict = rewritten.setdefault("tools", {})
                                        existing: list = list(tools_entry.get("messages", []))
                                        tools_entry["messages"] = [*existing, *tool_msgs]
                                        event = {**event, "chunk": rewritten}
                    yield "subagent_event", event
                # AI 安全审核事件：AutoSecurityReviewMiddleware 发射的 SecurityReviewPassedEvent / SecurityReviewFailedEvent
                elif isinstance(event, dict) and event.get("type") in ("security_review_passed", "security_review_failed"):
                    yield "security_review", event
            else:
                pass