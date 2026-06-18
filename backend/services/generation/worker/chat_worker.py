# backend/services/generation/worker/chat_worker.py
"""通用 Graph Worker —— 适用于 ReactAgent、Mambo Agent 等不需要 VFS 注入的 Agent 类型。

DeepAgent 需要 VFS files 注入，请使用 deep_agent_chat_worker.DeepAgentChatWorker。
"""

from typing import AsyncGenerator, Tuple, List

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
        # 指定分支 checkpoint → LangGraph 会进行时间旅行，从该 checkpoint 分叉
        if llm_input.run_time_config.branch_checkpoint_id:
            thread_config["configurable"]["checkpoint_id"] = llm_input.run_time_config.branch_checkpoint_id

        if llm_input.agent_config.recover_from_error:
            input_data = None
        else:
            # Sync _summarization_event with context_builder's rebuilt event
            # - None → clear stale event from previous run
            # - non-None → overwrite with recalculated cutoff_index from DB
            await agent.aupdate_state(
                thread_config,
                {"_summarization_event": llm_input.context.auto_summarization_event},
            )

            resume_payload = llm_input.agent_config.resume_payload
            if resume_payload:
                input_data = Command(resume=resume_payload)
            else:
                messages = self._convert_messages(llm_input.context.messages)
                input_data = {"messages": Overwrite(value=messages)}

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
                            cutoff_index = summary.get("cutoff_index", 0)
                            state = await agent.aget_state(thread_config)
                            state_messages: List = state.values["messages"]
                            if cutoff_index and state_messages and cutoff_index <= len(state_messages):
                                last_zip_message = state_messages[cutoff_index - 1]
                                yield "summarization", SummarizationEventInfo(
                                    last_zip_message=last_zip_message,
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
                            cutoff_index = summary.get("cutoff_index", 0)
                            state = await agent.aget_state(thread_config)
                            state_messages: List = state.values["messages"]
                            if cutoff_index and state_messages and cutoff_index <= len(state_messages):
                                last_zip_message = state_messages[cutoff_index - 1]
                                yield "summarization", SummarizationEventInfo(
                                    last_zip_message=last_zip_message,
                                    event=summary,
                                )
                        if "messages" in tools_update:
                            for message in tools_update["messages"]:
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
                # 子代理内部事件：mambo_agents SubAgentMiddleware 发射的 custom stream_writer 事件
                if isinstance(event, dict) and event.get("type") == "subagent_event":
                    yield "subagent_event", event
                # AI 安全审核事件：AutoSecurityReviewMiddleware 发射的 SecurityReviewPassedEvent / SecurityReviewFailedEvent
                elif isinstance(event, dict) and event.get("type") in ("security_review_passed", "security_review_failed"):
                    yield "security_review", event
            else:
                pass