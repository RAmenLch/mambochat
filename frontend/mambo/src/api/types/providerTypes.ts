// frontend/mambo/src/api/types/providerTypes.ts

export type ProviderWorkerType = 'openai' | 'google' | 'deepseek'
export type ModelType = 'chat' | 'embedding'

export interface AIModelMetaConfig {
  context_length?: number | null
  max_output_tokens?: number | null
  embedding_dimension?: number | null
  tokenizer?: string | null
  input_modalities?: string[] | null
  output_modalities?: string[] | null
  supported_parameters?: string[] | null
}

export interface AIModelBase {
  modelId: string
  name: string
  model_type: ModelType
  meta_config?: AIModelMetaConfig | null
}

export interface AIModel extends AIModelBase {
  id: string
  providerId: string
}

export interface AIModelCreate extends AIModelBase {
  providerId: string
}

export interface AIModelUpdate {
  name?: string
  model_type?: ModelType
  meta_config?: AIModelMetaConfig | null
}

export interface AIProvider {
  id: string
  name: string
  apiHost: string
  worker_type: ProviderWorkerType
  use_proxy: boolean
}

export interface AIProviderWithModels extends AIProvider {
  models: AIModel[]
}

export interface AIProviderCreate {
  id?: string | null
  name: string
  apiHost: string
  apiKey: string
  worker_type: ProviderWorkerType
  use_proxy: boolean
}

export interface AIProviderUpdate {
  name?: string
  apiHost?: string
  apiKey?: string
  worker_type?: ProviderWorkerType
  use_proxy?: boolean
}

export interface ProviderWithModelsCreate extends AIProviderCreate {
  models: AIModelBase[]
}

export interface ConnectionRequest {
  apiHost: string
  apiKey: string
}

export interface ConnectionTestResponse {
  status: string
  message: string
}

// --- System Config Types ---

export interface LLMParameterDefinition {
  key: string
  label: string
  path: string[]
  description: string
  type: 'integer' | 'number' | 'string' | 'boolean'
  limit?: Array<any> | { min?: number; max?: number }
  default_value: any
  default_activate: boolean
}

export interface DefaultProviderInfo {
  name: string
  apiHost: string
  worker_type: ProviderWorkerType
}

export interface SystemConfigResponse {
  llm_parameters: LLMParameterDefinition[]
  default_providers: DefaultProviderInfo[]
}
