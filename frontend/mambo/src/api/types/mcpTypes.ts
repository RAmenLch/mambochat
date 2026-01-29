// frontend/mambo/src/api/types/mcpTypes.ts

export type McpTransportType = 'stdio' | 'sse';

export interface McpServer {
  id: string;
  name: string;
  description: string | null;
  transportType: McpTransportType;
  isEnabled: boolean;
  isSystem: boolean;

  // STDIO 模式专属字段
  command: string | null;
  args: string[] | null;
  env: Record<string, string> | null;

  // SSE 模式专属字段
  url: string | null;
}

export interface McpCreateRequest {
  name: string;
  description?: string | null;
  transportType: McpTransportType;
  isEnabled?: boolean;

  // STDIO 模式参数
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;

  // SSE 模式参数
  url?: string | null;
}

export interface McpUpdateRequest {
  name?: string;
  description?: string | null;
  transportType?: McpTransportType;
  isEnabled?: boolean;

  // STDIO 模式参数
  command?: string | null;
  args?: string[] | null;
  env?: Record<string, string> | null;

  // SSE 模式参数
  url?: string | null;
}
