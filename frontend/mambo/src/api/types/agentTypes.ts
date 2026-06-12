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
}

export type AgentUpdate = Partial<AgentCreate>

export interface ChatDuplicateRequest {
  up_to_message_id?: string | null;
}

export interface ChatArchiveRequest {
  item_ids: string[];
  new_folder_name: string;
  parent_id?: string | null;
}
