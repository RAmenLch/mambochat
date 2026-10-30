// frontend/mambo/src/api/types/imageGenTypes.ts

export interface ImageGenConfig {
  id: string;
  name: string;
  description: string | null;
  mcpServerId: string;
  defaultCount: number;
  defaultSync: boolean;
  defaultResolution: string;
  defaultWaitTimeout: number;
  timeout: number | null;
  enableStandardTools: boolean;
  enableGenerateShow: boolean;
  isEnabled: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ImageGenConfigCreate {
  name: string;
  description?: string | null;
  mcpServerId: string;
  defaultCount?: number;
  defaultSync?: boolean;
  defaultResolution?: string;
  defaultWaitTimeout?: number;
  timeout?: number | null;
  enableStandardTools?: boolean;
  enableGenerateShow?: boolean;
  isEnabled?: boolean;
}

export interface ImageGenConfigUpdate {
  name?: string;
  description?: string | null;
  mcpServerId?: string;
  defaultCount?: number;
  defaultSync?: boolean;
  defaultResolution?: string;
  defaultWaitTimeout?: number;
  timeout?: number | null;
  enableStandardTools?: boolean;
  enableGenerateShow?: boolean;
  isEnabled?: boolean;
}

export interface ImageGenToolCheckResult {
  status: 'healthy' | 'unhealthy';
  server_name: string | null;
  found_tools: string[];
  missing_tools: string[];
  message: string;
  error: string | null;
}
