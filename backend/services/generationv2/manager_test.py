from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_mcp_adapters.client import MultiServerMCPClient

from llm_io import LLMInput
from services.generationv2.openai_worker import OpenAiWorker
import asyncio



from backend.config.mcp_config import BING_MCP_SERVER_PATH, DDGS_MCP_SERVER_PATH
from services.generationv2.utils import OpenAiDecode


async def main_non_stream():
    llm_input = LLMInput(model_id='gemini-3-pro-preview-thinking',
                         messages=[{'role': 'system', 'content': '你是一个猫娘~'}, {'role': 'user', 'content': '测试'}],
                         parameters={'stream': False}, api_host='https://aigc.x-see.cn/v1',
                         api_key='sk-tVEx5WzIRoKISRAUQUQjpk092r3XDhPtbvcbqRVRf5L7i2lV',
                         proxy_url=None, tools=None, tool_choice=None, timeout=60)

    async for m,i in OpenAiWorker().generate(llm_input):
        print(OpenAiDecode.get_text_content(m,i),end="") # 模拟executor的append写入
        print(OpenAiDecode.get_reasoning_content(m,i),end="") # 模拟executor的append写入


async def main_stream():
    llm_input = LLMInput(model_id='gemini-3-pro-preview-thinking',
                         messages=[{'role': 'system', 'content': '你是一个猫娘~'}, {'role': 'user', 'content': '测试'}],
                         parameters={'stream': True}, api_host='https://aigc.x-see.cn/v1',
                         api_key='sk-tVEx5WzIRoKISRAUQUQjpk092r3XDhPtbvcbqRVRf5L7i2lV',
                         proxy_url=None, tools=None, tool_choice=None, timeout=60)

    async for m,i in OpenAiWorker().generate(llm_input):
        print(OpenAiDecode.get_text_content(m,i),end="")
        print(OpenAiDecode.get_reasoning_content(m,i),end="")


async def main_mcp():

    client = MultiServerMCPClient(
        {
            "bing_search": {
                "transport": "stdio",
                "command": "python",
                "args": [str(DDGS_MCP_SERVER_PATH)],
            }
        }
    )
    tools = await client.get_tools() # 由manager初始化mcp_client并写入llm_input
    llm_input2 = LLMInput(model_id='Pro/zai-org/GLM-4.7', messages=[{'role': 'system', 'content': '你是一个猫娘~'}, {'role': 'user', 'content': '搜索今日广州天气'}],
                          parameters={'stream': True}, api_host='https://api.siliconflow.cn/v1', api_key='sk-znwdeklerxjqnjfqqzjsahaknrrjbzywuzzxhazibmfqgkii',
                          proxy_url=None, tools=tools, tool_choice=None, timeout=60)
    cs = ""
    rs = ""
    ts = {}
    async for m,i in OpenAiWorker().generate(llm_input2):
        print(m,i)

        c = OpenAiDecode.get_text_content(m,i)
        cs += str(c) if c else ""

        r = OpenAiDecode.get_reasoning_content(m,i)
        rs += str(r) if r else ""

        tc = OpenAiDecode.get_toolcall_content(m,i)
        if tc:
            for t in tc:
                ts[t["id"]] = [t]
        # 现在manager 已经不需要主动执行方法了,由worker中的agent负责执行
        # 我们还需要组合工具的调用和结果(以写入tool-submessage),可通过id进行匹配
        tr = OpenAiDecode.get_toolcall_result(m,i)
        if tr:
            ts[tr["id"]] += [ts]

    print(rs)
    print(cs)
    print(ts)

# image的写入,实际上基本不变
async def main_image():
    llm_input3 = LLMInput(model_id='zai-org/GLM-4.6V', messages=[{'role': 'system', 'content': '你是一个猫娘~'},
                                                                 {'role': 'user', 'content': [{'type': 'text', 'text': '这是那种衣服?'}
                                                                                              ,{'type': 'image_url',
                                                                                               'image_url': {
                                                                                                   'url': 'data:image/jpeg;base64,${base64_str}'
                                                                                                   }
                                                                                               }
                                                                                              ]
                                                                  }
                                                                 ],
                          parameters={'stream': True}, api_host='https://api.siliconflow.cn/v1', api_key='sk-znwdeklerxjqnjfqqzjsahaknrrjbzywuzzxhazibmfqgkii',
                          proxy_url=None, tools=None, tool_choice=None, timeout=60)
    async for m,i in OpenAiWorker().generate(llm_input3):
        x:AIMessageChunk = i
        print(x)

# image的输出
async def main_image_out():
    llm_input3 = LLMInput(model_id='google/gemini-2.5-flash-image',
                          messages=[{'role': 'user', 'content': [{'type': 'text', 'text': '把衣服换成红色'},
                                                                 {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,${base64_str}'}}]}],
                          parameters={'temperature': 0.6, 'top_p': 1.0, 'stream': True}, api_host='https://openrouter.ai/api/v1', api_key='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', proxy_url='http://127.0.0.1:7890', tools=None, tool_choice=None, timeout=60)
    cs = ""
    imgs = []
    async for m,i in OpenAiWorker().generate(llm_input3):
        c = OpenAiDecode.get_text_content(m,i)
        cs += str(c) if c else ""
        img = OpenAiDecode.get_image_url(m,i)
        if img:
            imgs.append(img)
        print(img)



if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main_mcp())
