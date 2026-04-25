# backend/services/generation/worker/chat_worker.py

import json
from typing import AsyncGenerator, Any, List, Dict, Tuple

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    AIMessage,
    ToolMessage,
    AIMessageChunk
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, Overwrite
from deepagents.backends.utils import create_file_data

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker, StreamEvent
from backend.services.generation.core.llm_io import LLMInput, AgentConfig
from backend.services.generation.worker.decode import BaseDecode, DecoderRegistry
from backend.services.generation.graph_builders.factory import GraphBuilderFactory
from backend.schemas.enums import AgentTypeEnum


class UniversalGraphWorker(AbstractGenerateWorker):

    def resolve_decoder(self, message: StreamEvent) -> BaseDecode:
        provider = "default"
        if isinstance(message, BaseMessage) and isinstance(message.response_metadata, dict):
            provider = message.response_metadata.get("model_provider", "default")
        return DecoderRegistry.get_decoder(provider)

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        lc_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "") or ''
            name = msg.get("name")

            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content, name=name))
            elif role == "assistant":
                raw_tool_calls = msg.get("tool_calls")
                lc_tool_calls = []

                # 提取 reasoning_content（DeepSeek 思考模式需要回传）
                additional_kwargs = {}
                reasoning_content = msg.get("reasoning_content")
                if reasoning_content:
                    additional_kwargs["reasoning_content"] = reasoning_content

                if raw_tool_calls and isinstance(raw_tool_calls, list):
                    for tc in raw_tool_calls:
                        if "function" in tc:
                            try:
                                args_str = tc["function"].get("arguments", "{}")
                                args_dict = json.loads(args_str) if isinstance(args_str, str) else args_str
                            except json.JSONDecodeError:
                                args_dict = {}

                            lc_tool_calls.append({
                                "name": tc["function"].get("name", ""),
                                "args": args_dict,
                                "id": tc.get("id", "")
                            })
                        elif "name" in tc and "args" in tc:
                            lc_tool_calls.append({
                                "name": tc.get("name", ""),
                                "args": tc.get("args", {}),
                                "id": tc.get("id", "")
                            })

                if lc_tool_calls:
                    lc_messages.append(AIMessage(content=content, name=name, tool_calls=lc_tool_calls, additional_kwargs=additional_kwargs))
                else:
                    lc_messages.append(AIMessage(content=content, name=name, additional_kwargs=additional_kwargs))

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    lc_messages.append(ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        name=name
                    ))
            else:
                lc_messages.append(HumanMessage(content=content, name=name))

        return lc_messages

    def _collect_vfs_files_recursively(self, config: AgentConfig) -> Dict[str, Any]:
        files = {}

        if config.skills:
            for skill in config.skills:
                for file_config in skill.files:
                    if file_config.content is not None:
                        virtual_path = f"/skills/{skill.name}/{file_config.file_path}"
                        files[virtual_path] = create_file_data(file_config.content)

        if config.sub_configs:
            for sub_config in config.sub_configs:
                files.update(self._collect_vfs_files_recursively(sub_config))

        return files

    async def generate(
            self,
            llm_input: LLMInput
    ) -> AsyncGenerator[Tuple[str, StreamEvent], None]:

        graph_builder = GraphBuilderFactory.get_builder(llm_input.agent_config.agent_type)
        agent = graph_builder.build(llm_input.agent_config, llm_input.run_time_config)

        thread_config: RunnableConfig = {"configurable": {"thread_id": llm_input.run_time_config.chat_id}}
        if llm_input.agent_config.recover_from_error:
            input_data = None
        else:
            files_to_inject = {}
            if llm_input.agent_config.agent_type == AgentTypeEnum.DEEP:
                files_to_inject = self._collect_vfs_files_recursively(llm_input.agent_config)

            resume_payload = llm_input.agent_config.resume_payload
            if resume_payload:
                input_data = Command(resume=resume_payload)
            else:
                messages = self._convert_messages(llm_input.context.messages)
                input_data = {"messages": Overwrite(value=messages)}
                if files_to_inject:
                    input_data["files"] = files_to_inject

        async for stream_event in agent.astream(
                input=input_data,
                config=thread_config,
                stream_mode=["messages", "updates"],
                version="v2"
        ):
            if not isinstance(stream_event, dict):
                continue
            mode = stream_event.get("type")
            event = stream_event.get("data")

            if mode == "updates" and isinstance(event, dict):
                if "model" in event:
                    model_update = event["model"]
                    if isinstance(model_update, dict) and "messages" in model_update:
                        for message in model_update["messages"]:
                            yield mode, message
                if "tools" in event:
                    tools_update = event["tools"]
                    if isinstance(tools_update, dict) and "messages" in tools_update:
                        for message in tools_update["messages"]:
                            yield mode, message
                if "__interrupt__" in event or "HumanInTheLoopMiddleware.after_model" in event:
                    yield mode, event
            elif mode == "messages" and isinstance(event, (list, tuple)) and len(event) > 0:
                yield mode, event[0]
