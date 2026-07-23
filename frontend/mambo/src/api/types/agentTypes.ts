// frontend/mambo/src/api/types/agentTypes.ts
export type AgentItemType = 'agent' | 'folder';
export type AgentType = 'ReActAgent' | 'DeepAgent' | 'Mambo';

export interface SummarizationConfig {
  trigger_type: 'fraction' | 'tokens' | 'messages'
  trigger_value: number
  keep_type: 'fraction' | 'tokens' | 'messages'
  keep_value: number
  offload_to_backend: boolean
}

export interface SecurityReviewConfig {
  enabled: boolean
  model_id?: string | null
  system_prompt?: string | null
  review_tools?: string[] | null
}

export interface VersionControlConfig {
  enabled: boolean
  auto_snapshot: boolean
}

export interface MamboAgentParameters {
  include_general_purpose: boolean
  enable_planning: boolean
  enable_memory: boolean
  enable_summarization: boolean
  enable_show: boolean
  memory_resource_ids: string[]
  summarization_config?: SummarizationConfig | null
  security_review?: SecurityReviewConfig | null
  version_control?: VersionControlConfig | null
  mcp_direct_tool_threshold: number
}

export interface Agent {
  id: string;
  createdAt: string;
  updatedAt: string;
  name: string;
  description: string | null;
  itemType: AgentItemType;
  parentId: string | null;
  sortOrder: number;
  AgentType: AgentType;
  systemPrompt: string | null;
  modelParameters: Record<string, any> | null;
  agentParameters: MamboAgentParameters | null;
  aiModelId: string | null;
  agentAvatarId: string | null;
  agentAvatarUrl: string | null;
  resourcePromptList: string[] | null;
  enabledMcpIds: string[] | null;
  subAgents: string[] | null;
  backendIds: string[] | null;
  defaultBackendId: string | null;
}

export interface AgentCreate {
  name: string;
  description?: string | null;
  itemType?: AgentItemType;
  parentId?: string | null;
  sortOrder?: number;
  AgentType?: AgentType;
  systemPrompt?: string | null;
  modelParameters?: Record<string, any> | null;
  agentParameters?: MamboAgentParameters | null;
  aiModelId?: string | null;
  agentAvatarId?: string | null;
  resourcePromptList?: string[] | null;
  enabledMcpIds?: string[] | null;
  subAgents?: string[] | null;
  backendIds: string[] | null;
  defaultBackendId?: string | null;
  // 转运字段（Router 层合并进 agentParameters）
  memoryResourceIds?: string[] | null;
  securityReviewConfig?: SecurityReviewConfig | null;
}

export type AgentUpdate = Partial<AgentCreate>

export interface ChatDuplicateRequest {
  up_to_message_id?: string | null;
}

export interface HitlToolInfo {
  name: string;
  source: 'mcp' | 'backend';
}

export interface ChatArchiveRequest {
  item_ids: string[];
  new_folder_name: string;
  parent_id?: string | null;
}
