// frontend/mambo/src/api/types/resourceTypes.ts

import type { FileResponse } from './common';

export type ResourceItemType = 'resource' | 'folder' | 'stub'
export type ResourceType =
  | 'system_prompt'
  | 'submessage_template'
  | 'knowledge_base'
  | 'knowledge_base_chunk'
  | 'kb_file'
  | 'file'
  | 'skill'
  | string

export interface SkillCreate {
  name: string
  description: string
  parentId?: string | null
}

//  SKILL 验证结果
export interface SkillValidationResult {
  is_valid: boolean
  errors: string[]
  warnings: string[]
}




// --- Knowledge Base Types ---

export interface KBFileAttributes {
  splitter_config?: KBSplitterConfig
  last_ingest_config?: KBSplitterConfig
  [key: string]: any
}

export type KBFileStatus =
  | 'INITIAL'
  | 'CLEANING'
  | 'READING'
  | 'SPLITTING'
  | 'EMBEDDING'
  | 'COMPLETED'
  | 'FAILED'
  | 'STOPPED'

export interface KBChunkStatus {
  resource_id: string
  total_chunks: number
  pending_chunks: number
  completed_chunks: number
  failed_chunks: number
  stopped_chunks: number
  file_status: KBFileStatus
  is_stale: boolean
}

export type SplitterType = 'simple' | 'separator' | 'markdown'
export type KBTaskAction = 'start' | 'resume' | 'stop'

export interface KBSplitterConfig {
  splitter_type: SplitterType
  chunk_size: number
  chunk_overlap: number
  separator?: string | null
}

export interface KnowledgeBaseCreate {
  name: string
  description?: string | null
  parent_id?: string | null
  embedding_model_id?: string | null
  embedding_rate_limit?: number
}

export interface KBUpdateConfigRequest {
  splitter_config: KBSplitterConfig
}

export interface KBRunTaskRequest {
  action: KBTaskAction
}

export type KBTaskProgressPayload = KBChunkStatus

export interface KBResumeConflictErrorDetail {
  message: string
  current_config: KBSplitterConfig
  last_ingest_config: KBSplitterConfig
}

export interface KBSearchRequest {
  query_text: string
  kb_id?: string | null
  top_k?: number
}

export interface KBSearchResultItem {
  chunk_id: string
  chunk_content: string
  score: number
  resource_id: string
  resource_name: string
  kb_id: string
  kb_name: string
  chunk_index: number
}

export interface KBSearchResponse {
  total: number
  items: KBSearchResultItem[]
}

export interface KBChunk {
  id: string
  resource_id: string
  content: string
  chunk_index: number
  byte_size: number
  status: 'PENDING' | 'COMPLETED' | 'FAILED' | 'STOPPED'
  vector_id?: number
}

export interface KBChunkListResponse {
  total: number
  items: KBChunk[]
}

export interface KBChunkListRequest {
  min_index?: number
  max_index?: number
  page?: number
  page_size?: number
}

// --- Resource Center Types ---

export interface ResourceVersion {
  id: string
  resourceId: string
  name: string
  commitMessage: string | null
  content: string | null
  attributes: KBFileAttributes | Record<string, any> | null
  sortOrder: number
  createdAt: string // ISO 8601 date string
  updatedAt: string // ISO 8601 date string
  file_info: FileResponse | null
}

export interface Resource {
  id: string
  name: string
  description: string | null
  itemType: ResourceItemType
  resourceType: ResourceType | null
  parentId: string | null
  sortOrder: number
  createdAt: string // ISO 8601 date string
  updatedAt: string // ISO 8601 date string
  latest_version: ResourceVersion | null
  isLoaded?: boolean
  kb_id: string | null
  kb_config: KBSplitterConfig | null
}

export type ResourceNode = Resource & { children?: ResourceNode[] }

export interface ResourceWithVersions extends Resource {
  versions: ResourceVersion[]
}

export interface ResourceCreate {
  name: string
  description?: string | null
  itemType: ResourceItemType
  resourceType?: ResourceType | null
  parentId?: string | null
  sortOrder?: number
  initial_content?: string | null
  initial_attributes?: Record<string, any> | null
}

export interface ResourceUpdate {
  name?: string
  description?: string | null
  parentId?: string | null
}

export interface ResourceReorderItem {
  id: string
  parentId: string | null
  sortOrder: number
}

export interface ResourceVersionCreate {
  name: string
  commitMessage?: string | null
  content?: string | null
  attributes?: Record<string, any> | null
}

export interface ResourceVersionUpdate {
  name?: string
  commitMessage?: string | null
  content?: string | null
  attributes?: Record<string, any> | null
}

// --- Search Types (Resource) ---

export interface ResourceSearchRequest {
  keyword: string
  root_id?: string | null
  enable_regex?: boolean
  page_num?: number
  page_size?: number
}

export type ResourceMatchType = 'name' | 'description' | 'content'

export interface ResourceSearchResultItem {
  resource_id: string
  resource_name: string
  resource_path: string
  match_type: ResourceMatchType
  context_text: string
  version_id: string | null
  updated_at: string
}

export interface ResourceSearchResponse {
  total: number
  items: ResourceSearchResultItem[]
}

export interface SkillImportResultItem {
  name: string
  status: 'success' | 'failed'
  resource_id: string | null
  error: string | null
}

export interface SkillImportResponse {
  total_detected: number
  success_count: number
  failed_count: number
  details: SkillImportResultItem[]
}
