// frontend/mambo/src/api/types/imageGenTypes.ts

export type ImageGenBackendType = 'mcp' | 'model'

export interface ImageGenConfig {
  id: string;
  name: string;
  description: string | null;
  backendType: ImageGenBackendType;
  mcpServerId: string | null;
  aiModelId: string | null;
  supportsReferenceImages: boolean | null;
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
  backendType?: ImageGenBackendType;
  mcpServerId?: string | null;
  aiModelId?: string | null;
  supportsReferenceImages?: boolean | null;
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
  backendType?: ImageGenBackendType;
  mcpServerId?: string | null;
  aiModelId?: string | null;
  supportsReferenceImages?: boolean | null;
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
  backend_type?: ImageGenBackendType | null;
  found_tools: string[];
  missing_tools: string[];
  supports_reference_images?: boolean | null;
  message: string;
  error: string | null;
}
