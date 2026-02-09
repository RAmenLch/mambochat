// frontend/mambo/src/api/types/mcpTypes.ts

export type McpTransportType = 'stdio' | 'sse';
export type McpHealthStatus = 'healthy' | 'unhealthy' | null;

export interface McpServer {
  id: string;
  name: string;
  description: string | null;
  transportType: McpTransportType;
  isEnabled: boolean;
  isSystem: boolean;

  // 状态字段
  last_status: McpHealthStatus;
  last_test_at: string | null;
  last_error: string | null;

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

export interface McpTestResponse {
  status: 'healthy' | 'unhealthy';
  tools_count: number;
  message: string;
  error: string | null;
}
