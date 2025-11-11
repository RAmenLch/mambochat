// frontend/mambo/src/constants/metaConfigOptions.ts

/**
 * 可用的输入模态选项
 */
export const inputModalitiesOptions: string[] = [
  'audio',
  'text',
  'video',
  'file',
  'image',
];

/**
 * 可用的输出模态选项
 */
export const outputModalitiesOptions: string[] = [
  'image',
  'text',
];

/**
 * 可用的分词器选项
 */
export const tokenizerOptions: string[] = [
  'GPT',
  'Llama3',
  'Llama2',
  'Qwen3',
  'DeepSeek',
  'Llama4',
  'Nova',
  'Gemini',
  'Router',
  'Mistral',
  'Cohere',
  'Claude',
  'Qwen',
  'Other',
  'Grok',
];

/**
 * 可用的模型支持参数选项
 */
export const supportedParametersOptions: string[] = [
  'top_k',
  'stop',
  'top_a',
  'logit_bias',
  'presence_penalty',
  'tools',
  'response_format',
  'reasoning',
  'top_p',
  'web_search_options',
  'structured_outputs',
  'frequency_penalty',
  'logprobs',
  'temperature',
  'include_reasoning',
  'min_p',
  'top_logprobs',
  'repetition_penalty',
  'seed',
  'max_tokens',
  'tool_choice',
];
