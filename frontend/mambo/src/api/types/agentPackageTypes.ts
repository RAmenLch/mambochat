// Agent 导出包（.mamboagent）相关类型定义
// 与 backend/schemas/agent_package.py 中的导入响应模型对齐

export interface AgentPackageRenameSuggestion {
  entity_type: string; // 'agent' | 'provider' | 'backend' | 'resource_namespace' | 'subagent_folder'
  source_id: string;
  original_name: string;
  new_name: string;
}

export interface AgentPackageProviderBrief {
  source_id: string;
  name: string;
}

export interface AgentPackageResourcePreview {
  name: string;
  itemType: string;
  resourceType: string | null;
  children: AgentPackageResourcePreview[];
}

export interface AgentPackagePreview {
  importable: boolean;
  format_version: string;
  mambochat_version: string;
  exported_at: string;
  description: string | null;
  warnings: string[];
  rename_suggestions: AgentPackageRenameSuggestion[];
  providers_missing_api_key: AgentPackageProviderBrief[];
  resource_tree: AgentPackageResourcePreview[];
}

export interface AgentPackageCreatedEntity {
  entity_type: string; // 'provider' | 'resource' | 'mcp' | 'backend' | 'agent' | 'file'
  source_id: string;
  new_id: string;
}

export interface AgentPackageImportReport {
  import_session_id: string;
  success: boolean;
  main_agent_id: string | null;
  created: AgentPackageCreatedEntity[];
  failed_phase: string | null;
  failed_entity: string | null;
  error: string | null;
  providers_missing_api_key: AgentPackageProviderBrief[];
}

export interface AgentPackageCleanupReport {
  cleaned: string[];
}
