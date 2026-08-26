"""内部模型调用标记（lc_source）白名单。

mambo_agents 在内部辅助模型调用（对话摘要 summarization、多模态描述
multimodal_describer）时，通过 ``config.metadata.lc_source`` 打上来源标记，
用于下游区分「面向用户的模型输出」与「内部辅助输出」。

Worker 消费消息流（``mode == "messages"``）时，必须按此集合过滤这些内部
调用产生的 chunks / 最终消息——否则内部输出（如思考内容、描述模型的中间
输出）会被误消费、渲染成主 Agent 的内部消息。
"""

INTERNAL_LC_SOURCES = frozenset({"summarization", "multimodal_describer"})
"""内部辅助模型调用的 lc_source 标记集合。"""
