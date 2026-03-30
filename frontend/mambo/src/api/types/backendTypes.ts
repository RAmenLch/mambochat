// frontend/mambo/src/api/types/backendTypes.ts

export type BackendType = 'ssh';

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

export interface BackendConfig {
  id: string;
  name: string;
  description?: string | null;
  backendType: BackendType;
  configData: SshConfigData; // 目前仅支持 SSH，未来可扩展为联合类型
  createdAt: string;
  updatedAt: string;
}

export interface BackendCreate {
  name: string;
  description?: string | null;
  backendType: BackendType;
  configData: SshConfigData;
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
