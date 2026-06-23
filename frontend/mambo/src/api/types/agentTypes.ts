// frontend/mambo/src/api/types/agentTypes.ts
export type AgentItemType = 'agent' | 'folder';
export type AgentType = 'ReActAgent' | 'DeepAgent' | 'Mambo';

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
  agentParameters: Record<string, any> | null;
  aiModelId: string | null;
  agentAvatarId: string | null;
  agentAvatarUrl: string | null;
  resourcePromptList: string[] | null;
  enabledMcpIds: string[] | null;
  subAgents: string[] | null;
  backendIds: string[] | null;
  defaultBackendId: string | null;
}

export interface SecurityReviewConfig {
  enabled: boolean
  model_id?: string | null
  system_prompt?: string | null
  review_tools?: string[] | null
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
  agentParameters?: Record<string, any> | null;
  aiModelId?: string | null;
  agentAvatarId?: string | null;
  resourcePromptList?: string[] | null;
  enabledMcpIds?: string[] | null;
  subAgents?: string[] | null;
  backendIds: string[] | null;
  defaultBackendId?: string | null;
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
