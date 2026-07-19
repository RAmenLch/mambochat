# backend/services/generation/worker/chat_worker.py
"""通用 Graph Worker —— 适用于 ReactAgent、Mambo Agent 等不需要 VFS 注入的 Agent 类型。

DeepAgent 需要 VFS files 注入，请使用 deep_agent_chat_worker.DeepAgentChatWorker。
"""

from typing import AsyncGenerator, Tuple, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, Overwrite

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker, StreamEvent
from backend.services.generation.core.llm_io import LLMInput
from backend.services.generation.graph_builders.factory import GraphBuilderFactory
from backend.services.generation.core.llm_io import SummarizationEventInfo


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
                    yield "subagent_event", event
                # AI 安全审核事件：AutoSecurityReviewMiddleware 发射的 SecurityReviewPassedEvent / SecurityReviewFailedEvent
                elif isinstance(event, dict) and event.get("type") in ("security_review_passed", "security_review_failed"):
                    yield "security_review", event
            else:
                pass