// frontend/mambo/src/api/types/backendTypes.ts

export type BackendType = 'ssh' | 'api';

export interface SshConfigData {
  hostname: string;
  username: string;
  port?: number;
  password?: string | null;
  root_dir?: string;
  edit_whitelist?: string[] | null;
  edit_blacklist?: string[] | null;
  ignore_dirs?: string[] | null;
}

export interface ApiConfigData {
  api_key: string;
  edit_whitelist?: string[] | null;
  edit_blacklist?: string[] | null;
}

export type BackendConfigData = SshConfigData | ApiConfigData;

export interface BackendConfig {
  id: string;
  name: string;
  description?: string | null;
  backendType: BackendType;
  configData: BackendConfigData;
  createdAt: string;
  updatedAt: string;
}

export interface BackendCreate {
  name: string;
  description?: string | null;
  backendType: BackendType;
  configData: BackendConfigData;
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

export function isSshConfig(data: BackendConfigData): data is SshConfigData {
  return 'hostname' in data;
}

export function isApiConfig(data: BackendConfigData): data is ApiConfigData {
  return 'api_key' in data;
}
