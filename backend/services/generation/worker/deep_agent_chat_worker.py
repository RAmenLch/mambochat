# backend/services/generation/worker/deep_agent_chat_worker.py
"""DeepAgent 专用 ChatWorker —— 继承通用 Worker，增加 VFS files 注入。

DeepAgent 使用 CompositeBackend + TreeStateBackend 架构，
需要通过 input_data["files"] 将 skills 文件注入到 VFS 中。
Mambo Agent 不需要此操作（skills 通过 MamboResourceBackend shortcuts 挂载）。
"""

from typing import AsyncGenerator, Any, Dict, Tuple, List

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, Overwrite

from backend.services.generation.core.llm_io import LLMInput, AgentConfig, SummarizationEventInfo
from backend.services.generation.graph_builders.factory import GraphBuilderFactory
from backend.services.generation.worker.abstract_worker import StreamEvent
from backend.services.generation.worker.chat_worker import UniversalGraphWorker


class DeepAgentChatWorker(UniversalGraphWorker):
    """DeepAgent 专用 Worker：在通用流程基础上注入 VFS files。

    仅需覆盖 generate() 方法，在构建 input_data 时附加
    _collect_vfs_files_recursively 收集的 skills 文件内容。
    """

    def _collect_vfs_files_recursively(self, config: AgentConfig) -> Dict[str, Any]:
        """递归收集所有 skills 文件，构建 VFS files 注入字典。

        将 SkillConfig.files 中的每个文件映射为 VFS 路径：
            /skills/{skill_name}/{file_path}

        Returns:
            {"path": {"content": str, "encoding": "utf-8"}, ...}
        """
        files: Dict[str, Any] = {}

        if config.skills:
            for skill in config.skills:
                for file_config in skill.files:
                    if file_config.content is not None:
                        virtual_path = f"/skills/{skill.name}/{file_config.file_path}"
                        files[virtual_path] = {
                            "content": file_config.content,
                            "encoding": "utf-8",
                        }

        if config.sub_configs:
            for sub_config in config.sub_configs:
                files.update(self._collect_vfs_files_recursively(sub_config))

        return files

    async def generate(
        self,
        llm_input: LLMInput,
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
        # resume 场景下不设置 checkpoint_id（详见 chat_worker.py 注释）
        if llm_input.run_time_config.branch_checkpoint_id:
            thread_config["configurable"]["checkpoint_id"] = llm_input.run_time_config.branch_checkpoint_id
        else:
            _cq_config = {"configurable": {"thread_id": llm_input.run_time_config.chat_id}}
            try:
                cp_tuple = await agent.checkpointer.aget_tuple(_cq_config)
                if cp_tuple and cp_tuple.checkpoint:
                    thread_config["configurable"]["checkpoint_map"] = {"": cp_tuple.checkpoint["id"]}
            except Exception:
                pass

        if llm_input.agent_config.recover_from_error:
            input_data = None
        else:
            # DeepAgent 特有：收集 skills 文件注入 VFS
            files_to_inject = self._collect_vfs_files_recursively(llm_input.agent_config)

            # When resuming from an interrupt (ask_user / HITL), skip
            # aupdate_state — it creates a new checkpoint that drops the
            # pending INTERRUPT write, preventing the interrupted task
            # from being rescheduled, and can re-trigger the model node
            # via _summarization_event channel version bump.
            if not resume_payload:
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
                if files_to_inject:
                    input_data["files"] = files_to_inject
            else:
                input_data = Command(resume=resume_payload)

        async for stream_event in agent.astream(
            input=input_data,
            config=thread_config,
            stream_mode=["messages", "updates", "custom"],
            version="v2",
        ):
            if not isinstance(stream_event, dict):
                continue
            mode = stream_event.get("type")
            event = stream_event.get("data")

            if mode == "updates" and isinstance(event, dict):
                if "model" in event:
                    model_update = event["model"]
                    if isinstance(model_update, dict):
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
                if isinstance(meta, dict) and meta.get("lc_source") == "summarization":
                    continue
                yield mode, msg
            elif mode == "custom":
                # 版本控制备份事件：VersionControlMiddleware 发射的 BackupEvent
                if isinstance(event, dict) and event.get("type") == "backup":
                    yield "version_snapshot", event
                elif isinstance(event, dict) and event.get("type") == "subagent_event":
                    yield "subagent_event", event
                elif isinstance(event, dict) and event.get("type") in ("security_review_passed", "security_review_failed"):
                    yield "security_review", event
            else:
                pass
