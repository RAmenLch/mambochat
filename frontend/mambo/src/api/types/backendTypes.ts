// frontend/mambo/src/api/types/backendTypes.ts

export type BackendType = 'ssh' | 'api' | 'resource' | 'local';

export interface ToolPermission {
  enabled: boolean;
  require_review: boolean;
}

export interface ToolsConfig {
  execute: ToolPermission;
}

export const defaultToolsConfig = (): ToolsConfig => ({
  execute: { enabled: false, require_review: true }
});

export interface SshConfigData {
  hostname: string;
  username: string;
  port?: number;
  password?: string | null;
  root_dir?: string;
  edit_whitelist?: string[] | null;
  edit_blacklist?: string[] | null;
  ignore_dirs?: string[] | null;
  api_key?: string;
  resource_id?: string;
  enable_version_editing?: boolean;
}

export interface ApiConfigData {
  api_key: string;
  edit_whitelist?: string[] | null;
  edit_blacklist?: string[] | null;
  hostname?: string;
  username?: string;
  port?: number;
  password?: string | null;
  root_dir?: string;
  ignore_dirs?: string[] | null;
  resource_id?: string;
  enable_version_editing?: boolean;
}

export interface ResourceConfigData {
  resource_id: string;
  edit_whitelist?: string[] | null;
  edit_blacklist?: string[] | null;
  enable_version_editing?: boolean;
  hostname?: string;
  username?: string;
  port?: number;
  password?: string | null;
  root_dir?: string;
  ignore_dirs?: string[] | null;
  api_key?: string;
}

export interface LocalConfigData {
  root_dir: string;
  edit_whitelist?: string[] | null;
  edit_blacklist?: string[] | null;
  ignore_dirs?: string[] | null;
  hostname?: string;
  username?: string;
  port?: number;
  password?: string | null;
  api_key?: string;
  resource_id?: string;
  enable_version_editing?: boolean;
}

export type BackendConfigData = SshConfigData | ApiConfigData | ResourceConfigData | LocalConfigData;

export interface BackendConfig {
  id: string;
  name: string;
  description?: string | null;
  backendType: BackendType;
  configData: BackendConfigData;
  tools_config?: ToolsConfig | null;
  createdAt: string;
  updatedAt: string;
}

export interface BackendCreate {
  name: string;
  description?: string | null;
  backendType: BackendType;
  configData: BackendConfigData;
  tools_config?: ToolsConfig;
}

export interface BackendUpdate extends Partial<BackendCreate> {}

export interface SshPublicKeyResponse {
  public_key: string;
}

export interface SshTestRequest {
  backend_id?: string | null;
  configData: Record<string, any>;
}

export interface SshTestResponse {
  success: boolean;
  message: string;
}

export interface SshLsEntry {
  path: string;
  is_dir: boolean;
  size: number;
  modified_at: string;
}

export interface LocalLsResponse {
  success: boolean;
  message: string;
  entries?: SshLsEntry[] | null;
  parent_path?: string | null;
}

export interface UnifiedLsRequest {
  backend_type: BackendType;
  path: string;
  root_dir: string;
  /** SSH only */
  hostname?: string | null;
  port?: number;
  username?: string | null;
  password?: string | null;
  /** Common */
  backend_id?: string | null;
}

export function isSshConfig(data: BackendConfigData): data is SshConfigData {
  return 'hostname' in data;
}

export function isApiConfig(data: BackendConfigData): data is ApiConfigData {
  return 'api_key' in data;
}

export function isResourceConfig(data: BackendConfigData): data is ResourceConfigData {
  return 'resource_id' in data;
}
