# backend/services/generation/worker/chat_worker.py

import json
from typing import AsyncGenerator, Any, List, Dict, Union, Tuple

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

from backend.services.generation.worker.abstract_worker import AbstractGenerateWorker
from backend.services.generation.core.llm_io import LLMInput, AgentConfig
from backend.services.generation.worker.decode import BaseDecode, DecoderRegistry
from backend.services.generation.graph_builders.factory import GraphBuilderFactory
from backend.schemas.enums import AgentTypeEnum


class UniversalGraphWorker(AbstractGenerateWorker):

    def resolve_decoder(self, message: Any) -> BaseDecode:
        provider = "default"
        if hasattr(message, "response_metadata") and isinstance(message.response_metadata, dict):
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
                    lc_messages.append(AIMessage(content=content, name=name, tool_calls=lc_tool_calls))
                else:
                    lc_messages.append(AIMessage(content=content, name=name))

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
    ) -> AsyncGenerator[Tuple[str, Union[ToolMessage, AIMessageChunk, AIMessage, Dict[str, Any]]], None]:

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

        async for stream1 in agent.astream(
                input=input_data,
                config=thread_config,
                stream_mode=["messages", "updates"],
                version="v2"
        ):
            mode = stream1["type"]
            event = stream1["data"]

            if mode == "updates":
                if "model" in event:
                    for message in event["model"]['messages']:
                        yield mode, message
                if "tools" in event:
                    for message in event["tools"]['messages']:
                        yield mode, message
                if "__interrupt__" in event or "HumanInTheLoopMiddleware.after_model" in event:
                    yield mode, event
            else:
                yield mode, event[0]
